from __future__ import annotations

import pydantic


class WorkspaceFileEntry(pydantic.BaseModel):
    # path relative to the workspace files root, e.g. "data/report.csv"
    path: str
    # generates a presigned url on click and redirects to it
    href: str
    size_label: str
    updated_at_label: str


class WorkspaceFileBrowserProps(pydantic.BaseModel):
    _component: str = "WorkspaceFileBrowser"

    description: str
    entries: list[WorkspaceFileEntry]
    next_page_url: str | None = None
