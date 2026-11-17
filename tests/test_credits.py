from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

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


def test_free_workspace_is_refused_once_daily_free_limit_is_used(transactional_db):
    workspace, user = make_workspace(balance=1000)
    with patch.object(credits.settings, "FREE_CREDITS_DAILY_LIMIT", 100):
        credits.deduct_credits(workspace, user, 100)
        assert list(credits.ensure_credits_and_auto_recharge(workspace, user, 1)) == []

        credits.deduct_credits(workspace, user, 1)
        assert credits.get_free_credits_consumed_today() == 101
        with pytest.raises(exceptions.FreeCreditsLimitReached):
            list(credits.ensure_credits_and_auto_recharge(workspace, user, 1))


def test_daily_free_limit_applies_across_free_workspaces(transactional_db):
    spender, spender_user = make_workspace(balance=1000, uid="spender")
    workspace, user = make_workspace(balance=1000)
    with patch.object(credits.settings, "FREE_CREDITS_DAILY_LIMIT", 100):
        credits.deduct_credits(spender, spender_user, 101)
        with pytest.raises(exceptions.FreeCreditsLimitReached):
            list(credits.ensure_credits_and_auto_recharge(workspace, user, 1))


def test_daily_free_limit_ignores_paying_workspaces(transactional_db):
    paying, paying_user = make_workspace(balance=1000, uid="paying")
    Workspace.objects.filter(pk=paying.pk).update(is_paying=True)
    paying.refresh_from_db()
    workspace, user = make_workspace(balance=1000)
    with patch.object(credits.settings, "FREE_CREDITS_DAILY_LIMIT", 100):
        # paid usage doesn't count towards the free limit
        credits.deduct_credits(paying, paying_user, 500)
        assert credits.get_free_credits_consumed_today() == 0
        assert list(credits.ensure_credits_and_auto_recharge(workspace, user, 1)) == []

        # and paying workspaces keep running after free usage passes the limit
        credits.deduct_credits(workspace, user, 101)
        assert (
            list(credits.ensure_credits_and_auto_recharge(paying, paying_user, 1)) == []
        )


def test_first_team_workspace_gets_no_free_credits_past_daily_limit(transactional_db):
    spender, spender_user = make_workspace(balance=1000, uid="spender")
    with patch.object(credits.settings, "FREE_CREDITS_DAILY_LIMIT", 100):
        credits.deduct_credits(spender, spender_user, 100)
        within_limit, _ = make_workspace(balance=0, team=True, uid="within_limit")
        assert within_limit.balance == credits.settings.FIRST_WORKSPACE_FREE_CREDITS

        credits.deduct_credits(spender, spender_user, 1)
        past_limit, _ = make_workspace(balance=0, team=True, uid="past_limit")
        assert past_limit.balance == 0


def test_daily_free_limit_resets_the_next_day(transactional_db):
    workspace, user = make_workspace(balance=1000)
    with patch.object(credits.settings, "FREE_CREDITS_DAILY_LIMIT", 100):
        txn = credits.deduct_credits(workspace, user, 101)
        AppUserTransaction.objects.filter(pk=txn.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        assert credits.get_free_credits_consumed_today() == 0
        assert list(credits.ensure_credits_and_auto_recharge(workspace, user, 1)) == []


def test_daily_free_limit_can_be_disabled(transactional_db):
    workspace, user = make_workspace(balance=1000)
    with patch.object(credits.settings, "FREE_CREDITS_DAILY_LIMIT", 0):
        credits.deduct_credits(workspace, user, 500)
        assert list(credits.ensure_credits_and_auto_recharge(workspace, user, 1)) == []


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


@pytest.mark.parametrize(
    "cost_usd, expected",
    [(0, 0), (0.0002, 1), (0.01, 1), (0.0123, 2), (0.05, 5), (1.5, 150)],
)
def test_credits_for_cost_rounds_up_to_the_next_credit(cost_usd, expected):
    assert credits.credits_for_cost(cost_usd) == expected


def make_workspace(
    balance: int, team: bool = False, uid: str = "test_user"
) -> tuple[Workspace, AppUser]:
    user = AppUser.objects.create(uid=uid, is_anonymous=False)
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
