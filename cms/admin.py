from django.contrib import admin

from cms.models import SDG, NewsItem
from gooeysite.admin import GooeyModelAdmin


@admin.register(NewsItem)
class NewsItemAdmin(GooeyModelAdmin):
    list_display = ["publish_date", "headline", "tag"]
    list_filter = ["tag"]
    search_fields = ["headline", "tag"]
    date_hierarchy = "publish_date"
    fields = ["publish_date", "headline", "tag", "photo_url", "url"]


@admin.register(SDG)
class SDGAdmin(GooeyModelAdmin):
    list_display = ["number", "name", "icon_url", "updated_at"]
    list_display_links = ["number", "name"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]
