from django.db import models
from django.utils import timezone

from bots.custom_fields import CustomURLField


class NewsItem(models.Model):
    headline = models.CharField(max_length=200)
    tag = models.CharField(
        max_length=64,
        help_text='Freeform label, e.g. "Event", "Product", "Case Study".',
    )
    photo_url = CustomURLField(default="", blank=True)
    publish_date = models.DateTimeField(default=timezone.now)
    url = CustomURLField(default="", blank=False, help_text="News item URL.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.headline


class SDG(models.Model):
    """One of the 17 UN Sustainable Development Goals. A row rather than an enum so
    sub-goals, KPIs and indicators can point at it. Seeded by `cms/migrations/0002_sdg_publishedrunstat.py`."""

    number = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=64)
    photo_url = CustomURLField(
        blank=True,
        default="",
        help_text="The UN's transparent inverted icon, drawn on a white tile.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["number"]
        verbose_name = "SDG"
        verbose_name_plural = "SDGs"

    def __str__(self):
        return f"{self.number}. {self.name}"

    @property
    def un_url(self) -> str:
        return f"https://sdgs.un.org/goals/goal{self.number}"


class PublishedRunStat(models.Model):
    """One hand-authored impact number on the About page. Authored rather than counted:
    "1800+ Farmers supported" is marketing copy, not a query result."""

    published_run = models.ForeignKey(
        "bots.PublishedRun", on_delete=models.CASCADE, related_name="stats"
    )
    value = models.CharField(max_length=32, help_text='e.g. "1800+"')
    label = models.CharField(max_length=64, help_text='e.g. "Farmers supported"')
    order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.value} {self.label}"
