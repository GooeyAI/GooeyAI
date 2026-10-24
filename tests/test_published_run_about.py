from importlib import import_module
from types import SimpleNamespace

import pytest

import gooey_gui as gui
from bots.models import PublishedRun, Workflow
from cms.models import SDG
from gooey_gui.core.renderer import NestingCtx, RenderTreeNode
from daras_ai_v2.loom_video_widget import youtube_embed_url
from recipes.VideoBots_v2 import VideoBotsPageV2
from widgets.about_marketing import (
    DEFAULT_MORE_INFO_TEXT,
    DEFAULT_STATS_TITLE,
    about_media,
    about_more_info,
    about_sdgs,
    about_stats,
)

DEFAULT_SDGS = [
    SDG(**sdg) for sdg in import_module("cms.migrations.0002_sdg_publishedrunstat").SDGS
]


def test_the_seed_covers_all_seventeen_goals_once():
    assert [s.number for s in DEFAULT_SDGS] == list(range(1, 18))
    assert DEFAULT_SDGS[0].name == "No Poverty"
    assert DEFAULT_SDGS[-1].name == "Partnerships for the Goals"
    assert all(s.name and s.photo_url.endswith(".png") for s in DEFAULT_SDGS)


def test_sdg_un_url_is_derived_from_the_number():
    assert SDG(number=1).un_url == "https://sdgs.un.org/goals/goal1"
    assert SDG(number=17).un_url == "https://sdgs.un.org/goals/goal17"


def make_pr(**kwargs):
    """A published run with every marketing field empty, overridden per test."""
    defaults = dict(
        photo_url="",
        banner_url="",
        video_url="",
        headline="",
        more_info_url="",
        more_info_text="",
        sdgs=sdgs_of(),
        stats_title="",
    )
    return SimpleNamespace(**(defaults | kwargs))


def sdgs_of(*numbers):
    """The run's `sdgs` manager, stubbed with unsaved seed rows."""
    return rows_manager([s for s in DEFAULT_SDGS if s.number in numbers])


def rows_manager(rows):
    """A related manager stub: the About helpers read rows through `all` or `order_by`."""
    return SimpleNamespace(all=lambda: rows, order_by=lambda *fields: rows)


@pytest.mark.parametrize(
    "fields, expected_kind, expected_url",
    [
        (dict(video_url="v", banner_url="b", photo_url="p"), "video", "v"),
        (dict(banner_url="b", photo_url="p"), "banner", "b"),
        (dict(photo_url="p"), "photo", "p"),
    ],
)
def test_media_precedence(fields, expected_kind, expected_url):
    media = about_media(make_pr(**fields), workflow=0)
    assert (media.kind, media.url) == (expected_kind, expected_url)


def test_a_youtube_video_url_becomes_an_iframe_embed():
    media = about_media(
        make_pr(video_url="https://www.youtube.com/watch?v=a0cBLQndN8s&list=PLx"),
        workflow=0,
    )
    assert (media.kind, media.url) == (
        "embed",
        "https://www.youtube.com/embed/a0cBLQndN8s",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123&t=42s",
        "https://youtu.be/abc123?si=x",
        "https://m.youtube.com/watch?v=abc123",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/embed/abc123",
    ],
)
def test_youtube_embed_url_accepts_every_link_shape(url):
    assert youtube_embed_url(url) == "https://www.youtube.com/embed/abc123"


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example.com/clip.mp4",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/@gooeyai",
        "https://youtu.be/",
    ],
)
def test_youtube_embed_url_rejects_anything_else(url):
    assert youtube_embed_url(url) is None


def test_no_media_at_all_leaves_the_slot_empty():
    assert about_media(make_pr(), workflow=0) is None


def test_sdg_tiles_carry_the_un_icon_and_link():
    tiles = about_sdgs(make_pr(sdgs=sdgs_of(1, 13)))
    assert [t.number for t in tiles] == [1, 13]
    assert tiles[0].title == "No Poverty"
    assert tiles[1].href == "https://sdgs.un.org/goals/goal13"
    assert tiles[1].photo_url == DEFAULT_SDGS[12].photo_url


def test_the_stat_rows_are_the_switch():
    """No separate toggle: adding a row shows the group, removing the last one hides it."""
    pr = make_pr()
    pr.stats = rows_manager([])
    assert about_stats(pr) is None

    pr.stats = rows_manager([SimpleNamespace(value="1800+", label="Farmers supported")])
    stats = about_stats(pr)
    assert stats.title == DEFAULT_STATS_TITLE
    assert [(c.value, c.label) for c in stats.cards] == [("1800+", "Farmers supported")]


def test_more_info_needs_a_url_and_defaults_its_label():
    assert about_more_info(make_pr(more_info_text="Read the report")) is None
    link = about_more_info(make_pr(more_info_url="/x"))
    assert (link.href, link.text) == ("/x", DEFAULT_MORE_INFO_TEXT)
    link = about_more_info(
        make_pr(more_info_url="/x", more_info_text="Read the report")
    )
    assert link.text == "Read the report"


def test_a_fully_dressed_about_page_serialises(monkeypatch):
    """Every marketing field set, rendered through the real component call - catches prop
    shape and pydantic validation that the per-method tests cannot."""
    page = object.__new__(VideoBotsPageV2)
    pr = make_pr(
        headline="Transforming Smallholder Farming",
        banner_url="https://cdn/banner.jpg",
        more_info_url="https://example.org/case-study",
        more_info_text="View case study",
        sdgs=sdgs_of(1, 13),
        stats_title="",
    )
    pr.workspace_id = None
    pr.notes = "An agri-advisor chatbot."
    pr.run_count = 0
    pr.tags = SimpleNamespace(all=list)
    pr.stats = rows_manager(
        [
            SimpleNamespace(value="1800+", label="Farmers supported"),
            SimpleNamespace(value="17,000", label="User messages"),
        ]
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "current_pr", property(lambda self: pr), raising=False
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "_about_meta_groups", lambda self: [], raising=False
    )
    monkeypatch.setattr(
        VideoBotsPageV2,
        "_workflow_identity",
        lambda self: SimpleNamespace(
            name="Farmer.AI", photo_url=None, circle_photo=False
        ),
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "current_app_url", lambda self, tab=None: "/agent/"
    )
    monkeypatch.setattr(
        VideoBotsPageV2, "is_logged_in", lambda self: False, raising=False
    )
    page._top_bar_integrations = lambda: []
    page.tab = None
    page.request = SimpleNamespace(user=None)
    gui.session_state.clear()

    root = RenderTreeNode("root")
    with NestingCtx(root):
        page._render_about_content()
    props = root.to_dict()["children"][0]["props"]

    assert props["headline"] == "Transforming Smallholder Farming"
    assert props["media"] == {"kind": "banner", "url": "https://cdn/banner.jpg"}
    assert props["more_info"] == {
        "text": "View case study",
        "href": "https://example.org/case-study",
    }
    assert [s["number"] for s in props["sdgs"]] == [1, 13]
    # blank stats_title falls back rather than rendering an empty heading
    assert props["stats"]["title"] == DEFAULT_STATS_TITLE
    assert [c["value"] for c in props["stats"]["cards"]] == ["1800+", "17,000"]


def test_older_code_can_still_create_published_runs(transactional_db):
    """Code from before the About fields - a server mid-deploy or not yet redeployed -
    leaves their columns out of its INSERT. Without a db_default that fails NOT NULL,
    which broke the Builder's Save as New with "banner_url cannot be null"."""
    about_defaults = dict(
        headline="",
        banner_url="",
        video_url="",
        more_info_url="",
        more_info_text="",
        stats_title="",
        builder_prompts=[],
    )
    # the INSERT the older model's save() sends: every column but these
    older_fields = [
        f
        for f in PublishedRun._meta.local_concrete_fields
        if not f.primary_key and f.name not in about_defaults
    ]
    pr = PublishedRun(workflow=Workflow.VIDEO_BOTS, published_run_id="older-code")
    PublishedRun.objects._insert([pr], fields=older_fields)

    pr = PublishedRun.objects.get(published_run_id="older-code")
    assert {name: getattr(pr, name) for name in about_defaults} == about_defaults
