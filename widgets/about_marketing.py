from bots.models import PublishedRun, Workflow
from daras_ai_v2.loom_video_widget import youtube_embed_url
from gooey_gui.types.about_props import (
    AboutBannerMedia,
    AboutEmbedMedia,
    AboutMedia,
    AboutMoreInfo,
    AboutPhotoMedia,
    AboutSDG,
    AboutStat,
    AboutStats,
    AboutVideoMedia,
)

DEFAULT_STATS_TITLE = "Community Engagement"
DEFAULT_MORE_INFO_TEXT = "Case Study"


def about_media(pr: PublishedRun, workflow: Workflow) -> AboutMedia | None:
    """The one slot at the head of About. A video outranks a banner, and the portrait
    About has always drawn is the fallback, so no existing page changes."""
    from widgets.workflow_image import CIRCLE_IMAGE_WORKFLOWS

    if pr.video_url:
        if embed_url := youtube_embed_url(pr.video_url):
            return AboutEmbedMedia(url=embed_url)
        return AboutVideoMedia(url=pr.video_url)
    if pr.banner_url:
        return AboutBannerMedia(url=pr.banner_url)
    if pr.photo_url:
        return AboutPhotoMedia(
            url=pr.photo_url, circle=workflow in CIRCLE_IMAGE_WORKFLOWS
        )
    return None


def about_more_info(pr: PublishedRun) -> AboutMoreInfo | None:
    """The outbound link beside Share. The url is the switch; a blank label falls back
    to "Case Study", the usual target."""
    if not pr.more_info_url:
        return None
    return AboutMoreInfo(
        text=pr.more_info_text or DEFAULT_MORE_INFO_TEXT, href=pr.more_info_url
    )


def about_sdgs(pr: PublishedRun) -> list[AboutSDG]:
    return [
        AboutSDG(
            number=sdg.number, title=sdg.name, photo_url=sdg.photo_url, href=sdg.un_url
        )
        for sdg in pr.sdgs.all()
    ]


def about_stats(pr: PublishedRun) -> AboutStats | None:
    """Hand-authored impact numbers. The rows are the switch: add them and the group
    appears, delete them and it goes."""
    cards = [
        AboutStat(value=s.value, label=s.label)
        for s in pr.stats.order_by("order", "id")
    ]
    if not cards:
        return None
    return AboutStats(title=pr.stats_title or DEFAULT_STATS_TITLE, cards=cards)
