"""
Billing for streams the client abandons, on providers LiteLLM can't price
them for.

On a client disconnect, the Proxy bills the chunks streamed so far through the
success callback. Gemini on Vertex reports usage only when a stream ends, so
on Chat Completions and Anthropic Messages that partial response costs 0, and
on Gemini's own streamGenerateContent route no callback fires at all. For those
streams, the Model API counts what was sent and streamed, and dispatches the
partial response itself.
"""

import json

import litellm
import sentry_sdk
from litellm import ModelResponse, ModelResponseStream, Usage

# providers whose abandoned streams the Proxy can't price on these call types.
# Responses streams are priced by the Proxy itself.
UNPRICED_ON_DISCONNECT = {
    "vertex_ai": ("acompletion", "anthropic_messages", "agenerate_content_stream"),
}

# request fields that hold the prompt, across Chat Completions, Anthropic
# Messages and Gemini
PROMPT_FIELDS = (
    "messages",
    "system",
    "contents",
    "systemInstruction",
    "system_instruction",
    "tools",
)


class StreamedOutput:
    """
    What a stream has sent so far: its text, and the usage the provider
    reported, if any. Takes LiteLLM chunks and raw Anthropic or Gemini SSE.
    """

    def __init__(self):
        self.text_parts: list[str] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._sse_buffer = ""

    def add(self, chunk):
        if isinstance(chunk, ModelResponseStream):
            self.add_model_chunk(chunk)
            return
        if isinstance(chunk, bytes):
            chunk = chunk.decode(errors="ignore")
        if isinstance(chunk, str):
            self.add_sse(chunk)

    def add_model_chunk(self, chunk: ModelResponseStream):
        for choice in chunk.choices:
            delta = choice.delta
            self.text_parts += [
                delta.content or "",
                getattr(delta, "reasoning_content", None) or "",
            ]
            for tool_call in delta.tool_calls or []:
                function = tool_call.function
                self.text_parts += [function.name or "", function.arguments or ""]

    def add_sse(self, text: str):
        self._sse_buffer += text
        *lines, self._sse_buffer = self._sse_buffer.split("\n")
        for line in lines:
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line.removeprefix("data:"))
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                self.add_event(event)

    def add_event(self, event: dict):
        # Anthropic Messages
        delta = event.get("delta") or {}
        for key in ("text", "partial_json", "thinking"):
            self.text_parts.append(delta.get(key) or "")
        usage = event.get("usage") or (event.get("message") or {}).get("usage") or {}
        self.prompt_tokens = max(self.prompt_tokens, usage.get("input_tokens") or 0)
        self.completion_tokens = max(
            self.completion_tokens, usage.get("output_tokens") or 0
        )
        # Gemini
        for candidate in event.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                self.text_parts.append(part.get("text") or "")
                if part.get("functionCall"):
                    self.text_parts.append(json.dumps(part["functionCall"]))
        usage = event.get("usageMetadata") or {}
        self.prompt_tokens = max(self.prompt_tokens, usage.get("promptTokenCount") or 0)
        self.completion_tokens = max(
            self.completion_tokens,
            (usage.get("candidatesTokenCount") or 0)
            + (usage.get("thoughtsTokenCount") or 0),
        )

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


def is_unpriced_on_disconnect(request_data: dict) -> bool:
    logging_obj = request_data.get("litellm_logging_obj")
    provider = request_data.get("model", "").split("/", 1)[0]
    call_types = UNPRICED_ON_DISCONNECT.get(provider) or ()
    return getattr(logging_obj, "call_type", None) in call_types


async def bill_abandoned_stream(request_data: dict, streamed: StreamedOutput):
    """
    Dispatch the success callbacks for a stream the client left, with the
    prompt and the output streamed so far counted, so it's billed like a
    completed one. The Proxy's own disconnect billing then sees a final
    success already dispatched, and doesn't send its zero-cost one.
    """
    try:
        logging_obj = request_data["litellm_logging_obj"]
        model = request_data["model"]
        prompt_tokens = streamed.prompt_tokens or count_prompt_tokens(
            model, request_data
        )
        completion_tokens = streamed.completion_tokens or litellm.token_counter(
            model=model, text=streamed.text
        )
        partial = ModelResponse(
            model=model.split("/", 1)[-1],
            choices=[{"message": {"role": "assistant", "content": streamed.text}}],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )
        await logging_obj.dispatch_success_handlers(
            partial,
            cache_hit=False,
            start_time=None,
            end_time=None,
            prefer_async_handlers=True,
        )
    except Exception as e:
        sentry_sdk.capture_exception(e)


def count_prompt_tokens(model: str, request_data: dict) -> int:
    """
    Tokens in the prompt's text. Images, audio and files aren't counted, so
    this undercounts prompts that carry them.
    """
    texts = []
    for field in PROMPT_FIELDS:
        collect_text(request_data.get(field), texts)
    return litellm.token_counter(model=model, text="\n".join(texts))


def collect_text(value, texts: list[str]):
    if isinstance(value, str):
        texts.append(value)
    elif isinstance(value, list):
        for item in value:
            collect_text(item, texts)
    elif isinstance(value, dict):
        for key, item in value.items():
            # inline media, and the protocol's own labels
            if key not in ("data", "url", "image_url", "file_data", "type", "role"):
                collect_text(item, texts)
