from app.config import Settings
from app.llm.base import LLMError, LLMProvider
from app.llm.service import CircuitBreaker, LLMService, ResponseCache, TokenBudget

# Chosen for latency and cost: selection is a narrow task with the answer space fixed by us.
DEFAULT_MODELS = {"gemini": "gemini-3.5-flash-lite", "openai": "gpt-5-mini"}


def create_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise LLMError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
        from app.llm.gemini_provider import GeminiProvider

        return GeminiProvider(api_key=settings.gemini_api_key.get_secret_value())

    if not settings.openai_api_key:
        raise LLMError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
    from app.llm.openai_provider import OpenAIProvider

    return OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())


def create_llm_service(settings: Settings) -> LLMService:
    return LLMService(
        create_provider(settings),
        model=settings.llm_model or DEFAULT_MODELS[settings.llm_provider],
        fallback_model=settings.llm_fallback_model,
        timeout_s=settings.llm_timeout_s,
        deadline_s=settings.llm_deadline_s,
        max_retries=settings.llm_max_retries,
        max_output_tokens=settings.llm_max_output_tokens,
        budget=TokenBudget(daily_limit=settings.llm_daily_token_budget),
        cache=ResponseCache(max_size=settings.llm_cache_size),
        circuit=CircuitBreaker(settings.llm_circuit_failures, settings.llm_circuit_cooldown_s),
    )
