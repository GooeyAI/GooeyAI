__import__("gooeysite.wsgi")  # Note: this must always be at the top

from fastapi import HTTPException, Request
from litellm.proxy._types import ProxyException, UserAPIKeyAuth
from starlette.concurrency import run_in_threadpool

from auth.token_authentication import authenticate_credentials
from gooeysite.bg_db_conn import db_middleware

# The routes a Gooey API key may call. The Proxy checks every request against
# the returned key's allowed_routes (exact or "/"-prefix match), so its admin,
# key-management and UI routes stay closed.
#
# TODO: open the Responses protocol (and /cursor/chat/completions, which
# bridges to it) once it's stateless: POST only, no previous_response_id, and
# store=false. Every workspace shares Gooey's provider keys, so stored response
# IDs would otherwise be readable and deletable across workspaces.
INFERENCE_ROUTES = [
    "/v1/chat/completions",
    "/chat/completions",
    "/v1/messages",
    "/v1beta/models",
    "/v1/models",
    "/models",
]


async def user_api_key_auth(request: Request, api_key: str) -> UserAPIKeyAuth:
    """
    LiteLLM Proxy `custom_auth`: resolve a Gooey API key to its workspace.

    The Proxy passes the key from `Authorization: Bearer`, `x-api-key` or
    `x-goog-api-key`, with any `Bearer ` prefix already stripped.
    """
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
        allowed_routes=INFERENCE_ROUTES,
        metadata={
            "gooey_workspace_id": gooey_api_key.workspace_id,
            "gooey_user_id": user_id,
            "gooey_api_key_id": gooey_api_key.id,
        },
    )


def auth_error(status_code: int, message: str) -> ProxyException:
    return ProxyException(
        message=message, type="auth_error", param=None, code=status_code
    )
