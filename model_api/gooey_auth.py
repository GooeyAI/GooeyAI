__import__("gooeysite.wsgi")  # Note: this must always be at the top

from fastapi import HTTPException, Request
from litellm.proxy._types import ProxyException, UserAPIKeyAuth
from starlette.concurrency import run_in_threadpool

from auth.token_authentication import authenticate_credentials
from gooeysite.bg_db_conn import db_middleware

# The routes a Gooey API key may call. The Proxy checks every request against
# the returned key's allowed_routes (exact or "/"-prefix match), so its admin,
# key-management and UI routes stay closed.
INFERENCE_ROUTES = [
    "/v1/chat/completions",
    "/chat/completions",
    "/v1/messages",
    "/v1beta/models",
    "/v1/models",
    "/models",
]

# The Responses protocol, POST only. Every workspace shares Gooey's provider
# keys, so fetching, deleting or cancelling a stored response by ID stays
# closed, and model_api/hooks.py makes every call stateless (store=false, no
# previous_response_id).
# /cursor/chat/completions takes Cursor's Responses-shaped bodies and bridges
# them to Responses, so the same POST-only, stateless rules apply.
RESPONSES_ROUTES = ["/v1/responses", "/responses", "/cursor/chat/completions"]


async def user_api_key_auth(request: Request, api_key: str) -> UserAPIKeyAuth:
    """
    LiteLLM Proxy `custom_auth`: resolve a Gooey API key to its workspace.

    The Proxy passes the key from `Authorization: Bearer`, `x-api-key` or
    `x-goog-api-key`, with any `Bearer ` prefix already stripped.
    """
    if is_stored_response_route(request):
        raise auth_error(403, "This route is not available.")
    if not api_key:
        raise auth_error(401, "Missing API key.")

    try:
        gooey_api_key = await run_in_threadpool(
            db_middleware(authenticate_credentials), api_key
        )
    except HTTPException as e:
        # APIAuth errors carry {"error": msg}
        raise auth_error(e.status_code, e.detail["error"])

    # older keys have no created_by; they act for the workspace owner
    user_id = gooey_api_key.created_by_id or gooey_api_key.workspace.created_by_id
    return UserAPIKeyAuth(
        user_id=str(user_id),
        allowed_routes=INFERENCE_ROUTES + RESPONSES_ROUTES,
        metadata={
            "gooey_workspace_id": gooey_api_key.workspace_id,
            "gooey_user_id": user_id,
            "gooey_api_key_id": gooey_api_key.id,
        },
    )


def is_stored_response_route(request: Request) -> bool:
    """
    allowed_routes match by prefix and ignore the method, so admitting the
    Responses routes would also admit reading, deleting or cancelling a stored
    response by ID. Those, and anything but POST, are refused here.
    """
    path = request.url.path
    for route in RESPONSES_ROUTES:
        if path == route:
            return request.method != "POST"
        if path.startswith(route + "/"):
            return True
    return False


def auth_error(status_code: int, message: str) -> ProxyException:
    return ProxyException(
        message=message, type="auth_error", param=None, code=status_code
    )
