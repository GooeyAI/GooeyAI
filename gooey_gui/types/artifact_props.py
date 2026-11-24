from __future__ import annotations

from typing import ClassVar, Literal

from gooey_gui.types import StrictComponentModel


class ArtifactFrameProps(StrictComponentModel):
    _component: ClassVar[Literal["ArtifactFrame"]] = "ArtifactFrame"

    title: str
    # the page's HTML, embedded so it never expires; src is the signed link for larger pages
    srcdoc: str | None = None
    src: str | None = None
    sandbox: str
    device: Literal["desktop", "mobile"] = "desktop"


class ArtifactCard(StrictComponentModel):
    title: str
    href: str
    author: str
    status: str
    status_tone: Literal["live", "draft", "muted"] = "muted"
    updated_at_label: str
    # e.g. "1 proposed version", for people who can make it live
    note: str | None = None


class ArtifactGridProps(StrictComponentModel):
    _component: ClassVar[Literal["ArtifactGrid"]] = "ArtifactGrid"

    workspace_name: str
    cards: list[ArtifactCard]
    empty_message: str
