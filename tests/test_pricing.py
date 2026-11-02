import pytest
from starlette.testclient import TestClient

from bots.models import AppUser
from bots.models import SavedRun, Workflow
from daras_ai_v2.lipsync_api import LipsyncModel
from functions.models import CalledFunction, FunctionTrigger
from payments.models import Subscription
from payments.plans import PricingPlan
from recipes.CompareLLM import CompareLLMPage
from recipes.Lipsync import LipsyncPage
from recipes.VideoBots import VideoBotsPage
from server import app
from usage_costs.models import UsageCost, ModelPricing

client = TestClient(app)


def test_copilot_get_raw_price_round_up(transactional_db):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="test_run",
        uid=user.uid,
    )

    state = {
        "tts_provider": "google",
        "num_outputs": 1,
    }

    model_pricing = ModelPricing.objects.create(
        model_id=1,
        sku=1,
        unit_cost=2.1,
        unit_quantity=1,
        category=1,
        provider=1,
        model_name="test_model",
    )

    UsageCost.objects.create(
        saved_run=bot_saved_run,
        pricing=model_pricing,
        quantity=1,
        unit_cost=model_pricing.unit_cost,
        unit_quantity=model_pricing.unit_quantity,
        dollar_amount=model_pricing.unit_cost * 1 / model_pricing.unit_quantity,
    )
    copilot_page = VideoBotsPage(
        user=user,
        query_params=dict(run_id=bot_saved_run.run_id or "", uid=user.uid or ""),
    )
    assert (
        copilot_page.get_price_roundoff(state=state)
        == 210 + copilot_page.PROFIT_CREDITS
    )


def test_agent_price_includes_recipe_tool_calls(transactional_db):
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    agent_run = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS, run_id="agent_run", uid=user.uid
    )
    for workflow, trigger, price in [
        (Workflow.GOOGLE_GPT, FunctionTrigger.pre, 3),  # billed in the agent
        (Workflow.IMAGE_GEN, FunctionTrigger.prompt, 4),  # billed in the agent
        (Workflow.FUNCTIONS, FunctionTrigger.prompt, 1),  # functions stay free
        (Workflow.FUNCTIONS, FunctionTrigger.pre, 1),  # in any trigger
        (Workflow.IMAGE_GEN, FunctionTrigger.post, 4),  # bills itself
    ]:
        CalledFunction.objects.create(
            saved_run=agent_run,
            function_run=SavedRun.objects.create(
                workflow=workflow,
                surface=SavedRun.Surface.tool_call,
                price=price,
            ),
            trigger=trigger.db_value,
        )
    page = VideoBotsPage(
        user=user, query_params=dict(run_id=agent_run.run_id, uid=user.uid)
    )

    # no usage counts as 1 credit, plus the Before search and the tool call
    assert page.get_price_roundoff(state={"tts_provider": "google"}) == (
        1 + 3 + 4 + page.PROFIT_CREDITS
    )

    agent_run.price = 11
    agent_run.save(update_fields=["price"])
    tools = page.get_cost_breakdown(running=False).sections[0]
    assert tools.label == "Tool calls · 2"
    assert [(line.label, line.usd) for line in tools.lines] == [
        (Workflow.GOOGLE_GPT.short_title, 0.03),
        (Workflow.IMAGE_GEN.short_title, 0.04),
    ]
    # each line opens its own run
    assert all(line.url for line in tools.lines)


@pytest.mark.parametrize(
    "ended", [dict(error_msg="Provider error"), dict(is_cancelled=True)]
)
def test_unbilled_run_costs_nothing(transactional_db, ended):
    user = AppUser.objects.create(uid="test_user", is_anonymous=False)
    sr = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS, run_id="ended_run", uid=user.uid, **ended
    )
    page = VideoBotsPage(user=user, query_params=dict(run_id=sr.run_id, uid=user.uid))

    # not the estimate a fresh run would show: nothing was charged
    assert page.get_run_cost_credits() == 0


def test_running_run_has_the_cost_modal_before_any_usage(transactional_db):
    from daras_ai_v2.base import StateKeys
    from gooey_gui.core.state import set_session_state
    from recipes.VideoBots_v2 import VideoBotsPageV2

    user = AppUser.objects.create(uid="test_user", balance=1000, is_anonymous=False)
    sr = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS, run_id="early_run", uid=user.uid
    )

    def run_cost_props(state):
        set_session_state(state)
        page = VideoBotsPageV2(
            user=user, query_params=dict(run_id=sr.run_id, uid=user.uid)
        )
        return page._run_cost_props

    try:
        # no model call yet, so no eco figures: the modal still opens
        running = run_cost_props({StateKeys.run_status: "Running..."})
        assert running.status == "running" and running.eco is None
        # its usage is still to come, so no "Minimum usage" stand-in line
        assert "Minimum usage" not in [
            line.label
            for section in running.cost_breakdown.sections
            for line in section.lines
        ]
        # an idle run with nothing to show has no modal
        assert run_cost_props({}) is None
        # a finished run charged without metered usage (an unpriced model,
        # billed tool calls) still itemises its charge
        sr.price = 3
        sr.save(update_fields=["price"])
        done = run_cost_props({})
        assert done.status == "done" and done.eco is None and done.cost_breakdown
    finally:
        set_session_state({})


def test_multiple_llm_sums_usage_cost(transactional_db):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.COMPARE_LLM,
        run_id="test_run",
        uid=user.uid,
    )

    state = {
        "tts_provider": "google",
        "num_outputs": 3,
        "selected_models": ["test_model1", "test_model2"],
    }

    model_pricing1 = ModelPricing.objects.create(
        model_id=1,
        sku=1,
        unit_cost=2.1,
        unit_quantity=1,
        category=1,
        provider=1,
        model_name="test_model1",
    )
    model_pricing2 = ModelPricing.objects.create(
        model_id=2,
        sku=1,
        unit_cost=1,
        unit_quantity=1,
        category=1,
        provider=1,
        model_name="test_model2",
    )

    UsageCost.objects.create(
        saved_run=bot_saved_run,
        pricing=model_pricing1,
        quantity=1,
        unit_cost=model_pricing1.unit_cost,
        unit_quantity=model_pricing1.unit_quantity,
        dollar_amount=model_pricing1.unit_cost * 1 / model_pricing1.unit_quantity,
    )
    UsageCost.objects.create(
        saved_run=bot_saved_run,
        pricing=model_pricing2,
        quantity=1,
        unit_cost=model_pricing2.unit_cost,
        unit_quantity=model_pricing2.unit_quantity,
        dollar_amount=model_pricing2.unit_cost * 1 / model_pricing2.unit_quantity,
    )

    llm_page = CompareLLMPage(
        user=user,
        query_params=dict(run_id=bot_saved_run.run_id or "", uid=user.uid or ""),
    )
    assert llm_page.get_price_roundoff(state=state) == (310 + llm_page.PROFIT_CREDITS)


def test_workflowmetadata_2x_multiplier(transactional_db):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.COMPARE_LLM,
        run_id="test_run",
        uid=user.uid,
    )

    state = {
        "tts_provider": "google",
        "num_outputs": 1,
        "selected_models": ["test_model"],
    }

    model_pricing = ModelPricing.objects.create(
        model_id=1,
        sku=1,
        unit_cost=2.1,
        unit_quantity=1,
        category=1,
        provider=1,
        model_name="test_model",
    )

    UsageCost.objects.create(
        saved_run=bot_saved_run,
        pricing=model_pricing,
        quantity=1,
        unit_cost=model_pricing.unit_cost,
        unit_quantity=model_pricing.unit_quantity,
        dollar_amount=model_pricing.unit_cost * 1 / model_pricing.unit_quantity,
    )

    metadata = Workflow.COMPARE_LLM.get_or_create_metadata()
    metadata.price_multiplier = 2
    metadata.save()

    llm_page = CompareLLMPage(
        user=user,
        query_params=dict(run_id=bot_saved_run.run_id or "", uid=user.uid or ""),
    )
    assert (
        llm_page.get_price_roundoff(state=state) == (210 + llm_page.PROFIT_CREDITS) * 2
    )


def test_lipsync_pricing(transactional_db):
    page = LipsyncPage(user=AppUser.objects.create(is_anonymous=False, balance=5))
    assert (
        page.get_price_roundoff(
            state=dict(selected_model=LipsyncModel.Wav2Lip.name, duration_sec=32)
        )
        == 42
    )
    assert (
        page.get_price_roundoff(
            state=dict(selected_model=LipsyncModel.SadTalker.name, duration_sec=32)
        )
        == 84
    )

    page.current_workspace.subscription = Subscription.objects.create(
        plan=PricingPlan.ENTERPRISE.db_value
    )
    assert (
        page.get_price_roundoff(
            state=dict(selected_model=LipsyncModel.Wav2Lip.name, duration_sec=32)
        )
        == 66
    )
    assert (
        page.get_price_roundoff(
            state=dict(selected_model=LipsyncModel.SadTalker.name, duration_sec=32)
        )
        == 132
    )
