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


class ArtifactFileEntry(StrictComponentModel):
    path: str
    name: str
    depth: int = 0
    is_folder: bool = False
    size_label: str = ""
    type_label: str = ""
    # text files small enough to show in the viewer
    content: str | None = None
    download_url: str | None = None


class ArtifactFilesProps(StrictComponentModel):
    _component: ClassVar[Literal["ArtifactFiles"]] = "ArtifactFiles"

    summary: str
    entries: list[ArtifactFileEntry]
    selected: str | None = None


class ArtifactLink(StrictComponentModel):
    label: str
    href: str
    icon_class: str
    is_danger: bool = False


class ArtifactCard(StrictComponentModel):
    title: str
    href: str
    # a scaled-down copy of the page, for the thumbnail
    thumbnail_srcdoc: str | None = None
    meta: str
    # shown when someone else made it
    author_initial: str | None = None
    author_name: str
    menu: list[ArtifactLink]


class ArtifactFilterOption(StrictComponentModel):
    label: str
    href: str
    active: bool = False


class ArtifactGridProps(StrictComponentModel):
    _component: ClassVar[Literal["ArtifactGrid"]] = "ArtifactGrid"

    title: str
    subtitle: str
    create_menu: list[ArtifactLink]
    search_action: str
    search_value: str = ""
    # other filters to keep when searching
    search_hidden: dict[str, str] = {}
    made_by: list[ArtifactFilterOption]
    sort: list[ArtifactFilterOption]
    cards: list[ArtifactCard]
    empty_message: str
