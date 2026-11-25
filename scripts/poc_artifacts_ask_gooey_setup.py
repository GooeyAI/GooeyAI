"""PoC, local only: sets up a local "Ask Gooey" builder agent with the Bash tool, for trying
artifact edits without the production builder. Prints the integration id.

Create a plain stand-in:

    docker exec -i -e POC_EMAIL=you@example.com artifacts-api sh -c \
        'cd /app && poetry run python manage.py shell < scripts/poc_artifacts_ask_gooey_setup.py'

Or add the website section and the Bash tool to an existing builder, such as a copy of
production's Ask Gooey, keeping the rest of its prompt and tools:

    docker exec -i -e POC_INTEGRATION_ID=2 artifacts-api sh -c \
        'cd /app && poetry run python manage.py shell < scripts/poc_artifacts_ask_gooey_setup.py'

Then start the api / celery containers with GOOEY_BUILDER_INTEGRATION_ID set to the printed id.
"""

import os

from app_users.models import AppUser
from bots.models import BotIntegration, Platform, PublishedRun
from bots.models.workflow import WorkflowAccessLevel
from daras_ai_v2.crypto import get_random_doc_id
from daras_ai_v2.fastapi_tricks import get_app_route_url
from functions.inbuilt_tools import BashLLMTool, GooeyToolkit
from functions.models import FunctionTrigger
from recipes.VideoBots import VideoBotsPage
from routers.root import tool_page

TITLE = "Ask Gooey (local stand-in)"
# the production builder's name and avatar, so the panel looks as it does there
WIDGET_NAME = "Ask Gooey"
PHOTO_URL = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/47e069e2-5b65-11f1-80ef-02420a00016f/gooey-builder-logo-fit.gif"
MODEL = os.environ.get("POC_MODEL", "gpt_5_1")

WEBSITES_HEADING = "## Websites (artefacts)"
WEBSITES_SECTION = f"""\
{WEBSITES_HEADING}
A website is a folder in the workspace files with an index.html; the folder name is its name. \
Use the bash tool to read and write it. When the person is looking at a website (below), \
"the page" and "the title" mean that website: read its index.html first, change only files in \
its folder, keep the page one self-contained HTML file (inline CSS and JS, absolute https:// \
links for media), and write the whole file back. Each change becomes a draft the person can \
publish with Update, so make the change they asked for and nothing else. Describe what changed \
on the page - what it shows, its layout and how it responds - never the code, files or tools. \
Don't link to the files or show diffs: the page already shows the person the new draft.
{{% if artifact_page %}}
The person is looking at {{{{ artifact_page }}}}.
{{% endif %}}
"""

PROMPT = f"""\
You are Ask Gooey, the assistant inside Gooey.AI. You help people build and change their \
workflows and agents, and the websites (artifacts) they make with them.

Workflows and agents: use your workflow tools to look at, change, run and save the workflow \
the person is on. Look things up with your tools instead of asking.

Replies: be brief. If a tool fails, say so in one line and what the person can do.

{WEBSITES_SECTION}"""


def main():
    if os.environ.get("POC_INTEGRATION_ID"):
        add_websites_to_builder(int(os.environ["POC_INTEGRATION_ID"]))
        return
    user, _ = AppUser.objects.get_or_create_from_email(os.environ["POC_EMAIL"])
    workspace, _ = user.get_or_create_personal_workspace()
    bash_url = get_bash_url()
    state = {
        **VideoBotsPage.get_root_pr().saved_run.state,
        "bot_script": PROMPT,
        "selected_model": MODEL,
        "max_tokens": 4000,
        "reasoning_effort": "low",
        # Ask Gooey's replies are read, not heard
        "tts_provider": None,
        "messages": [],
        "input_prompt": "",
        "documents": [],
        "functions": [
            dict(
                trigger=FunctionTrigger.prompt.name,
                url=bash_url,
                label=BashLLMTool.label,
            )
        ],
    }
    pr = ensure_published_run(user, workspace, state)
    # every member who opens an artifact draft chats with it, so it has to be viewable
    pr.public_access = WorkflowAccessLevel.FIND_AND_VIEW
    pr.save(update_fields=["public_access"])

    bi, _ = BotIntegration.objects.update_or_create(
        published_run=pr,
        platform=Platform.WEB,
        defaults=dict(
            name=WIDGET_NAME,
            photo_url=PHOTO_URL,
            saved_run=pr.saved_run,
            workspace=workspace,
            created_by=user,
        ),
    )
    print(f"builder agent: {pr.get_app_url()}")
    print(f"GOOEY_BUILDER_INTEGRATION_ID={bi.id}")


def add_websites_to_builder(integration_id):
    """Adds (or refreshes) the website section and adds the Bash tool to an existing
    builder, once."""
    bi = BotIntegration.objects.get(id=integration_id)
    sr = bi.saved_run or bi.published_run.saved_run
    state = sr.state
    prompt = state.get("bot_script") or ""
    # the section is last, so a newer one replaces it from its heading on
    prompt = prompt.split(WEBSITES_HEADING)[0]
    state["bot_script"] = prompt.rstrip() + "\n\n" + WEBSITES_SECTION
    bash_url = get_bash_url()
    functions = state.get("functions") or []
    if not any(fn.get("url") == bash_url for fn in functions):
        functions.append(
            dict(
                trigger=FunctionTrigger.prompt.name,
                url=bash_url,
                label=BashLLMTool.label,
            )
        )
    state["functions"] = functions
    sr.save(update_fields=["state"])
    print(f"builder agent: {bi.published_run.get_app_url()}")
    print(f"GOOEY_BUILDER_INTEGRATION_ID={bi.id}")


def get_bash_url():
    return get_app_route_url(
        tool_page,
        path_params=dict(
            toolkit_slug=GooeyToolkit.inbuilt.name, tool_slug=BashLLMTool.name
        ),
    )


def ensure_published_run(user, workspace, state):
    pr = PublishedRun.objects.filter(
        workflow=VideoBotsPage.workflow, title=TITLE, workspace=workspace
    ).first()
    if pr:
        pr.saved_run.state = state
        pr.saved_run.save(update_fields=["state"])
        return pr
    sr = VideoBotsPage.get_root_pr().saved_run.clone(
        uid=user.uid, workspace_id=workspace.id
    )
    sr.state = state
    sr.save()
    return PublishedRun.objects.create_with_version(
        workflow=VideoBotsPage.workflow,
        published_run_id=get_random_doc_id(),
        saved_run=sr,
        user=user,
        workspace=workspace,
        title=TITLE,
    )


main()
