from django.contrib import admin
from django.utils.html import format_html

from bots.admin_links import open_in_new_tab
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
    list_display = ["number", "photo", "name", "view_un_goal", "updated_at"]
    list_display_links = ["number", "name"]
    search_fields = ["name"]
    readonly_fields = ["photo", "view_un_goal", "created_at", "updated_at"]

    @admin.display(description="Photo")
    def photo(self, sdg: SDG):
        if not sdg.photo_url:
            return ""
        return format_html('<img src="{}" style="height: 3rem" alt="">', sdg.photo_url)

    @admin.display(description="UN goal page")
    def view_un_goal(self, sdg: SDG):
        return open_in_new_tab(sdg.un_url, label=sdg.un_url)
