import json

from daras_ai_v2.language_model_anthropic import (
    ANTHROPIC_CONTENT_KEY,
    to_anthropic_messages,
)

SAVED_CONTENT = [
    {"type": "thinking", "thinking": "", "signature": "sig"},
    {"type": "tool_use", "id": "call_1", "name": "get_weather", "input": {"q": 1}},
]


def test_system_and_user_messages():
    system, msgs = to_anthropic_messages(
        [
            {"role": "system", "content": "be terse", "tools": [{"name": "x"}]},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "https://x/a.png"}},
                    {"type": "text", "text": "what is this?"},
                ],
            },
        ]
    )
    assert system == [{"type": "text", "text": "be terse"}]
    assert msgs == [
        {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "url", "url": "https://x/a.png"}},
                {"type": "text", "text": "what is this?"},
            ],
        }
    ]


def test_tool_loop_replays_saved_content_and_merges_tool_results():
    _, msgs = to_anthropic_messages(
        [
            {"role": "user", "content": "weather?"},
            _assistant_tool_call_entry(),
            {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
            {"role": "tool", "tool_call_id": "call_2", "content": "rainy"},
        ]
    )
    assert msgs[1] == {"role": "assistant", "content": SAVED_CONTENT}
    assert msgs[2] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "sunny"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "rainy"},
        ],
    }


def test_earlier_turns_drop_thinking():
    _, msgs = to_anthropic_messages(
        [
            {"role": "user", "content": "weather?"},
            _assistant_tool_call_entry(content="<think>hmm</think>\n\nchecking"),
            {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
            {"role": "assistant", "content": "<think>ok</think>\n\nIt's sunny."},
            {"role": "user", "content": "thanks"},
        ]
    )
    assert msgs[1] == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "checking"},
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "get_weather",
                "input": {"q": 1},
            },
        ],
    }
    assert msgs[3] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "It's sunny."}],
    }


def test_empty_assistant_entries_are_skipped():
    _, msgs = to_anthropic_messages(
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": ""}]
    )
    assert msgs == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


def _assistant_tool_call_entry(content: str = "") -> dict:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": json.dumps({"q": 1})},
                "extra_content": {ANTHROPIC_CONTENT_KEY: SAVED_CONTENT},
            }
        ],
    }
