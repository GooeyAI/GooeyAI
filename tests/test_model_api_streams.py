import json
from types import SimpleNamespace

import pytest
from litellm import ModelResponseStream

from model_api.streams import (
    StreamedOutput,
    count_prompt_tokens,
    is_unpriced_on_disconnect,
)


@pytest.mark.parametrize(
    "model, call_type, expected",
    [
        ("vertex_ai/gemini-2.5-flash", "acompletion", True),
        ("vertex_ai/gemini-2.5-flash", "anthropic_messages", True),
        ("vertex_ai/gemini-2.5-flash", "agenerate_content_stream", True),
        # the Proxy prices these itself
        ("vertex_ai/gemini-2.5-flash", "aresponses", False),
        ("openai/gpt-4.1-mini", "acompletion", False),
        ("anthropic/claude-sonnet-4-5", "anthropic_messages", False),
    ],
)
def test_only_streams_the_proxy_cant_price_are_metered(model, call_type, expected):
    request_data = {
        "model": model,
        "litellm_logging_obj": SimpleNamespace(call_type=call_type),
    }
    assert is_unpriced_on_disconnect(request_data) is expected


def test_counts_text_from_model_chunks():
    streamed = StreamedOutput()
    for text in ["Hello ", "there"]:
        streamed.add(
            ModelResponseStream(choices=[{"index": 0, "delta": {"content": text}}])
        )
    assert streamed.text == "Hello there"
    assert (streamed.prompt_tokens, streamed.completion_tokens) == (0, 0)


def test_counts_gemini_sse_split_across_chunks():
    event = {
        "candidates": [{"content": {"parts": [{"text": "one two"}]}}],
        "usageMetadata": {"trafficType": "ON_DEMAND"},
    }
    sse = f"data: {json.dumps(event)}\n\n".encode()
    streamed = StreamedOutput()
    streamed.add(sse[:20])
    streamed.add(sse[20:])
    assert streamed.text == "one two"
    # Vertex reports no counts until the stream ends
    assert streamed.completion_tokens == 0


def test_prefers_the_usage_gemini_reports():
    event = {
        "candidates": [{"content": {"parts": [{"text": "hi"}]}}],
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": 3,
            "thoughtsTokenCount": 40,
        },
    }
    streamed = StreamedOutput()
    streamed.add(f"data: {json.dumps(event)}\n\n".encode())
    assert (streamed.prompt_tokens, streamed.completion_tokens) == (12, 43)


def test_counts_anthropic_sse():
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 0}}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}},
        {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": '{"city"'},
        },
    ]
    streamed = StreamedOutput()
    for event in events:
        streamed.add(f"event: x\ndata: {json.dumps(event)}\n\n".encode())
    assert streamed.text == 'Hi{"city"'


def test_prompt_counts_text_but_not_inline_media():
    text_only = {"messages": [{"role": "user", "content": "Describe this image."}]}
    with_image = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + "A" * 5000},
                    },
                ],
            }
        ]
    }
    model = "vertex_ai/gemini-2.5-flash"
    assert count_prompt_tokens(model, with_image) == count_prompt_tokens(
        model, text_only
    )
