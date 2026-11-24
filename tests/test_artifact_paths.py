from starlette.routing import Route

from server import app
from workspaces.artifacts import RESERVED_FOLDER_NAMES


def test_reserved_folder_names_cover_workflow_tab_routes():
    """
    Workflow tab routes such as /{page_slug}/api/ match before /<handle>/<path>, so their first
    fixed segment can't be used as a folder name in workspace file addresses.
    """
    claimed = set()
    for route in app.routes:
        if not isinstance(route, Route) or not route.path.startswith("/{page_slug}/"):
            continue
        literal_segments = [
            segment
            for segment in route.path.strip("/").split("/")[1:]
            if segment and "{" not in segment
        ]
        if literal_segments:
            claimed.add(literal_segments[0])
    assert claimed
    assert claimed <= set(RESERVED_FOLDER_NAMES)
