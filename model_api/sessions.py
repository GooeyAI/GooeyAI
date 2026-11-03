"""
Groups Model API runs by the client session they came from (OpenCode sends
`x-session-id`), so /history/ lists a session once, with its totals.
"""

from django.db import connection, transaction
from django.db.models import Count, FloatField, IntegerField, Max, Min, Sum
from django.db.models.fields.json import KT
from django.db.models.functions import Cast

from app_users.models import AppUser
from bots.models import MessageThread, SavedRun
from workspaces.models import Workspace

# user agent product names, as the clients write themselves
CLIENT_NAMES = {"opencode": "OpenCode"}

# A session's thread is found by a key kept after its title: Model API threads
# never go through the title generators that rename Agent threads.
SESSION_KEY_DELIMITER = "\nmodel_api_session:"


def add_to_session(
    run: SavedRun, workspace: Workspace, user: AppUser, session_id: str
) -> MessageThread:
    """
    Add a Model API run to its client session's thread. Session ids come from
    the client, so a thread is scoped to the workspace and the key's user:
    nobody else's calls can join it. Callbacks can arrive out of order, so the
    thread's first and last runs go by when each call started.
    """
    key_suffix = f"{SESSION_KEY_DELIMITER}{workspace.id}:{user.id}:{session_id}"
    with transaction.atomic():
        # a session's first calls can arrive together: one creates the thread
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [key_suffix])
        thread = (
            MessageThread.objects.select_related("first_run", "last_run")
            # start from the workspace's runs, which are indexed; titles aren't
            .filter(
                last_run__workspace=workspace,
                last_run__workflow=run.workflow,
                title__endswith=key_suffix,
            )
            .first()
        ) or MessageThread.objects.create(
            title=session_title(run.state.get("user_agent")) + key_suffix
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


def display_title(thread: MessageThread) -> str:
    """The thread's title without its session key."""
    return thread.title.split(SESSION_KEY_DELIMITER)[0]


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
