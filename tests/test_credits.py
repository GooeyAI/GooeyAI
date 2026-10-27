from unittest.mock import patch

import pytest

from app_users.models import AppUserTransaction
from bots.models import AppUser
from daras_ai_v2 import exceptions
from payments import credits
from payments.models import Subscription
from payments.plans import PricingPlan
from workspaces.models import Workspace, WorkspaceMembership


def test_ensure_credits_passes_with_enough_workspace_balance(transactional_db):
    workspace, user = make_workspace(balance=100)
    assert list(credits.ensure_credits_and_auto_recharge(workspace, user, 100)) == []


def test_ensure_credits_raises_when_workspace_balance_is_short(transactional_db):
    workspace, user = make_workspace(balance=99)
    with pytest.raises(exceptions.InsufficientCredits):
        list(credits.ensure_credits_and_auto_recharge(workspace, user, 100))


def test_ensure_credits_auto_recharges_once_before_raising(transactional_db):
    workspace, user = make_workspace(balance=10)

    def recharge(ws):
        Workspace.objects.filter(pk=ws.pk).update(balance=500)

    with (
        patch.object(credits, "should_attempt_auto_recharge", return_value=True),
        patch.object(credits, "run_auto_recharge_gracefully", side_effect=recharge),
    ):
        messages = list(credits.ensure_credits_and_auto_recharge(workspace, user, 100))

    assert messages == ["Low balance detected. Recharging..."]
    assert workspace.balance == 500


def test_ensure_credits_uses_membership_balance_on_team_plan(transactional_db):
    workspace, user = make_workspace(balance=0, team=True)
    set_membership_balance(workspace, user, 100)
    assert list(credits.ensure_credits_and_auto_recharge(workspace, user, 100)) == []

    set_membership_balance(workspace, user, 99)
    with pytest.raises(exceptions.InsufficientCredits):
        list(credits.ensure_credits_and_auto_recharge(workspace, user, 100))


def test_ensure_credits_rejects_non_member_on_team_plan(transactional_db):
    workspace, _ = make_workspace(balance=1000, team=True)
    outsider = AppUser.objects.create(uid="outsider", is_anonymous=False)
    with pytest.raises(exceptions.UserError):
        list(credits.ensure_credits_and_auto_recharge(workspace, outsider, 1))


def test_deduct_credits_from_workspace(transactional_db):
    workspace, user = make_workspace(balance=100)
    txn = credits.deduct_credits(workspace, user, 30)
    workspace.refresh_from_db()
    assert workspace.balance == 70
    assert txn.amount == -30
    assert txn.invoice_id.startswith("gooey_in_")


def test_deduct_credits_from_membership_on_team_plan(transactional_db):
    workspace, user = make_workspace(balance=100, team=True)
    set_membership_balance(workspace, user, 50)
    credits.deduct_credits(workspace, user, 20)
    workspace.refresh_from_db()
    assert workspace.balance == 100
    assert credits.get_active_membership(workspace, user).balance == 30


def test_deduct_credits_once_per_invoice_id(transactional_db):
    workspace, user = make_workspace(balance=100)
    first = credits.deduct_credits(workspace, user, 30, invoice_id="gooey_test_1")
    second = credits.deduct_credits(workspace, user, 30, invoice_id="gooey_test_1")
    workspace.refresh_from_db()
    assert workspace.balance == 70
    assert first.pk == second.pk
    assert AppUserTransaction.objects.filter(invoice_id="gooey_test_1").count() == 1


def test_base_page_checks_and_deducts_through_credits(transactional_db):
    from recipes.SmartGPT import SmartGPTPage

    workspace, user = make_workspace(balance=100)
    page = SmartGPTPage(user=user, request_session={})
    price = page.get_price_roundoff({})

    assert list(page.ensure_credits_and_auto_recharge({})) == []
    txn, amount = page.deduct_credits({})

    workspace.refresh_from_db()
    assert amount == price == 20
    assert txn.amount == -price
    assert workspace.balance == 100 - price


def make_workspace(balance: int, team: bool = False) -> tuple[Workspace, AppUser]:
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    workspace = Workspace(
        name="myteam", created_by=user, is_personal=not team, balance=balance
    )
    workspace.create_with_owner()
    if team:
        workspace.subscription = Subscription.objects.create(
            plan=PricingPlan.TEAM.db_value, amount=1
        )
        workspace.save(update_fields=["subscription"])
    return workspace, user


def set_membership_balance(workspace: Workspace, user: AppUser, balance: int):
    WorkspaceMembership.objects.filter(workspace=workspace, user=user).update(
        balance=balance
    )
