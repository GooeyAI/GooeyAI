from unittest.mock import Mock, patch

import pytest
import requests

from daras_ai_v2 import serp_search
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.serp_search_locations import SerpSearchLocation, SerpSearchType


def test_resolves_google_links_before_building_references():
    original = {
        "organic": [
            {"link": "https://example.com/first", "title": "First"},
            {"link": "https://www.google.com/goto?url=encoded", "title": "Later"},
        ],
        "searchParameters": {"q": "test"},
    }
    resolved = {
        **original,
        "organic": [
            original["organic"][0],
            {"link": "https://example.com/later", "title": "Later"},
        ],
    }
    with (
        patch.object(serp_search, "call_serp_api", return_value=original),
        patch.object(
            serp_search.requests, "post", return_value=Mock(json=lambda: resolved)
        ) as post,
        patch.object(serp_search, "raise_for_status") as check_status,
    ):
        data, links = get_links()

    post.assert_called_once_with(
        "https://google.serper.dev/resolve",
        json=original,
        headers={"X-API-KEY": serp_search.settings.SERPER_API_KEY},
        timeout=60,
    )
    check_status.assert_called_once_with(post.return_value)
    assert data == resolved
    assert [link.url for link in links] == [
        "https://example.com/first",
        "https://example.com/later",
    ]
    assert [link.title for link in links] == ["First", "Later"]


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"organic": [{"link": "https://example.com/article"}]},
        {"organic": [{"link": "https://google.com.example.com/goto?url=encoded"}]},
        {"organic": [{"link": "https://www.google.com/maps"}]},
    ],
)
def test_direct_or_empty_results_do_not_call_resolver(data):
    with (
        patch.object(serp_search, "call_serp_api", return_value=data),
        patch.object(serp_search.requests, "post") as post,
    ):
        result, _ = get_links()
    assert result == data
    post.assert_not_called()


def test_incomplete_resolution_is_not_used_for_retrieval():
    data = {"organic": [{"link": "https://google.com/goto?url=encoded"}]}
    with (
        patch.object(serp_search, "call_serp_api", return_value=data),
        patch.object(
            serp_search.requests,
            "post",
            return_value=Mock(json=lambda: {**data, "retryAfter": 5}),
        ),
        patch.object(serp_search, "raise_for_status"),
        pytest.raises(UserError, match="retry after 5 seconds"),
    ):
        get_links()


def test_resolver_http_errors_propagate():
    data = {"organic": [{"link": "https://www.google.com/goto?url=encoded"}]}
    with (
        patch.object(serp_search, "call_serp_api", return_value=data),
        patch.object(serp_search.requests, "post"),
        patch.object(
            serp_search, "raise_for_status", side_effect=requests.HTTPError("503")
        ),
        pytest.raises(requests.HTTPError, match="503"),
    ):
        get_links()


def get_links():
    return serp_search.get_links_from_serp_api(
        "test",
        search_type=SerpSearchType.SEARCH,
        search_location=SerpSearchLocation.UNITED_STATES,
    )
