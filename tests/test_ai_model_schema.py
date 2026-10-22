import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ai_models.models import AIModelSpec
from daras_ai_v2.ai_model_form import (
    build_combined_input_schema,
    extract_openapi_schema,
)
from functions.workflow_tools import WorkflowLLMTool
from recipes.ImageGenPage import ImageGenPage


def test_image_tool_schema_inlines_component_refs_after_workflow_wrapping():
    document = _image_openapi_schema()
    original = copy.deepcopy(document)
    model = AIModelSpec(name="test-image", schema=document)
    saved_run = SimpleNamespace(
        workflow=ImageGenPage.workflow,
        state={"selected_model": model.name, "inputs": {"prompt": "test"}},
    )
    published_run = SimpleNamespace(title="Image generation", notes="Generate an image")
    models = MagicMock()
    models.__iter__.side_effect = lambda: iter([model])
    models.order_for_frontend.return_value.values_list.return_value = [model.name]
    with (
        patch("daras_ai_v2.workflow_url_input.url_to_runs") as url_to_runs,
        patch.object(AIModelSpec.objects, "filter", return_value=models),
    ):
        url_to_runs.return_value = (ImageGenPage, saved_run, published_run)
        tool = WorkflowLLMTool("https://gooey.ai/image-generation/")

    parameters = tool.spec_openai["function"]["parameters"]
    inputs = parameters["properties"]["inputs"]
    assert inputs["required"] == ["prompt"]
    image_size = inputs["properties"]["image_size"]
    assert image_size["default"] == "square_hd"
    assert image_size["anyOf"][0]["enum"] == ["square_hd", "landscape_4_3"]
    dimensions = image_size["anyOf"][1]
    assert dimensions["properties"]["width"] == {"type": "integer", "minimum": 1}
    assert dimensions["properties"]["height"] == {"type": "integer", "minimum": 1}
    assert dimensions["required"] == ["width", "height"]
    assert '"$ref"' not in json.dumps(parameters)
    assert "selected_model" not in parameters["properties"]
    assert document == original


@pytest.mark.parametrize("definitions_key", ["$defs", "definitions"])
def test_combined_schema_inlines_plain_json_schema_refs(definitions_key):
    document = {
        "type": "object",
        "properties": {
            "size": {
                "$ref": f"#/{definitions_key}/Size~1in~0pixels",
                "description": "Output size",
            },
            "skip_me": {"type": "string"},
            "not_common": {"type": "string"},
        },
        "required": ["size", "skip_me"],
        definitions_key: {"Size/in~pixels": {"type": "integer", "minimum": 1}},
    }
    original = copy.deepcopy(document)
    other = {"properties": {"size": {}, "skip_me": {}}}
    result = build_combined_input_schema(
        [AIModelSpec(schema=document), AIModelSpec(schema=other)],
        skip_fields=["skip_me"],
    )
    assert result == {
        "type": "object",
        "properties": {
            "size": {"type": "integer", "minimum": 1, "description": "Output size"}
        },
        "required": ["size"],
    }
    assert document == original


def test_extract_response_schema_keeps_original_contract():
    document = _image_openapi_schema()
    document["paths"]["/test-image/requests/{request_id}"] = {
        "get": {
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Input"}
                        }
                    }
                }
            }
        }
    }
    result = extract_openapi_schema(document, "response")
    assert result is document["components"]["schemas"]["Input"]
    assert result["properties"]["image_size"]["anyOf"][0] == {
        "$ref": "#/components/schemas/ImageSize"
    }


def test_combined_schema_does_not_resolve_discarded_fields():
    document = _image_openapi_schema()
    properties = document["components"]["schemas"]["Input"]["properties"]
    properties["skipped"] = {"$ref": "#/components/schemas/Missing"}
    properties["not_common"] = {"$ref": "#/components/schemas/Missing"}
    other = {"properties": {"prompt": {}, "image_size": {}, "skipped": {}}}

    result = build_combined_input_schema(
        [AIModelSpec(schema=document), AIModelSpec(schema=other)],
        skip_fields=["skipped"],
    )

    assert set(result["properties"]) == {"prompt", "image_size"}
    assert '"$ref"' not in json.dumps(result)


@pytest.mark.parametrize(
    ("ref", "error"),
    [
        ("#/components/schemas/Missing", "Unresolved schema reference"),
        ("#/components/schemas/Input", "Recursive schema reference"),
        ("https://example.com/schema.json", "Unsupported schema reference"),
    ],
)
def test_invalid_refs_fail_at_schema_construction(ref, error):
    document = _image_openapi_schema()
    document["components"]["schemas"]["Input"]["properties"]["image_size"] = {
        "$ref": ref
    }
    with pytest.raises(ValueError, match=error):
        build_combined_input_schema([AIModelSpec(schema=document)])


def _image_openapi_schema():
    return {
        "info": {"x-fal-metadata": {"endpointId": "test-image"}},
        "paths": {
            "/test-image": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Input"}
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Input": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "image_size": {
                            "anyOf": [
                                {"$ref": "#/components/schemas/ImageSize"},
                                {"$ref": "#/components/schemas/Dimensions"},
                            ],
                            "default": "square_hd",
                        },
                    },
                    "required": ["prompt"],
                },
                "ImageSize": {
                    "type": "string",
                    "enum": ["square_hd", "landscape_4_3"],
                },
                "Dimensions": {
                    "type": "object",
                    "properties": {
                        "width": {"$ref": "#/components/schemas/Dimension"},
                        "height": {"$ref": "#/components/schemas/Dimension"},
                    },
                    "required": ["width", "height"],
                },
                "Dimension": {"type": "integer", "minimum": 1},
            }
        },
    }
