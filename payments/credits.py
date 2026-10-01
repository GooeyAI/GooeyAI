import typing
import uuid

from app_users.models import AppUser, AppUserTransaction
from daras_ai_v2 import exceptions
from payments.auto_recharge import (
    run_auto_recharge_gracefully,
    should_attempt_auto_recharge,
)
from payments.plans import PricingPlan
from workspaces.models import Workspace, WorkspaceMembership

# kept byte-for-byte from BasePage, where this message used to live
TEAM_MEMBER_MISSING_ERROR = """
                  The workspace member who created this workflow is no longer part of the workspace.
                """


def ensure_credits_and_auto_recharge(
    workspace: Workspace, user: AppUser, price: int
) -> typing.Iterator[str]:
    """
    Raise InsufficientCredits unless whoever holds the balance can cover `price`.

    On Team plans that's the user's membership; otherwise it's the workspace,
    which gets one auto-recharge attempt first. Yields a progress message while
    recharging.
    """
    if PricingPlan.from_sub(workspace.subscription) == PricingPlan.TEAM:
        membership = get_active_membership(workspace, user)
        if not membership:
            raise exceptions.UserError(TEAM_MEMBER_MISSING_ERROR)
        if membership.balance >= price:
            return
        raise exceptions.InsufficientCredits(price=price)

    if workspace.balance >= price:
        return

    if should_attempt_auto_recharge(workspace):
        yield "Low balance detected. Recharging..."
        run_auto_recharge_gracefully(workspace)
        workspace.refresh_from_db()

    if workspace.balance >= price:
        return

    raise exceptions.InsufficientCredits(price=price)


def deduct_credits(
    workspace: Workspace,
    user: AppUser,
    amount: int,
    invoice_id: str | None = None,
) -> AppUserTransaction:
    """
    Deduct `amount` credits from the membership on Team plans, else from the
    workspace. A repeated `invoice_id` returns the existing transaction instead
    of deducting again.
    """
    invoice_id = invoice_id or f"gooey_in_{uuid.uuid1()}"

    if PricingPlan.from_sub(workspace.subscription) == PricingPlan.TEAM:
        membership = get_active_membership(workspace, user)
        if membership:
            return membership.add_balance(amount=-amount, invoice_id=invoice_id)

    return workspace.add_balance(amount=-amount, user=user, invoice_id=invoice_id)


def get_active_membership(
    workspace: Workspace, user: AppUser
) -> WorkspaceMembership | None:
    return workspace.memberships.filter(user=user, deleted__isnull=True).first()
