import pytest

from ai_models.models import AIModelCreator, AIModelSpec
from daras_ai_v2.language_model_body import to_llm_body


def test_to_llm_body_strips_internal_keys():
    messages = [
        {"role": "system", "content": "be helpful"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "https://foo/img.png"}},
                {"type": "text", "text": "what is this?"},
            ],
            "run_url": "https://gooey.ai/run/123",
        },
        {
            "role": "assistant",
            "content": "let me check",
            "chunk": "",
            "finish_reason": "tool_calls",
            "metrics": {"thinking_duration_sec": 3},
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": None,
                    "function": {"name": "search", "arguments": None},
                    "label": "Search",
                    "url": "https://gooey.ai/tool/search",
                    "icon": "🔍",
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "42"},
    ]
    assert to_llm_body(messages) == [
        {"role": "system", "content": "be helpful"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "https://foo/img.png"}},
                {"type": "text", "text": "what is this?"},
            ],
        },
        {
            "role": "assistant",
            "content": "let me check",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search", "arguments": ""},
                }
            ],
        },
        {"role": "tool", "content": "42", "tool_call_id": "call_1"},
    ]


def test_to_llm_body_strips_message_extra_content():
    body = to_llm_body(
        [
            {
                "role": "assistant",
                "content": "hi there",
                "run_url": "https://gooey.ai/run/123",
                "extra_content": {
                    "display_content": "hola",
                    "video": ["https://gooey.ai/video.mp4"],
                    "audio": ["https://gooey.ai/audio.mp3"],
                },
            }
        ]
    )
    assert body == [{"role": "assistant", "content": "hi there"}]


def test_to_llm_body_defaults():
    assert to_llm_body([{"content": "hi"}]) == [{"role": "user", "content": "hi"}]
    # assistant msg with tool_calls and no content: content key must be dropped
    body = to_llm_body(
        [{"role": "assistant", "content": None, "tool_calls": [{"id": "x"}]}]
    )
    assert "content" not in body[0]
    assert body[0]["tool_calls"] == [
        {"id": "x", "type": "function", "function": {"name": "", "arguments": ""}}
    ]


@pytest.mark.parametrize(
    "model",
    [None, AIModelSpec(model_id="gpt-4o", creator=AIModelCreator(name="Featured"))],
)
def test_to_llm_body_strips_provider_metadata_by_default(model):
    body = to_llm_body(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "search", "arguments": "{}"},
                        "extra_content": {"google": {"thought_signature": "signature"}},
                    }
                ],
            }
        ],
        model=model,
    )
    assert body[0]["tool_calls"][0] == {
        "id": "call_1",
        "type": "function",
        "function": {"name": "search", "arguments": "{}"},
    }


@pytest.mark.parametrize(
    "model",
    [
        AIModelSpec(creator=AIModelCreator(website_url="https://deepmind.google/")),
        AIModelSpec(
            model_id="google/gemini-4-argon", creator=AIModelCreator(name="Featured")
        ),
        AIModelSpec(model_id="google/gemini-4-argon"),
    ],
    ids=["google-creator", "featured-creator", "no-creator"],
)
def test_to_llm_body_preserves_provider_metadata_when_requested(model):
    body = to_llm_body(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "search", "arguments": "{}"},
                        "extra_content": {"google": {"thought_signature": "signature"}},
                        "label": "Search",
                    }
                ],
            }
        ],
        model=model,
    )
    assert body[0]["tool_calls"][0] == {
        "id": "call_1",
        "type": "function",
        "function": {"name": "search", "arguments": "{}"},
        "extra_content": {"google": {"thought_signature": "signature"}},
    }
