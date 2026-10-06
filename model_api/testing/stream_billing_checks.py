"""
Live checks that every way a stream can end is charged exactly once, run in
the model-api container against the mock upstream (not collected by pytest):

    uvicorn model_api.testing.mock_upstream:app --port 9999 &
    ANTHROPIC_API_KEY=mock litellm --config model_api/proxy_config.mock.yaml \
        --port 8091 --telemetry False &
    GOOEY_API_KEY=... python model_api/testing/stream_billing_checks.py

Charges real (local) credits at gpt-4.1-mini and claude-sonnet-4-5 prices:
about 1 credit per case.
"""

__import__("gooeysite.wsgi")  # Note: this must always be at the top

import os
import time

import httpx
from django.utils import timezone

from app_users.models import AppUserTransaction
from model_api.models import ModelApiCall

PROXY_URL = "http://localhost:8091"
MOCK_URL = "http://localhost:9999"


def main():
    api_key = os.environ["GOOEY_API_KEY"]

    call, upstream, _ = run_case(api_key, "chunks=10")
    assert call.settled_by == "success", call.settled_by
    assert upstream["outcome"] == "completed", upstream
    assert call.usage["completion_tokens"] > 0, call.usage
    report("completed stream", call, upstream)

    call, upstream, closed_at = run_case(api_key, "chunks=40 interval=0.25", read=5)
    assert call.settled_by == "incomplete_stream", call.settled_by
    assert_hung_up_promptly(upstream, closed_at)
    assert 0 < call.usage["completion_tokens"] < 40, call.usage
    report("client aborts mid-stream", call, upstream)

    call, upstream, closed_at = run_case(api_key, "first_delay=5", timeout=1.5)
    assert_hung_up_promptly(upstream, closed_at)
    assert call.usage["completion_tokens"] == 0, call.usage
    report("client aborts before the first chunk", call, upstream)

    # 5 content chunks + the finish chunk, then the usage chunk 5s later
    call, upstream, closed_at = run_case(
        api_key, "chunks=5 usage_delay=5", read=6, include_usage=True
    )
    assert_hung_up_promptly(upstream, closed_at)
    assert call.usage["completion_tokens"] > 0, call.usage
    report("client aborts before the usage chunk", call, upstream)

    call, upstream, _ = run_case(api_key, "chunks=20 fail_after=3")
    assert upstream["outcome"] == "failed", upstream
    report("upstream drops mid-stream", call, upstream)

    # the stateless Responses protocol
    call, upstream, _ = run_case(api_key, "chunks=10", route="responses")
    assert upstream["outcome"] == "completed", upstream
    assert call.usage["completion_tokens"] > 0, call.usage
    report("responses: completed stream", call, upstream)

    call, upstream, closed_at = run_case(
        api_key, "chunks=40 interval=0.25", route="responses", read=8
    )
    assert_hung_up_promptly(upstream, closed_at)
    assert 0 < call.usage["completion_tokens"] < 80, call.usage
    report("responses: client aborts mid-stream", call, upstream)

    # Claude, through the Anthropic Messages route and through Chat Completions.
    # Its streams close like any other: the read is always in flight when the
    # client leaves, so cancelling it drops the upstream connection.
    for route in ("messages", "chat"):
        call, upstream, _ = run_case(
            api_key, "chunks=10", model="claude-sonnet-4-5", route=route
        )
        assert upstream["outcome"] == "completed", upstream
        assert call.usage["completion_tokens"] > 0, call.usage
        report(f"claude via {route}: completed stream", call, upstream)

        call, upstream, closed_at = run_case(
            api_key,
            "chunks=40 interval=0.25",
            model="claude-sonnet-4-5",
            route=route,
            read=8,
        )
        assert_hung_up_promptly(upstream, closed_at)
        assert 0 < call.usage["completion_tokens"] < 80, call.usage
        report(f"claude via {route}: client aborts mid-stream", call, upstream)

    print("\nall stream billing checks passed")


def run_case(
    api_key: str,
    controls: str,
    *,
    model: str = "gpt-4.1-mini",
    route: str = "chat",
    read: int | None = None,
    timeout: float = 60,
    include_usage: bool = False,
) -> tuple[ModelApiCall, dict, float]:
    """Stream one request, stopping after `read` data lines (or on timeout)."""
    httpx.delete(f"{MOCK_URL}/events")
    started = timezone.now()
    body = {
        "model": model,
        "stream": True,
        "messages": [{"role": "user", "content": controls}],
    }
    if include_usage:
        body["stream_options"] = {"include_usage": True}
    if route == "responses":
        path = "/v1/responses"
        headers = {"Authorization": f"Bearer {api_key}"}
        body["input"] = body.pop("messages")[0]["content"]
    elif route == "messages":
        path = "/v1/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        body["max_tokens"] = 500
    else:
        path = "/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}

    lines_read = 0
    try:
        with httpx.stream(
            "POST", f"{PROXY_URL}{path}", json=body, headers=headers, timeout=timeout
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data:"):
                    lines_read += 1
                if read is not None and lines_read >= read:
                    break
    except httpx.TimeoutException:
        pass
    closed_at = time.time()

    call = wait_for_settlement(started)
    upstream = wait_for_upstream_end()
    return call, upstream, closed_at


def wait_for_settlement(started) -> ModelApiCall:
    for _ in range(40):
        calls = ModelApiCall.objects.filter(created_at__gte=started)
        call = calls.first()
        if call and call.status != ModelApiCall.Status.RESERVED:
            assert calls.count() == 1, calls.count()
            assert call.status == ModelApiCall.Status.SETTLED, call
            assert call.charged_credits >= 1, call.charged_credits
            assert (
                AppUserTransaction.objects.filter(invoice_id=call.invoice_id).count()
                == 1
            )
            return call
        time.sleep(0.25)
    raise AssertionError(f"no call settled since {started}: {calls.first()}")


def wait_for_upstream_end() -> dict:
    for _ in range(40):
        events = httpx.get(f"{MOCK_URL}/events").json()
        if events and "ended" in events[-1]:
            return events[-1]
        time.sleep(0.25)
    raise AssertionError(f"upstream never ended: {events}")


def assert_hung_up_promptly(upstream: dict, closed_at: float):
    assert upstream["outcome"] == "caller_hung_up", upstream
    lag = upstream["ended"] - closed_at
    assert lag < 2, f"upstream kept streaming {lag:.1f}s after the client left"


def report(name: str, call: ModelApiCall, upstream: dict):
    print(
        f"ok  {name}: {call.charged_credits} credit(s), settled by {call.settled_by}, "
        f"usage {call.usage}, upstream {upstream['outcome']} after {upstream['sent']} chunks"
    )


if __name__ == "__main__":
    main()
