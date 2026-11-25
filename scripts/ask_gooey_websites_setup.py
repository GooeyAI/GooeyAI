"""Lets a deployment's Ask Gooey make and edit websites (artefacts): adds the Bash tool to the
builder agent and a website section to the end of its prompt, keeping the rest of its prompt
and tools. Safe to run again: the section is replaced, the tool added once.

    python manage.py shell < scripts/ask_gooey_websites_setup.py

It changes the builder named by GOOEY_BUILDER_INTEGRATION_ID, or by ASK_GOOEY_INTEGRATION_ID
when set. The section reads the hidden `artifact_page` variable that website pages send.
"""

import os

from bots.models import BotIntegration
from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_app_route_url
from functions.inbuilt_tools import BashLLMTool, GooeyToolkit
from functions.models import FunctionTrigger
from routers.root import tool_page

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


def main():
    integration_id = int(
        os.environ.get("ASK_GOOEY_INTEGRATION_ID")
        or settings.GOOEY_BUILDER_INTEGRATION_ID
    )
    bi = BotIntegration.objects.get(id=integration_id)
    sr = bi.saved_run or bi.published_run.saved_run
    state = sr.state
    # the section is last, so a newer one replaces it from its heading on
    prompt = (state.get("bot_script") or "").split(WEBSITES_HEADING)[0]
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
    print(f"updated Ask Gooey: {bi.published_run.get_app_url()}")


def get_bash_url():
    return get_app_route_url(
        tool_page,
        path_params=dict(
            toolkit_slug=GooeyToolkit.inbuilt.name, tool_slug=BashLLMTool.name
        ),
    )


main()
