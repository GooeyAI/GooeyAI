"""
A slow, scriptable OpenAI-compatible upstream for testing the Model API's
stream billing. Run it next to a Proxy that uses proxy_config.mock.yaml:

    uvicorn model_api.testing.mock_upstream:app --port 9999

The last user message controls the stream, e.g. "chunks=40 interval=0.25":
  chunks       content chunks to send (default 10)
  interval     seconds between chunks (default 0.05)
  first_delay  seconds before the first chunk (default 0)
  fail_after   drop the connection after this many chunks
  usage_delay  seconds between the last content chunk and the usage chunk

GET /events lists what happened to each request (completed, or the caller
hung up after N chunks); DELETE /events clears it.
"""

import asyncio
import json
import time
import uuid

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

events: list[dict] = []


async def chat_completions(request: Request):
    body = await request.json()
    controls = parse_controls(body["messages"])
    event = {"id": str(uuid.uuid4()), "started": time.time(), "sent": 0}
    events.append(event)

    if not body.get("stream"):
        event["outcome"] = "completed"
        return JSONResponse(completion(body["model"], controls["chunks"]))

    include_usage = (body.get("stream_options") or {}).get("include_usage")
    return StreamingResponse(
        stream(body["model"], controls, include_usage, event),
        media_type="text/event-stream",
    )


async def stream(model: str, controls: dict, include_usage: bool, event: dict):
    try:
        await asyncio.sleep(controls["first_delay"])
        for i in range(controls["chunks"]):
            if controls["fail_after"] is not None and i == controls["fail_after"]:
                event["outcome"] = "failed"
                raise ConnectionAbortedError("mock upstream dropped the connection")
            yield sse(chunk(model, {"content": f"w{i} "}))
            event["sent"] += 1
            await asyncio.sleep(controls["interval"])
        yield sse(chunk(model, {}, finish_reason="stop"))
        await asyncio.sleep(controls["usage_delay"])
        if include_usage:
            yield sse(chunk(model, None, usage=usage(controls["chunks"])))
        yield "data: [DONE]\n\n"
        event["outcome"] = "completed"
    except (asyncio.CancelledError, GeneratorExit):
        event["outcome"] = "caller_hung_up"
        raise
    finally:
        event["ended"] = time.time()


def parse_controls(messages: list) -> dict:
    controls = {
        "chunks": 10,
        "interval": 0.05,
        "first_delay": 0.0,
        "fail_after": None,
        "usage_delay": 0.0,
    }
    text = messages[-1]["content"] if messages else ""
    for word in str(text).split():
        key, _, value = word.partition("=")
        if key in controls and value:
            controls[key] = (
                int(value) if key in ("chunks", "fail_after") else float(value)
            )
    return controls


def chunk(model: str, delta: dict | None, finish_reason=None, usage=None) -> dict:
    choices = (
        []
        if delta is None
        else [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
    )
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
        **({"usage": usage} if usage else {}),
    }


def completion(model: str, n: int) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": " ".join(f"w{i}" for i in range(n)),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": usage(n),
    }


def usage(n: int) -> dict:
    return {"prompt_tokens": 20, "completion_tokens": 2 * n, "total_tokens": 20 + 2 * n}


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def list_events(request: Request):
    if request.method == "DELETE":
        events.clear()
    return JSONResponse(events)


app = Starlette(
    routes=[
        Route("/v1/chat/completions", chat_completions, methods=["POST"]),
        Route("/events", list_events, methods=["GET", "DELETE"]),
    ]
)
