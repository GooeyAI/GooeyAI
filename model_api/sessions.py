"""
Groups Model API runs by the client session they came from (OpenCode sends
`x-session-id`), so /history/ lists a session once, with its totals.
"""

from django.db import transaction
from django.db.models import Count, FloatField, IntegerField, Max, Min, Sum
from django.db.models.fields.json import KT
from django.db.models.functions import Cast

from app_users.models import AppUser
from bots.models import MessageThread, SavedRun
from workspaces.models import Workspace

# user agent product names, as the clients write themselves
CLIENT_NAMES = {"opencode": "OpenCode"}


def add_to_session(
    run: SavedRun, workspace: Workspace, user: AppUser, session_id: str
) -> MessageThread:
    """
    Add a Model API run to its client session's thread. Session ids come from
    the client, so a thread is scoped to the workspace and the key's user:
    nobody else's calls can join it. Callbacks can arrive out of order, so the
    thread's first and last runs go by when each call started.
    """
    with transaction.atomic():
        thread = MessageThread.objects.get_or_create(
            session_key=f"model_api:{workspace.id}:{user.id}:{session_id}",
            defaults=dict(title=session_title(run.state.get("user_agent"))),
        )[0]
        thread = (
            MessageThread.objects.select_for_update(of=("self",))
            .select_related("first_run", "last_run")
            .get(pk=thread.pk)
        )
        run.message_thread = thread
        run.save(update_fields=["message_thread"])
        if not thread.first_run or started_at(run) < started_at(thread.first_run):
            thread.first_run = run
        if not thread.last_run or started_at(run) >= started_at(thread.last_run):
            thread.last_run = run
        thread.save(update_fields=["first_run", "last_run"])
        save_session_totals(thread)
    return thread


def session_title(user_agent: str | None) -> str:
    """`opencode/2.1.2 ...` -> `OpenCode session`."""
    product = (user_agent or "").split("/")[0].split(" ")[0]
    if not product:
        return "Model API session"
    return f"{CLIENT_NAMES.get(product.lower(), product)} session"


def started_at(run: SavedRun) -> float:
    return run.state.get("started_at") or 0


def save_session_totals(thread: MessageThread):
    """
    Store the session's totals on its latest run, the one /history/ lists, so
    the history card needs no queries of its own. Metadata only.
    """
    runs = thread.saved_runs.all()
    totals = runs.aggregate(
        calls=Count("id"),
        credits=Sum("price"),
        prompt_tokens=Sum(Cast(KT("state__prompt_tokens"), IntegerField())),
        completion_tokens=Sum(Cast(KT("state__completion_tokens"), IntegerField())),
        cost_usd=Sum(Cast(KT("state__cost_usd"), FloatField())),
        started_at=Min(Cast(KT("state__started_at"), FloatField())),
        ended_at=Max(Cast(KT("state__ended_at"), FloatField())),
    )
    totals["models"] = sorted(
        {model for model in runs.values_list(KT("state__model"), flat=True) if model}
    )
    last_run = thread.last_run
    last_run.state["session"] = totals
    last_run.save(update_fields=["state"])
