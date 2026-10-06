"""
Smoke checks against a running Model API (not collected by pytest):

    GOOEY_API_KEY=... python model_api/smoke.py [base_url]

Makes real Model Provider calls, so it costs a few cents per run.
"""

import json
import os
import sys

import httpx
import openai

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090"
MODEL = "gpt-4.1-mini"
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]
# the Proxy's admin routes, plus reading or deleting stored responses by ID
CLOSED_ROUTES = [
    ("POST", "/key/generate"),
    ("GET", "/key/list"),
    ("POST", "/model/new"),
    ("GET", "/model/info"),
    ("GET", "/config/yaml"),
    ("POST", "/config/update"),
    ("GET", "/spend/logs"),
    ("GET", "/global/spend"),
    ("GET", "/user/info"),
    ("GET", "/"),
    ("GET", "/v1/responses/resp_123"),
    ("DELETE", "/v1/responses/resp_123"),
    ("POST", "/cursor/chat/completions"),
]


def main():
    api_key = os.environ["GOOEY_API_KEY"]
    client = openai.OpenAI(base_url=f"{BASE_URL}/v1", api_key=api_key)

    check_plain_stream(client)
    check_tool_call_round_trip(client)
    check_stateless_responses(client)
    check_rejected(client, api_key)
    check_routes_closed(api_key)
    print("\nall smoke checks passed")


def check_plain_stream(client: openai.OpenAI):
    chunks = list(
        client.chat.completions.create(
            model=MODEL,
            stream=True,
            stream_options={"include_usage": True},
            messages=[{"role": "user", "content": "Say hi in 3 words."}],
        )
    )
    text = "".join(c.choices[0].delta.content or "" for c in chunks if c.choices)
    usage = next((c.usage for c in reversed(chunks) if c.usage), None)
    assert text, "no text streamed"
    assert usage and usage.total_tokens, "no usage chunk"
    print(f"ok  plain stream: {text!r}, {usage.total_tokens} tokens")


def check_tool_call_round_trip(client: openai.OpenAI):
    messages = [
        {"role": "user", "content": "What's the weather in Paris? Use the tool."}
    ]
    calls, finish_reason = {}, None
    for chunk in client.chat.completions.create(
        model=MODEL, stream=True, messages=messages, tools=TOOLS
    ):
        for choice in chunk.choices:
            finish_reason = choice.finish_reason or finish_reason
            for tc in choice.delta.tool_calls or []:
                call = calls.setdefault(
                    tc.index, {"id": "", "name": "", "arguments": ""}
                )
                call["id"] = tc.id or call["id"]
                if tc.function:
                    call["name"] += tc.function.name or ""
                    call["arguments"] += tc.function.arguments or ""
    call = calls[0]
    assert finish_reason == "tool_calls", finish_reason
    assert call["id"].startswith("call_"), call
    print(f"ok  tool call: {call['name']}({call['arguments']}) id={call['id']}")

    messages += [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {"name": call["name"], "arguments": call["arguments"]},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call["id"],
            "content": json.dumps({"temp_c": 18, "sky": "cloudy"}),
        },
    ]
    reply = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
    assert "18" in reply.choices[0].message.content, reply.choices[0].message.content
    print(f"ok  tool result round trip: {reply.choices[0].message.content!r}")


def check_stateless_responses(client: openai.OpenAI):
    response = client.responses.create(model=MODEL, input="Say ok.", store=True)
    assert response.output_text, response
    assert response.store is False, "the Model API must not store responses"
    print(f"ok  responses: {response.output_text!r}, stored={response.store}")

    try:
        client.responses.create(
            model=MODEL, input="hi", previous_response_id=response.id
        )
    except openai.BadRequestError as e:
        print(f"ok  previous_response_id: {e.status_code} {e.message[:80]}")
    else:
        raise AssertionError("previous_response_id was not rejected")


def check_rejected(client: openai.OpenAI, api_key: str):
    messages = [{"role": "user", "content": "hi"}]
    cases = {
        "bad key": dict(
            client=openai.OpenAI(
                base_url=f"{BASE_URL}/v1", api_key="sk-not-a-real-key"
            ),
            model=MODEL,
            statuses=(401, 403),
        ),
        # model resolution answers unknown IDs before the router sees them
        "unknown model": dict(client=client, model="not-a-real-model", statuses=(404,)),
        # the Proxy rejects client-side credentials with a ValueError, so a 500
        "api_base in body": dict(
            client=client,
            model=MODEL,
            extra_body={"api_base": "https://example.com"},
            statuses=(500,),
        ),
    }
    for name, case in cases.items():
        try:
            case["client"].chat.completions.create(
                model=case["model"],
                messages=messages,
                extra_body=case.get("extra_body"),
            )
        except openai.APIStatusError as e:
            assert e.status_code in case["statuses"], (name, e.status_code)
            print(f"ok  {name}: {e.status_code} {e.response.text[:120]}")
        else:
            raise AssertionError(f"{name}: request was not rejected")

    r = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        json={"model": MODEL, "messages": messages},
    )
    assert r.status_code in (401, 403), r.status_code
    print(f"ok  missing key: {r.status_code} {r.text[:120]}")


def check_routes_closed(api_key: str):
    for method, path in CLOSED_ROUTES:
        for label, headers in [
            ("gooey key", {"Authorization": f"Bearer {api_key}"}),
            ("no key", {}),
        ]:
            r = httpx.request(method, f"{BASE_URL}{path}", headers=headers)
            assert r.status_code in (401, 403, 404), (
                method,
                path,
                label,
                r.status_code,
            )
        print(f"ok  {method} {path}: closed")

    # with no master key, the Proxy refuses Admin UI login outright, as a 500
    # ("Master Key not set for Proxy")
    r = httpx.post(f"{BASE_URL}/login", data={"username": "admin", "password": "x"})
    assert r.status_code == 500 and "Master Key not set" in r.text, r.text
    print("ok  POST /login: refused")


if __name__ == "__main__":
    main()
