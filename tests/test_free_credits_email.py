from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import IntegrityError, transaction

from app_users import models as app_users_models
from app_users.models import AppUser, canonicalize_email


@pytest.fixture
def firebase_auth_enabled():
    # the code reads daras_ai_v2.settings, not django.conf.settings
    with mock.patch.object(app_users_models.settings, "ENABLE_FIREBASE_AUTH", True):
        yield


def _mk(email: str, uid: str | None = None):
    return AppUser.objects.create(
        uid=uid or f"uid-{email}", email=email, balance=0, is_anonymous=False
    )


def test_canonicalize_email():
    assert canonicalize_email(None) is None
    assert canonicalize_email("") == ""
    assert canonicalize_email("D.Ra.Fc27+x@GoogleMail.com") == "drafc27@gmail.com"
    assert canonicalize_email("d.r.a.f.c@gmail.com") == "drafc@gmail.com"
    # dots and plus tags are significant elsewhere; only case is folded
    assert canonicalize_email("J.Doe+x@Hotmail.com") == "j.doe+x@hotmail.com"


@pytest.mark.django_db
def test_find_same_inbox_matches_gmail_aliases_of_canonical_row():
    user = _mk("drafc27super@gmail.com")
    for alias in (
        "drafc27super@gmail.com",
        "d.ra.fc.2.7su.p.e.r@gmail.com",
        "drafc27.su.p.er@googlemail.com",
        "DRAFC27SUPER@GoogleMail.com",
        "drafc27super+promo@gmail.com",
    ):
        assert AppUser.objects.find_same_inbox(alias) == user, alias
    # genuinely different inboxes
    assert AppUser.objects.find_same_inbox("drafc27supers@gmail.com") is None
    assert AppUser.objects.find_same_inbox("rafc27super@gmail.com") is None
    assert AppUser.objects.find_same_inbox(None) is None


@pytest.mark.django_db
def test_find_same_inbox_matches_legacy_row_by_exact_email_only():
    # rows created before canonicalization keep their dotted spelling: they
    # match the exact address as entered, but not other permutations
    user = _mk("d.ra.fc.2.7su.p.e.r@gmail.com")
    assert AppUser.objects.find_same_inbox("d.ra.fc.2.7su.p.e.r@gmail.com") == user
    assert AppUser.objects.find_same_inbox("drafc27super@gmail.com") is None


@pytest.mark.django_db
def test_find_same_inbox_does_not_dot_normalize_other_domains():
    user = _mk("j.doe@hotmail.com")
    assert AppUser.objects.find_same_inbox("j.doe@hotmail.com") == user
    assert AppUser.objects.find_same_inbox("jdoe@hotmail.com") is None


def _firebase_user(uid: str, email: str, *, email_verified: bool = True):
    return SimpleNamespace(
        uid=uid,
        email=email,
        email_verified=email_verified,
        disabled=False,
        display_name="",
        phone_number=None,
        photo_url=None,
        provider_data=[SimpleNamespace(provider_id="password")],
        user_metadata=SimpleNamespace(creation_timestamp=1_700_000_000_000),
    )


@pytest.mark.django_db
def test_get_or_create_from_uid_resolves_gmail_alias_to_existing_user(
    firebase_auth_enabled,
):
    existing = _mk("drafc27super@gmail.com", uid="uid-original")
    with mock.patch(
        "app_users.models.auth.get_user",
        return_value=_firebase_user("uid-alias", "d.r.a.f.c.27.super@googlemail.com"),
    ):
        user, created = AppUser.objects.get_or_create_from_uid("uid-alias")
    assert user == existing
    assert not created
    assert AppUser.objects.count() == 1


@pytest.mark.django_db
def test_get_or_create_from_uid_stores_canonical_email_for_new_user(
    firebase_auth_enabled,
):
    with (
        mock.patch(
            "app_users.models.auth.get_user",
            return_value=_firebase_user("uid-new", "New.Person@googlemail.com"),
        ),
        mock.patch(
            "app_users.models.Handle.create_default_for_workspace", return_value=None
        ),
    ):
        user, created = AppUser.objects.get_or_create_from_uid("uid-new")
    assert created
    assert user.email == "newperson@gmail.com"
    assert user.balance == app_users_models.settings.VERIFIED_EMAIL_USER_FREE_CREDITS


@pytest.mark.django_db
def test_get_or_create_from_uid_phone_only_user_has_no_email(firebase_auth_enabled):
    _mk("someone@gmail.com", uid="uid-someone")
    phone_user = _firebase_user("uid-phone", None)
    phone_user.phone_number = "+919999999999"
    phone_user.provider_data = [SimpleNamespace(provider_id="phone")]
    with (
        mock.patch("app_users.models.auth.get_user", return_value=phone_user),
        mock.patch(
            "app_users.models.Handle.create_default_for_workspace", return_value=None
        ),
    ):
        user, created = AppUser.objects.get_or_create_from_uid("uid-phone")
    assert created
    assert user.uid == "uid-phone"
    assert user.email is None
    assert AppUser.objects.count() == 2


@pytest.mark.django_db
def test_unverified_email_never_resolves_to_another_uid(firebase_auth_enabled):
    # an unverified sign-up for a free inbox gets its own row and no free credits
    with (
        mock.patch(
            "app_users.models.auth.get_user",
            return_value=_firebase_user(
                "uid-unverified", "someone@gmail.com", email_verified=False
            ),
        ),
        mock.patch(
            "app_users.models.Handle.create_default_for_workspace", return_value=None
        ),
    ):
        user, created = AppUser.objects.get_or_create_from_uid("uid-unverified")
    assert created
    assert user.uid == "uid-unverified"
    assert user.balance == 0

    # ...and is never handed an existing account, even for an exact alias
    existing = _mk("drafc27super@gmail.com", uid="uid-original")
    with mock.patch(
        "app_users.models.auth.get_user",
        return_value=_firebase_user(
            "uid-attacker", "d.r.a.f.c.27.super+x@gmail.com", email_verified=False
        ),
    ):
        # no resolution → tries to create a row with the same canonical email
        # → unique constraint. Never returns `existing`.
        with pytest.raises(IntegrityError), transaction.atomic():
            AppUser.objects.get_or_create_from_uid("uid-attacker")
    assert AppUser.objects.get(uid="uid-original") == existing
    assert not AppUser.objects.filter(uid="uid-attacker").exists()
