"""
A slow, scriptable upstream for testing the Model API's stream billing. It
speaks OpenAI Chat Completions (/v1/chat/completions) and Anthropic Messages
(/v1/messages). Run it next to a Proxy that uses proxy_config.mock.yaml:

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
    event = new_event()
    if not body.get("stream"):
        event["outcome"] = "completed"
        return JSONResponse(openai_completion(body["model"], controls["chunks"]))

    include_usage = (body.get("stream_options") or {}).get("include_usage")
    frames = OpenAIFrames(body["model"], include_usage)
    return StreamingResponse(
        stream(controls, event, frames), media_type="text/event-stream"
    )


async def messages(request: Request):
    body = await request.json()
    controls = parse_controls(body["messages"])
    event = new_event()
    if not body.get("stream"):
        event["outcome"] = "completed"
        return JSONResponse(anthropic_message(body["model"], controls["chunks"]))

    frames = AnthropicFrames(body["model"])
    return StreamingResponse(
        stream(controls, event, frames), media_type="text/event-stream"
    )


async def stream(controls: dict, event: dict, frames):
    try:
        await asyncio.sleep(controls["first_delay"])
        for frame in frames.start():
            yield frame
        for i in range(controls["chunks"]):
            if controls["fail_after"] is not None and i == controls["fail_after"]:
                event["outcome"] = "failed"
                raise ConnectionAbortedError("mock upstream dropped the connection")
            yield frames.text(f"w{i} ")
            event["sent"] += 1
            await asyncio.sleep(controls["interval"])
        for frame in frames.finish():
            yield frame
        await asyncio.sleep(controls["usage_delay"])
        for frame in frames.end(controls["chunks"]):
            yield frame
        event["outcome"] = "completed"
    except (asyncio.CancelledError, GeneratorExit):
        event["outcome"] = "caller_hung_up"
        raise
    finally:
        event["ended"] = time.time()


class OpenAIFrames:
    def __init__(self, model: str, include_usage: bool):
        self.model = model
        self.include_usage = include_usage

    def start(self):
        return []

    def text(self, text: str) -> str:
        return sse(self.chunk({"content": text}))

    def finish(self):
        return [sse(self.chunk({}, finish_reason="stop"))]

    def end(self, n: int):
        frames = []
        if self.include_usage:
            frames.append(sse(self.chunk(None, usage=openai_usage(n))))
        frames.append("data: [DONE]\n\n")
        return frames

    def chunk(self, delta: dict | None, finish_reason=None, usage=None) -> dict:
        choices = (
            []
            if delta is None
            else [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
        )
        return {
            "id": "chatcmpl-mock",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "choices": choices,
            **({"usage": usage} if usage else {}),
        }


class AnthropicFrames:
    def __init__(self, model: str):
        self.model = model

    def start(self):
        message = {
            "id": "msg_mock",
            "type": "message",
            "role": "assistant",
            "model": self.model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 20, "output_tokens": 1},
        }
        return [
            event_sse("message_start", {"type": "message_start", "message": message}),
            event_sse(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
        ]

    def text(self, text: str) -> str:
        return event_sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        )

    def finish(self):
        return [
            event_sse("content_block_stop", {"type": "content_block_stop", "index": 0})
        ]

    def end(self, n: int):
        return [
            event_sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 2 * n},
                },
            ),
            event_sse("message_stop", {"type": "message_stop"}),
        ]


def new_event() -> dict:
    event = {"id": str(uuid.uuid4()), "started": time.time(), "sent": 0}
    events.append(event)
    return event


def parse_controls(messages: list) -> dict:
    controls = {
        "chunks": 10,
        "interval": 0.05,
        "first_delay": 0.0,
        "fail_after": None,
        "usage_delay": 0.0,
    }
    content = messages[-1]["content"] if messages else ""
    if isinstance(content, list):  # Anthropic content blocks
        content = " ".join(block.get("text", "") for block in content)
    for word in str(content).split():
        key, _, value = word.partition("=")
        if key in controls and value:
            controls[key] = (
                int(value) if key in ("chunks", "fail_after") else float(value)
            )
    return controls


def openai_completion(model: str, n: int) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": words(n)},
                "finish_reason": "stop",
            }
        ],
        "usage": openai_usage(n),
    }


def anthropic_message(model: str, n: int) -> dict:
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": words(n)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 20, "output_tokens": 2 * n},
    }


def openai_usage(n: int) -> dict:
    return {"prompt_tokens": 20, "completion_tokens": 2 * n, "total_tokens": 20 + 2 * n}


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def event_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def list_events(request: Request):
    if request.method == "DELETE":
        events.clear()
    return JSONResponse(events)


app = Starlette(
    routes=[
        Route("/v1/chat/completions", chat_completions, methods=["POST"]),
        Route("/v1/messages", messages, methods=["POST"]),
        Route("/events", list_events, methods=["GET", "DELETE"]),
    ]
)
