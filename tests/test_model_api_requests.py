import pytest
from litellm.proxy._types import ProxyException
from litellm.proxy.auth.route_checks import RouteChecks
from starlette.requests import Request

from model_api import billing
from model_api.gooey_auth import (
    INFERENCE_ROUTES,
    RESPONSES_ROUTES,
    is_stored_response_route,
)
from model_api.hooks import make_stateless


@pytest.mark.parametrize(
    "method, path, allowed",
    [
        ("POST", "/v1/chat/completions", True),
        ("POST", "/v1/messages", True),
        ("POST", "/v1beta/models/gemini-2.5-pro:streamGenerateContent", True),
        ("POST", "/v1/responses", True),
        ("POST", "/responses", True),
        # stored responses stay unreachable
        ("GET", "/v1/responses", False),
        ("GET", "/v1/responses/resp_123", False),
        ("DELETE", "/v1/responses/resp_123", False),
        ("POST", "/v1/responses/resp_123/cancel", False),
        ("POST", "/cursor/chat/completions", False),
        # the Proxy's own admin routes
        ("POST", "/key/generate", False),
        ("GET", "/config/yaml", False),
    ],
)
def test_route_allowlist(method, path, allowed):
    request = Request({"type": "http", "method": method, "path": path, "headers": []})
    assert is_allowed(request) is allowed


def is_allowed(request: Request) -> bool:
    """Our stored-response guard, then the Proxy's own allowed_routes check."""
    if is_stored_response_route(request):
        return False
    return any(
        RouteChecks._route_matches_allowed_route(request.url.path, route)
        for route in INFERENCE_ROUTES + RESPONSES_ROUTES
    )


def test_responses_calls_are_never_stored():
    data = {"model": "openai/gpt-4.1-mini", "input": "hi", "store": True}
    make_stateless(data)
    assert data["store"] is False


@pytest.mark.parametrize(
    "fields",
    [
        {"previous_response_id": "resp_123"},
        {"conversation": "conv_123"},
        {"background": True},
        {"input": [{"type": "item_reference", "id": "msg_123"}]},
    ],
)
def test_stateful_responses_requests_are_refused(fields):
    data = {"model": "openai/gpt-4.1-mini", "input": "hi"} | fields
    with pytest.raises(ProxyException) as e:
        make_stateless(data)
    assert e.value.code == "400"


def test_streamed_responses_events_are_counted_from_their_deltas():
    events = [
        FakeEvent({"type": "response.created", "response": {"usage": None}}),
        FakeEvent({"type": "response.output_text.delta", "delta": "Hello "}),
        FakeEvent({"type": "response.output_text.delta", "delta": "there"}),
    ]
    counted = billing.count_streamed_tokens("openai/gpt-4.1-mini", {}, events)
    assert counted == billing.litellm.token_counter(
        model="openai/gpt-4.1-mini", text="Hello there"
    )


def test_streamed_responses_events_prefer_the_reported_count():
    events = [
        FakeEvent({"type": "response.output_text.delta", "delta": "Hello"}),
        FakeEvent(
            {"type": "response.completed", "response": {"usage": {"output_tokens": 9}}}
        ),
    ]
    assert billing.count_streamed_tokens("openai/gpt-4.1-mini", {}, events) == 9


class FakeEvent:
    """A Responses stream event, as LiteLLM yields them: a model with model_dump()."""

    def __init__(self, data: dict):
        self.data = data

    def model_dump(self) -> dict:
        return self.data
