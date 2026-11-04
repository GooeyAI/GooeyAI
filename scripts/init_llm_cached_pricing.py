from decimal import Decimal

from usage_costs.models import ModelPricing, ModelSku

# cached input price as a fraction of the model's regular input price
# only models whose provider reports cached tokens & bills them at a discount
CACHED_INPUT_RATIO = {
    # OpenAI / Azure OpenAI - https://platform.openai.com/docs/pricing
    "gpt-6_astra": 0.1,
    "gpt_6_1_sol": 0.1,
    "gpt_6_sol": 0.1,
    "gpt_6_luna": 0.1,
    "gpt_5_6_sol": 0.1,
    "gpt_5_6_terra": 0.1,
    "gpt_5_6_luna": 0.1,
    "gpt_5_5": 0.1,
    "gpt_5_4": 0.1,
    "gpt_5_4_mini": 0.1,
    "gpt_5_4_nano": 0.1,
    "gpt_5_2": 0.1,
    "gpt_5_1": 0.1,
    "gpt_5": 0.1,
    "gpt_5_chat": 0.1,
    "gpt_5_mini": 0.1,
    "gpt_5_nano": 0.1,
    "gpt_realtime": 0.1,
    "gpt_realtime_1_5": 0.1,
    "gpt-realtime-mini": 0.1,
    # these are priced at the audio input rate, so cached audio input applies
    "gpt_realtime_2": 0.0125,
    "gpt_realtime_2_1": 0.0125,
    "gpt_realtime_2_1_mini": 0.03,
    "gpt_4_o_audio": 0.5,
    "gpt_4_o_mini_audio": 0.5,
    "gpt_4_5": 0.5,
    "gpt_4_1": 0.25,
    "gpt_4_1_mini": 0.25,
    "gpt_4_1_nano": 0.25,
    "gpt_4_o": 0.5,
    "gpt_4_o_mini": 0.5,
    "o1": 0.5,
    "o1_preview": 0.5,
    "o1_mini": 0.5,
    "o3_mini": 0.5,
    "o3": 0.25,
    "o4_mini": 0.25,
    "o4_mini_thinking": 0.25,
    # Google - https://ai.google.dev/gemini-api/docs/pricing
    "gemini_4_argon": 0.1,
    "gemini_3_8_flash": 0.1,
    "gemini_3_7_flash": 0.1,
    "gemini_3_6_flash": 0.1,
    "gemini_3_5_flash": 0.1,
    "gemini_3_1_pro_preview": 0.1,
    "gemini_3_1_flash_lite": 0.1,
    "gemini_3_pro": 0.1,
    "gemini_3_flash": 0.1,
    "gemini_2_5_pro": 0.1,
    "gemini_2_5_flash": 0.1,
    "gemini_2_5_flash_lite": 0.1,
    "gemini_2_flash": 0.25,
    # Fireworks AI - https://fireworks.ai/docs/guides/prompt-caching
    "deepseek_v_4_flash": 0.5,
    "deepseek_v_4_pro": 0.5,
    "deepseek_v3p1": 0.5,
    "deepseek_v3p2": 0.5,
    "glm_5_1": 0.5,
    # Fireworks AI - https://docs.fireworks.ai/serverless/pricing
    "deepseek_v_4_1_flash": 0.006 / 0.30,
    "glm_5_3_flash": 0.2,
    "gpt-oss-120b": 0.1,
    "minimax_m_3": 0.2,
    "nemotron_3_ultra": 0.2,
    "nemotron_lightning_3_5_30_b": 0.2,
    # Mistral AI - https://docs.mistral.ai/studio/conversations/advanced/prompt-caching
    "mistral_large_2512": 0.1,
    "Mistral Large 4": 0.1,
    "mistral_small_4": 0.1,
    "ministral-14b": 0.1,
    # Meta - https://dev.meta.ai/docs/pricing-rate-limits
    "muse_wonder": 0.20 / 4.00,
    "muse_spark_1_3": 0.15 / 1.25,
    "muse_spark_1_2": 0.15 / 1.25,
    # Vercel AI Gateway - https://ai-gateway.vercel.sh/v1/models
    "muse_glimmer_30b": 0.04 / 0.35,
    "gemma-4-26b-a4b-it": 0.1,
    # Alibaba Model Studio - https://help.aliyun.com/en/model-studio/context-cache
    "qwen_3_7_plus": 0.2,
    "qwen_3_8_27b": 0.2,
    "qwen_3_8_max": 1.5 / 12,
}


def run():
    prompt_pricings = ModelPricing.objects.filter(
        sku=ModelSku.llm_prompt, model_name__in=CACHED_INPUT_RATIO
    )
    for prompt_pricing in prompt_pricings:
        ratio = CACHED_INPUT_RATIO[prompt_pricing.model_name]
        obj, created = ModelPricing.objects.get_or_create(
            model_id=prompt_pricing.model_id,
            sku=ModelSku.llm_cached_prompt,
            defaults=dict(
                model_name=prompt_pricing.model_name,
                unit_cost=prompt_pricing.unit_cost * Decimal(str(ratio)),
                unit_quantity=prompt_pricing.unit_quantity,
                category=prompt_pricing.category,
                provider=prompt_pricing.provider,
                pricing_url=prompt_pricing.pricing_url,
                notes=f"{ratio * 100:g}% of the input price",
            ),
        )
        if created:
            print(f"created {obj} @ {obj.unit_cost}")
