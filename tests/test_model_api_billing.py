import threading
from unittest.mock import patch

import pytest
from django.db import connections

from app_users.models import AppUserTransaction
from bots.models import AppUser
from daras_ai_v2.exceptions import InsufficientCredits
from model_api import billing
from model_api.models import ModelApiCall
from payments.models import Subscription
from payments.plans import PricingPlan
from workspaces.models import Workspace, WorkspaceMembership


@pytest.mark.parametrize(
    "cost_usd, expected",
    [(0, 0), (0.0002, 1), (0.01, 1), (0.0123, 2), (0.05, 5), (1.5, 150)],
)
def test_credits_round_up_to_the_next_cent(cost_usd, expected):
    assert billing.credits_for_cost(cost_usd) == expected


def test_estimate_covers_max_tokens():
    request = {"messages": [{"role": "user", "content": "hi"}]}
    small = billing.estimate_cost_usd(
        "openai/gpt-4.1-mini", request | {"max_tokens": 10}
    )
    large = billing.estimate_cost_usd(
        "openai/gpt-4.1-mini", request | {"max_tokens": 32000}
    )
    assert 0 < small < large
    # 32k output tokens at gpt-4.1-mini's $1.60/M output price
    assert large >= 32000 * 1.6e-06


def test_estimate_covers_every_requested_choice():
    request = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1000}
    one = billing.estimate_cost_usd("openai/gpt-4.1-mini", request)
    three = billing.estimate_cost_usd("openai/gpt-4.1-mini", request | {"n": 3})
    # the prompt is paid once, the output three times
    assert three > 2.9 * one
    assert three - one == pytest.approx(2 * 1000 * 1.6e-06)


def test_reserve_admits_within_balance_and_refuses_beyond(transactional_db):
    workspace, user = make_workspace(balance=10)
    with fixed_estimate(0.05):  # 5 credits per call
        first = reserve(workspace, user)
        second = reserve(workspace, user)
        with pytest.raises(InsufficientCredits):
            reserve(workspace, user)  # 10 credits are already reserved

    assert first.status == second.status == ModelApiCall.Status.RESERVED
    assert first.reserved_credits == 5


def test_reserve_allows_the_configured_overdraft(transactional_db):
    workspace, user = make_workspace(balance=0)
    with (
        fixed_estimate(0.05),
        patch.object(billing.settings, "MODEL_API_OVERDRAFT_LIMIT_CREDITS", 5),
    ):
        reserve(workspace, user)
        with pytest.raises(InsufficientCredits):
            reserve(workspace, user)


def test_settle_charges_once(transactional_db):
    workspace, user = make_workspace(balance=100)
    with fixed_estimate(0.05):
        call = reserve(workspace, user)

    billing.settle(call.call_id, cost_usd=0.0123, usage={}, source="success")
    billing.settle(call.call_id, cost_usd=0.0123, usage={}, source="success")

    workspace.refresh_from_db()
    call.refresh_from_db()
    assert workspace.balance == 98
    assert call.status == ModelApiCall.Status.SETTLED
    assert call.charged_credits == 2
    assert AppUserTransaction.objects.filter(invoice_id=call.invoice_id).count() == 1


def test_rerunning_a_stuck_settlement_charges_once(transactional_db):
    workspace, user = make_workspace(balance=100)
    with fixed_estimate(0.05):
        call = reserve(workspace, user)
    billing.settle(call.call_id, cost_usd=0.03, usage={}, source="success")

    # as if the process died between the deduction and marking it settled
    ModelApiCall.objects.filter(pk=call.pk).update(status=ModelApiCall.Status.SETTLING)
    call.refresh_from_db()
    billing.finish_settlement(call)

    workspace.refresh_from_db()
    assert workspace.balance == 97
    assert AppUserTransaction.objects.filter(invoice_id=call.invoice_id).count() == 1


def test_settle_without_a_cost_charges_the_reservation(transactional_db):
    workspace, user = make_workspace(balance=100)
    with fixed_estimate(0.05):
        call = reserve(workspace, user)
    billing.settle(call.call_id, cost_usd=None, usage={}, source="success")
    workspace.refresh_from_db()
    assert workspace.balance == 95


def test_release_charges_nothing_and_a_late_cost_still_settles(transactional_db):
    workspace, user = make_workspace(balance=100)
    with fixed_estimate(0.05):
        call = reserve(workspace, user)

    assert billing.release(call.call_id)
    workspace.refresh_from_db()
    assert workspace.balance == 100

    billing.settle(call.call_id, cost_usd=0.01, usage={}, source="failure")
    workspace.refresh_from_db()
    assert workspace.balance == 99
    assert not billing.release(call.call_id)


def test_settling_an_unknown_call_is_a_no_op(transactional_db):
    assert (
        billing.settle("no-such-call", cost_usd=1, usage={}, source="success") is None
    )


def test_team_plan_reserves_and_charges_the_member(transactional_db):
    workspace, user = make_workspace(balance=1000, team=True)
    WorkspaceMembership.objects.filter(workspace=workspace, user=user).update(balance=5)
    with fixed_estimate(0.05):
        call = reserve(workspace, user)
        with pytest.raises(InsufficientCredits):
            reserve(workspace, user)
    billing.settle(call.call_id, cost_usd=0.02, usage={}, source="success")

    workspace.refresh_from_db()
    assert workspace.balance == 1000
    assert WorkspaceMembership.objects.get(workspace=workspace, user=user).balance == 3


def test_parallel_reservations_never_pass_the_balance(transactional_db):
    workspace, user = make_workspace(balance=15)
    admitted, refused = [], []

    def worker():
        try:
            reserve(workspace, user)
            admitted.append(1)
        except InsufficientCredits:
            refused.append(1)
        finally:
            connections.close_all()

    with fixed_estimate(0.05):
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(admitted) == 3
    assert len(refused) == 7


def reserve(workspace: Workspace, user: AppUser) -> ModelApiCall:
    return billing.reserve(
        workspace_id=workspace.id,
        user_id=user.id,
        api_key_id=None,
        model="gpt-4.1-mini",
        litellm_model="openai/gpt-4.1-mini",
        call_type="acompletion",
        request_data={"messages": [{"role": "user", "content": "hi"}]},
    )


def fixed_estimate(cost_usd: float):
    return patch.object(billing, "estimate_cost_usd", return_value=cost_usd)


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
