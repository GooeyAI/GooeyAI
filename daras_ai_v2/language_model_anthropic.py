from __future__ import annotations

import json
import typing
from time import time

from django.conf import settings

from ai_models.models import AIModelSpec
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.language_model import (
    CHATML_ROLE_ASSISTANT,
    CHATML_ROLE_USER,
    ConversationEntry,
    ReasoningEffort,
    ResponseFormatType,
    get_entry_text,
    is_llm_chunk_large_enough,
)
from functions.base_llm_tool import BaseLLMTool

if typing.TYPE_CHECKING:
    from anthropic.lib.streaming import MessageStreamManager
    from anthropic.types import Message, Usage

# the original assistant content blocks (incl. signed thinking blocks) are saved here,
# so that tool call loops can replay them to claude unchanged
ANTHROPIC_CONTENT_KEY = "anthropic_content"


def run_anthropic_chat(
    *,
    model: AIModelSpec,
    messages: list[ConversationEntry],
    max_tokens: int,
    temperature: float | None,
    stop: list[str] | None,
    tools: list[BaseLLMTool] | None,
    response_format_type: ResponseFormatType | None,
    reasoning_effort: ReasoningEffort.api_choices | None,
    stream: bool,
    start_chunk_size: int,
    stop_chunk_size: int,
    step_chunk_size: int,
) -> list[ConversationEntry] | typing.Generator[list[ConversationEntry], None, None]:
    import anthropic

    system, anthropic_msgs = to_anthropic_messages(messages)

    kwargs = {}
    if system:
        kwargs["system"] = system

    if model.llm_is_thinking_model:
        # newer claude models reject sampling params & fixed thinking budgets
        kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
        if reasoning_effort:
            re = ReasoningEffort.from_api(reasoning_effort)
            if re == ReasoningEffort.minimal:  # deprecated
                re = ReasoningEffort.low
            kwargs["output_config"] = {"effort": re.name}
        # max_tokens includes the thinking tokens
        max_tokens = max(ReasoningEffort.high.thinking_budget + 1000, max_tokens)
    elif temperature is not None:
        # sampling params were removed from the sdk, but older models still accept them
        kwargs["extra_body"] = {"temperature": temperature}

    if model.llm_max_output_tokens:
        # cap the max tokens at the model's max limit
        max_tokens = min(max_tokens, model.llm_max_output_tokens)

    if tools:
        kwargs["tools"] = [tool.spec_anthropic for tool in tools]

    if stop:
        kwargs["stop_sequences"] = stop

    client = anthropic.Anthropic(
        api_key=model.api_key or settings.ANTHROPIC_API_KEY,
        base_url=model.base_url or None,
    )
    message_stream = client.messages.stream(
        model=model.model_id,
        max_tokens=max_tokens,
        messages=anthropic_msgs,
        # cache everything up to the last block, so that the next turn / tool call reads it back
        cache_control={"type": "ephemeral"},
        **kwargs,
    )
    if stream:
        return _stream_anthropic_chat(
            message_stream,
            model.model_id,
            response_format_type=response_format_type,
            start_chunk_size=start_chunk_size,
            stop_chunk_size=stop_chunk_size,
            step_chunk_size=step_chunk_size,
        )

    # always stream from the api, since large max_tokens can exceed the http timeout
    with message_stream as s:
        message = s.get_final_message()
    record_anthropic_llm_usage(model.model_id, message.usage)
    entry = anthropic_message_to_entry(message, response_format_type)
    entry["content"] = entry.pop("chunk")
    return [entry]


def to_anthropic_messages(
    messages: list[ConversationEntry],
) -> tuple[list[dict], list[dict]]:
    """Convert openai style chat messages into claude's system prompt & messages."""
    system = []
    anthropic_msgs = []

    # thinking blocks are only replayed for the ongoing tool call loop,
    # earlier turns are dropped from the front which claude allows
    last_user_idx = max(
        (i for i, msg in enumerate(messages) if msg.get("role") == CHATML_ROLE_USER),
        default=-1,
    )

    for i, msg in enumerate(messages):
        role = msg.get("role") or CHATML_ROLE_USER
        match role:
            case "system":
                text = get_entry_text(msg)
                if text:
                    system.append({"type": "text", "text": text})
            case "user":
                content = _to_anthropic_user_content(msg)
                if content:
                    anthropic_msgs.append(
                        {"role": CHATML_ROLE_USER, "content": content}
                    )
            case "assistant":
                content = _to_anthropic_assistant_content(
                    msg, replay_thinking=i > last_user_idx
                )
                if content:
                    anthropic_msgs.append(
                        {"role": CHATML_ROLE_ASSISTANT, "content": content}
                    )
            case "tool":
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id") or "",
                    "content": get_entry_text(msg),
                }
                prev = anthropic_msgs[-1] if anthropic_msgs else None
                if (
                    prev
                    and prev["role"] == CHATML_ROLE_USER
                    and isinstance(prev["content"], list)
                    and prev["content"]
                    and prev["content"][-1].get("type") == "tool_result"
                ):
                    # parallel tool results go back together in one user message
                    prev["content"].append(tool_result)
                else:
                    anthropic_msgs.append(
                        {"role": CHATML_ROLE_USER, "content": [tool_result]}
                    )

    return system, anthropic_msgs


def _to_anthropic_user_content(msg: ConversationEntry) -> list[dict]:
    parts = msg.get("content") or ""
    if isinstance(parts, str):
        parts = [{"type": "text", "text": parts}]
    content = []
    for part in parts:
        match part.get("type"):
            case "text":
                if part.get("text"):
                    content.append({"type": "text", "text": part["text"]})
            case "image_url":
                url = (part.get("image_url") or {}).get("url")
                if url:
                    content.append(
                        {"type": "image", "source": {"type": "url", "url": url}}
                    )
    return content


def _to_anthropic_assistant_content(
    msg: ConversationEntry, *, replay_thinking: bool
) -> list[dict]:
    tool_calls = msg.get("tool_calls") or []
    if replay_thinking and tool_calls:
        extra_content = tool_calls[0].get("extra_content") or {}
        if saved := extra_content.get(ANTHROPIC_CONTENT_KEY):
            return saved

    from daras_ai_v2.bots import strip_thinking

    content = []
    # the streamed thinking summary is for display only, claude doesn't need it back
    text = strip_thinking(get_entry_text(msg))
    if text:
        content.append({"type": "text", "text": text})
    for tc in tool_calls:
        function = tc.get("function") or {}
        content.append(
            {
                "type": "tool_use",
                "id": tc.get("id") or "",
                "name": function.get("name") or "",
                "input": json.loads(function.get("arguments") or "{}"),
            }
        )
    return content


def _stream_anthropic_chat(
    message_stream: MessageStreamManager,
    model_id: str,
    *,
    response_format_type: ResponseFormatType | None,
    start_chunk_size: int,
    stop_chunk_size: int,
    step_chunk_size: int,
) -> typing.Generator[list[ConversationEntry], None, None]:
    entry: ConversationEntry = dict(
        role=CHATML_ROLE_ASSISTANT, content="", chunk="", metrics={}
    )
    ret = [entry]
    chunk_size = start_chunk_size
    thinking_started_at = time()

    with message_stream as s:
        for event in s:
            match event.type:
                case "content_block_start" if event.content_block.type == "thinking":
                    thinking_started_at = time()
                    entry["chunk"] += "<think>\n\n"
                case "content_block_stop" if event.content_block.type == "thinking":
                    entry["chunk"] += "\n\n</think>\n\n"
                    entry["metrics"]["thinking_duration_sec"] = round(
                        time() - thinking_started_at
                    )
                case "content_block_stop" if event.content_block.type == "text":
                    # text block has ended, stream the chunk immediately
                    entry["content"] += entry["chunk"]
                    entry["chunk"] = ""
                    yield ret
                case "thinking" | "text":
                    entry["chunk"] += (
                        event.thinking if event.type == "thinking" else event.text
                    )
                    if is_llm_chunk_large_enough(entry, chunk_size):
                        # increase the chunk size, but don't go over the max
                        chunk_size = min(chunk_size + step_chunk_size, stop_chunk_size)
                        # stream the chunk
                        yield ret
        message = s.get_final_message()

    record_anthropic_llm_usage(model_id, message.usage)
    final = anthropic_message_to_entry(message, response_format_type)
    entry["content"] += entry["chunk"]
    entry["chunk"] = ""
    entry["finish_reason"] = final["finish_reason"]
    if final.get("tool_calls"):
        entry["tool_calls"] = final["tool_calls"]
    yield ret


def anthropic_message_to_entry(
    message: Message, response_format_type: ResponseFormatType | None = None
) -> ConversationEntry:
    if message.stop_reason == "refusal":
        explanation = message.stop_details and message.stop_details.explanation
        raise UserError(
            "Claude declined to respond to this request. "
            "Please try a different prompt, or a different model."
            + (f"\n\n{explanation}" if explanation else "")
        )

    text = "".join(block.text for block in message.content if block.type == "text")
    if response_format_type == "json_object":
        text = _strip_json_code_fence(text)

    tool_calls = [
        {
            "id": block.id,
            "type": "function",
            "function": {"name": block.name, "arguments": json.dumps(block.input)},
        }
        for block in message.content
        if block.type == "tool_use"
    ]
    if tool_calls and message.stop_reason == "max_tokens":
        raise UserError(
            "Claude's response got cut off due to hitting the max_tokens limit, and the truncated response contains an incomplete tool call. "
            "Please retry the request with a higher max_tokens value."
        )

    entry: ConversationEntry = dict(
        role=CHATML_ROLE_ASSISTANT,
        chunk=text,
        finish_reason=_finish_reasons.get(message.stop_reason, message.stop_reason),
    )
    if tool_calls:
        tool_calls[0]["extra_content"] = {
            ANTHROPIC_CONTENT_KEY: [
                block.model_dump(mode="json", exclude_none=True)
                for block in message.content
            ]
        }
        entry["tool_calls"] = tool_calls
    return entry


# map claude stop reasons to openai finish reasons
_finish_reasons = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


def _strip_json_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].removesuffix("```").strip()
    return text


def record_anthropic_llm_usage(model_id: str, usage: Usage):
    from usage_costs.cost_utils import get_model_pricing, record_cost_auto
    from usage_costs.models import ModelSku

    prompt_tokens = usage.input_tokens or 0

    # bill cache reads & writes separately only when the model has a price for them, otherwise at the full prompt price
    for sku, quantity in [
        (ModelSku.llm_cached_prompt, usage.cache_read_input_tokens),
        (ModelSku.llm_cache_write, usage.cache_creation_input_tokens),
    ]:
        if not quantity:
            continue
        if get_model_pricing(model_id, sku):
            record_cost_auto(model=model_id, sku=sku, quantity=quantity)
        else:
            prompt_tokens += quantity

    if prompt_tokens:
        record_cost_auto(
            model=model_id, sku=ModelSku.llm_prompt, quantity=prompt_tokens
        )
    if usage.output_tokens:
        record_cost_auto(
            model=model_id, sku=ModelSku.llm_completion, quantity=usage.output_tokens
        )
