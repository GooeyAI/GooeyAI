import pytest
import yarl
from starlette.testclient import TestClient

from bots.models import PublishedRun, SavedRun
from bots.models.workflow import WorkflowAccessLevel
from recipes.VideoBots_v2 import VideoBotsPageV2
from server import app

client = TestClient(app)

# the client state a press of the title menu's Delete > confirm posts
CONFIRM_DELETE = {"--delete-run-modal": True, "--delete-run-modal:confirm": True}


@pytest.fixture
def root(transactional_db) -> PublishedRun:
    # before force_authentication, which renames the default workspace's owner
    return VideoBotsPageV2.get_root_pr()


def test_logged_out_post_cannot_delete_root(root):
    """Deleting needs permission, whatever state the client posts."""
    client.post(
        _path(VideoBotsPageV2.app_url()),
        json={"state": CONFIRM_DELETE},
        follow_redirects=False,
    )

    assert PublishedRun.objects.filter(id=root.id).exists()


def test_repeated_delete_on_run_url_keeps_root(root, force_authentication):
    """A run url resolves to root once its workflow is gone, so a second confirm hit it."""
    user = force_authentication
    workspace, _ = user.get_or_create_personal_workspace()
    pr = VideoBotsPageV2.create_published_run(
        published_run_id="my-workflow",
        saved_run=SavedRun.objects.create(
            workflow=VideoBotsPageV2.workflow, uid=user.uid, run_id="my-workflow-sr"
        ),
        user=user,
        workspace=workspace,
        title="My workflow",
        notes="",
        public_access=WorkflowAccessLevel.VIEW_ONLY,
    )
    run = SavedRun.objects.create(
        workflow=VideoBotsPageV2.workflow,
        uid=user.uid,
        run_id="my-workflow-run",
        workspace=workspace,
        parent_version=pr.versions.latest(),
    )
    url = _path(VideoBotsPageV2.app_url(run_id=run.run_id, uid=run.uid))

    client.post(url, json={"state": CONFIRM_DELETE}, follow_redirects=False)
    assert not PublishedRun.objects.filter(id=pr.id).exists()

    # the same submit again: a double click, or a retry
    client.post(url, json={"state": CONFIRM_DELETE}, follow_redirects=False)
    assert PublishedRun.objects.filter(id=root.id).exists()


def _path(url: str) -> str:
    return str(yarl.URL(url).relative())
