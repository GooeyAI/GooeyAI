from types import SimpleNamespace

from functions.composio_tools import COMPOSIO_PARAM_GUIDANCE, ComposioLLMTool

DRIVE_NAME_DESCRIPTION = (
    "Name for the file in Google Drive, including extension "
    "(e.g., 'report.pdf', 'image.png')."
)


def test_drive_upload_name_gets_filename_guidance():
    tool = _make_tool(
        "GOOGLEDRIVE_UPLOAD_FROM_URL",
        {
            "name": {"type": "string", "description": DRIVE_NAME_DESCRIPTION},
            "source_url": {"type": "string", "description": "HTTPS URL of the file."},
        },
    )

    properties = ComposioLLMTool(tool, scope=None).spec_parameters["properties"]

    guidance = COMPOSIO_PARAM_GUIDANCE["GOOGLEDRIVE_UPLOAD_FROM_URL"]["name"]
    assert properties["name"]["description"] == f"{DRIVE_NAME_DESCRIPTION} {guidance}"
    assert properties["source_url"]["description"] == "HTTPS URL of the file."
    # the shared composio tool spec must stay untouched
    assert tool.input_parameters["properties"]["name"]["description"] == (
        DRIVE_NAME_DESCRIPTION
    )


def test_tools_without_guidance_are_unchanged():
    properties = {"name": {"type": "string", "description": "Folder name."}}
    tool = _make_tool("GOOGLEDRIVE_CREATE_FOLDER", properties)

    llm_tool = ComposioLLMTool(tool, scope=None)

    assert llm_tool.spec_parameters["properties"] is properties


def test_guidance_for_missing_param_is_skipped():
    tool = _make_tool(
        "GOOGLEDRIVE_UPLOAD_FROM_URL",
        {"source_url": {"type": "string", "description": "HTTPS URL of the file."}},
    )

    properties = ComposioLLMTool(tool, scope=None).spec_parameters["properties"]

    assert properties == {
        "source_url": {"type": "string", "description": "HTTPS URL of the file."}
    }


def _make_tool(slug: str, properties: dict) -> SimpleNamespace:
    return SimpleNamespace(
        slug=slug,
        name=slug,
        description=f"{slug} description",
        input_parameters={"properties": properties, "required": list(properties)},
    )
