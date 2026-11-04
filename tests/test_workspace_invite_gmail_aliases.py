from unittest import mock

import pytest
from django.core.exceptions import ValidationError

from app_users.models import AppUser
from workspaces.models import Workspace, WorkspaceInvite, WorkspaceRole


def _user(email: str) -> AppUser:
    return AppUser.objects.create(
        uid=f"uid-{email}", email=email, balance=0, is_anonymous=False
    )


def _workspace(owner: AppUser) -> Workspace:
    ws = Workspace(name="Team", created_by=owner)
    ws.create_with_owner()
    return ws


class _Everyone:
    def __contains__(self, item):
        return True


@pytest.fixture(autouse=True)
def _no_celery_and_free_seats():
    # invites normally need a Team plan; admin emails bypass the seat check
    with (
        mock.patch("workspaces.models.settings.ADMIN_EMAILS", _Everyone()),
        mock.patch("workspaces.models.send_invitation_email.delay"),
        mock.patch("workspaces.models.send_added_to_workspace_email.delay"),
    ):
        yield


@pytest.mark.django_db
def test_invite_is_stored_canonical_and_accepted_by_canonical_signup():
    owner = _user("owner@example.com")
    ws = _workspace(owner)
    invite = WorkspaceInvite.objects.create_and_send_invite(
        workspace=ws,
        email="Jane.Doe@googlemail.com",
        current_user=owner,
        defaults=dict(role=WorkspaceRole.MEMBER),
    )
    assert invite.email == "janedoe@gmail.com"
    assert invite.status == WorkspaceInvite.Status.PENDING

    # the invitee signs up later; new users are stored with the canonical email
    jane = _user("janedoe@gmail.com")
    invite.refresh_from_db()
    assert invite.status == WorkspaceInvite.Status.ACCEPTED
    assert ws.memberships.filter(user=jane, deleted__isnull=True).exists()


@pytest.mark.django_db
def test_invite_to_dotted_address_auto_accepts_legacy_dotted_user():
    owner = _user("owner@example.com")
    ws = _workspace(owner)
    jane = _user("jane.doe@gmail.com")  # pre-canonicalization row
    invite = WorkspaceInvite.objects.create_and_send_invite(
        workspace=ws,
        email="jane.doe@gmail.com",
        current_user=owner,
        defaults=dict(role=WorkspaceRole.MEMBER),
    )
    assert invite.email == "janedoe@gmail.com"
    assert invite.status == WorkspaceInvite.Status.ACCEPTED
    assert ws.memberships.filter(user=jane, deleted__isnull=True).exists()


@pytest.mark.django_db
def test_accept_allows_dotted_invitee_for_canonical_invite():
    owner = _user("owner@example.com")
    ws = _workspace(owner)
    invite = WorkspaceInvite.objects.create(
        workspace=ws, email="janedoe@gmail.com", created_by=owner
    )
    jane = _user("ja.ne.doe@gmail.com")
    invite.refresh_from_db()
    if invite.status == WorkspaceInvite.Status.PENDING:
        invite.accept(jane, updated_by=jane)
    assert ws.memberships.filter(user=jane, deleted__isnull=True).exists()


@pytest.mark.django_db
def test_accept_rejects_a_different_inbox():
    owner = _user("owner@example.com")
    ws = _workspace(owner)
    invite = WorkspaceInvite.objects.create(
        workspace=ws, email="janedoe@gmail.com", created_by=owner
    )
    other = _user("johndoe@gmail.com")
    with pytest.raises(AssertionError):
        invite.accept(other, updated_by=other)


@pytest.mark.django_db
def test_inviting_an_existing_member_under_an_alias_is_rejected():
    owner = _user("owner@example.com")
    ws = _workspace(owner)
    _user("janedoe@gmail.com")
    WorkspaceInvite.objects.create_and_send_invite(
        workspace=ws, email="janedoe@gmail.com", current_user=owner
    )
    with pytest.raises(ValidationError, match="already a member"):
        WorkspaceInvite.objects.create_and_send_invite(
            workspace=ws, email="jane.doe+team@gmail.com", current_user=owner
        )
