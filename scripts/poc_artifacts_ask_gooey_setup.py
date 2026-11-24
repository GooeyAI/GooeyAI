"""PoC, local only: creates (or refreshes) a stand-in "Ask Gooey" builder agent with the Bash
tool, for trying artifact edits without the production builder. Prints the integration id.

    docker exec -i -e POC_EMAIL=you@example.com artifacts-api sh -c \
        'cd /app && poetry run python manage.py shell < scripts/poc_artifacts_ask_gooey_setup.py'

Then start the api / celery containers with GOOEY_BUILDER_INTEGRATION_ID set to the printed id.
The production Ask Gooey's prompt lives in its database; this is a plain stand-in.
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

PROMPT = """\
You are Ask Gooey, the assistant inside Gooey.AI. You help people build and change their \
workflows and agents, and the websites (artifacts) they make with them.

Workflows and agents: use your workflow tools to look at, change, run and save the workflow \
the person is on. Look things up with your tools instead of asking.

Websites: a website is a folder in the workspace files with an index.html. Use the bash tool \
to read and write it. When a message starts with "[Editing the page …]", it names the folder \
of the person's draft: read its index.html first, change only files in that folder, keep the \
page one self-contained HTML file (inline CSS and JS, absolute https:// links for media), and \
write the whole file back. Make the change the person asked for and nothing else.

Replies: be brief. Describe what changed on the page - what it shows, its layout and how it \
responds - never the code, files or tools behind it. If a tool fails, say so in one line and \
what the person can do.
"""


def main():
    user, _ = AppUser.objects.get_or_create_from_email(os.environ["POC_EMAIL"])
    workspace, _ = user.get_or_create_personal_workspace()
    bash_url = get_app_route_url(
        tool_page,
        path_params=dict(
            toolkit_slug=GooeyToolkit.inbuilt.name, tool_slug=BashLLMTool.name
        ),
    )
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
