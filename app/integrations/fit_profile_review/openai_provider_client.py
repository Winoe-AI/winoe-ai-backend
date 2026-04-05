"""OpenAI-backed fit-profile review provider."""

from __future__ import annotations

import logging

from app.ai import AggregatedFitProfileOutput, DayReviewerOutput
from app.ai.ai_provider_clients_service import (
    AIProviderExecutionError,
    api_key_configured,
    call_anthropic_json,
    call_openai_json_schema,
)
from app.config import settings
from app.integrations.fit_profile_review.base_client import (
    FitProfileAggregateRequest,
    FitProfileDayReviewRequest,
    FitProfileReviewProviderError,
)

logger = logging.getLogger(__name__)

_RETRYABLE_OPENAI_ERROR_MARKERS = (
    "ratelimiterror",
    "too many requests",
    "rate limit",
    "429",
    "apitimeouterror",
    "apiconnectionerror",
    "internalservererror",
    "serviceunavailableerror",
    "overloadederror",
)


def _is_retryable_openai_error(exc: Exception) -> bool:
    parts = [type(exc).__name__, str(exc)]
    normalized = " ".join(part for part in parts if part).strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _RETRYABLE_OPENAI_ERROR_MARKERS)


def _day_timeout_seconds() -> int:
    return max(
        settings.FIT_PROFILE_DAY1_TIMEOUT_SECONDS,
        settings.FIT_PROFILE_DAY23_TIMEOUT_SECONDS,
        settings.FIT_PROFILE_DAY4_TIMEOUT_SECONDS,
        settings.FIT_PROFILE_DAY5_TIMEOUT_SECONDS,
    )


def _day_max_retries() -> int:
    return max(
        settings.FIT_PROFILE_DAY1_MAX_RETRIES,
        settings.FIT_PROFILE_DAY23_MAX_RETRIES,
        settings.FIT_PROFILE_DAY4_MAX_RETRIES,
        settings.FIT_PROFILE_DAY5_MAX_RETRIES,
    )


def _fallback_day_model() -> str:
    return (
        str(settings.FIT_PROFILE_ANTHROPIC_FALLBACK_DAY_MODEL or "").strip()
        or "claude-sonnet-4-6"
    )


def _fallback_aggregator_model() -> str:
    return (
        str(settings.FIT_PROFILE_ANTHROPIC_FALLBACK_AGGREGATOR_MODEL or "").strip()
        or "claude-sonnet-4-6"
    )


def _unique_models(*model_names: str) -> list[str]:
    models: list[str] = []
    for model_name in model_names:
        normalized = (model_name or "").strip()
        if normalized and normalized not in models:
            models.append(normalized)
    return models


def _fallback_day_models() -> list[str]:
    return _unique_models(_fallback_day_model(), "claude-sonnet-4-6")


def _fallback_aggregator_models() -> list[str]:
    return _unique_models(_fallback_aggregator_model(), "claude-sonnet-4-6")


def _call_anthropic_with_model_fallbacks(
    *,
    operation: str,
    model_names: list[str],
    system_prompt: str,
    user_prompt: str,
    response_model,
    timeout_seconds: int,
    max_retries: int,
):
    last_error: AIProviderExecutionError | None = None
    for model_name in model_names:
        try:
            return call_anthropic_json(
                api_key=settings.ANTHROPIC_API_KEY,
                model=model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
        except AIProviderExecutionError as exc:
            last_error = exc
            logger.warning(
                "fit_profile_anthropic_model_attempt_failed operation=%s model=%s reason=%s",
                operation,
                model_name,
                type(exc).__name__,
            )
    if last_error is None:  # pragma: no cover - guarded by caller
        raise FitProfileReviewProviderError("anthropic_fallback_models_missing")
    raise last_error


class OpenAIFitProfileReviewProvider:
    """Run reviewer and aggregator calls via OpenAI structured outputs."""

    def review_day(
        self,
        *,
        request: FitProfileDayReviewRequest,
    ) -> DayReviewerOutput:
        try:
            result = call_openai_json_schema(
                api_key=settings.OPENAI_API_KEY,
                model=request.model,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                response_model=DayReviewerOutput,
                timeout_seconds=_day_timeout_seconds(),
                max_retries=_day_max_retries(),
            )
        except AIProviderExecutionError as exc:
            if not _is_retryable_openai_error(exc) or not api_key_configured(
                settings.ANTHROPIC_API_KEY
            ):
                raise FitProfileReviewProviderError(str(exc)) from exc
            fallback_models = _fallback_day_models()
            logger.warning(
                "fit_profile_openai_retryable_failure_falling_back_to_anthropic operation=review_day primaryModel=%s fallbackModels=%s reason=%s",
                request.model,
                ",".join(fallback_models),
                type(exc).__name__,
            )
            try:
                result = _call_anthropic_with_model_fallbacks(
                    operation="review_day",
                    model_names=fallback_models,
                    system_prompt=request.system_prompt,
                    user_prompt=request.user_prompt,
                    response_model=DayReviewerOutput,
                    timeout_seconds=_day_timeout_seconds(),
                    max_retries=_day_max_retries(),
                )
            except AIProviderExecutionError as fallback_exc:
                raise FitProfileReviewProviderError(str(fallback_exc)) from fallback_exc
        return result

    def aggregate_fit_profile(
        self,
        *,
        request: FitProfileAggregateRequest,
    ) -> AggregatedFitProfileOutput:
        try:
            result = call_openai_json_schema(
                api_key=settings.OPENAI_API_KEY,
                model=request.model,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                response_model=AggregatedFitProfileOutput,
                timeout_seconds=settings.FIT_PROFILE_AGGREGATOR_TIMEOUT_SECONDS,
                max_retries=settings.FIT_PROFILE_AGGREGATOR_MAX_RETRIES,
            )
        except AIProviderExecutionError as exc:
            if not _is_retryable_openai_error(exc) or not api_key_configured(
                settings.ANTHROPIC_API_KEY
            ):
                raise FitProfileReviewProviderError(str(exc)) from exc
            fallback_models = _fallback_aggregator_models()
            logger.warning(
                "fit_profile_openai_retryable_failure_falling_back_to_anthropic operation=aggregate_fit_profile primaryModel=%s fallbackModels=%s reason=%s",
                request.model,
                ",".join(fallback_models),
                type(exc).__name__,
            )
            try:
                result = _call_anthropic_with_model_fallbacks(
                    operation="aggregate_fit_profile",
                    model_names=fallback_models,
                    system_prompt=request.system_prompt,
                    user_prompt=request.user_prompt,
                    response_model=AggregatedFitProfileOutput,
                    timeout_seconds=settings.FIT_PROFILE_AGGREGATOR_TIMEOUT_SECONDS,
                    max_retries=settings.FIT_PROFILE_AGGREGATOR_MAX_RETRIES,
                )
            except AIProviderExecutionError as fallback_exc:
                raise FitProfileReviewProviderError(str(fallback_exc)) from fallback_exc
        return result


__all__ = ["OpenAIFitProfileReviewProvider"]
