from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from app.domains.simulations.ai_config import (
    AI_NOTICE_DEFAULT_TEXT,
    AI_NOTICE_DEFAULT_VERSION,
    default_ai_eval_enabled_by_day,
)
from app.schemas.simulations_ai_models import SimulationAIConfig


Resolver = Callable[..., tuple[str, str, dict[str, bool]]]


def build_simulation_ai_config_with_resolver(
    *,
    notice_version: str | None,
    notice_text: str | None,
    eval_enabled_by_day: Any,
    resolver: Resolver,
) -> SimulationAIConfig | None:
    resolved_notice_version, resolved_notice_text, resolved_eval = resolver(
        notice_version=notice_version,
        notice_text=notice_text,
        eval_enabled_by_day=eval_enabled_by_day,
    )
    try:
        return SimulationAIConfig.model_validate(
            {
                "noticeVersion": resolved_notice_version,
                "noticeText": resolved_notice_text,
                "evalEnabledByDay": resolved_eval,
            }
        )
    except ValidationError:
        return SimulationAIConfig.model_validate(
            {
                "noticeVersion": AI_NOTICE_DEFAULT_VERSION,
                "noticeText": AI_NOTICE_DEFAULT_TEXT,
                "evalEnabledByDay": default_ai_eval_enabled_by_day(),
            }
        )


__all__ = ["build_simulation_ai_config_with_resolver"]
