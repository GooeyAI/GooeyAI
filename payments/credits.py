import math
import typing
import uuid
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from app_users.models import AppUser, AppUserTransaction, TransactionReason
from daras_ai_v2 import exceptions, settings
from payments.auto_recharge import (
    run_auto_recharge_gracefully,
    should_attempt_auto_recharge,
)
from payments.plans import PricingPlan
from workspaces.models import Workspace, WorkspaceMembership


def ensure_credits_and_auto_recharge(
    workspace: Workspace, user: AppUser, price: int
) -> typing.Iterator[str]:
    """
    Raise InsufficientCredits unless whoever holds the balance can cover `price`.

    On Team plans that's the user's membership; otherwise it's the workspace,
    which gets one auto-recharge attempt first. Yields a progress message while
    recharging.

    Free workspaces are also refused with FreeCreditsLimitReached once the
    global daily limit on free usage is spent.
    """
    ensure_free_credits_daily_limit(workspace)

    if PricingPlan.from_sub(workspace.subscription) == PricingPlan.TEAM:
        membership = get_active_membership(workspace, user)
        if not membership:
            raise exceptions.UserError(
                "The workspace member who created this workflow is no longer part of the workspace."
            )
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


def ensure_free_credits_daily_limit(workspace: Workspace):
    """
    Raise FreeCreditsLimitReached for a non-paying workspace once all
    non-paying workspaces together have used up today's free credits.
    """
    if not workspace.is_paying and is_free_credits_daily_limit_reached():
        raise exceptions.FreeCreditsLimitReached()


def is_free_credits_daily_limit_reached() -> bool:
    """
    Whether non-paying workspaces have together used more than today's limit.
    New signups get no free credits while this holds.
    """
    return (
        settings.FREE_CREDITS_DAILY_LIMIT
        and get_free_credits_consumed_today() > settings.FREE_CREDITS_DAILY_LIMIT
    )


def get_free_credits_consumed_today() -> int:
    """Credits deducted from non-paying workspaces since midnight UTC."""
    start_of_day = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total = AppUserTransaction.objects.filter(
        workspace__is_paying=False,
        reason=TransactionReason.DEDUCT,
        created_at__gte=start_of_day,
    ).aggregate(total=Sum("amount"))["total"]
    return abs(total or 0)


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


def credits_for_cost(cost_usd: float) -> int:
    """Provider cost in credits, rounded up to the next credit."""
    if cost_usd <= 0:
        return 0
    return math.ceil(Decimal(str(cost_usd)) * settings.ADDON_CREDITS_PER_DOLLAR)


def format_credits_as_dollars(credits: int) -> str:
    """A credit count as the price a user pays, via the one conversion rate billing uses."""
    return f"${credits / settings.ADDON_CREDITS_PER_DOLLAR:,.2f}"
