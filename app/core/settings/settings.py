from __future__ import annotations

from .settings_fields import SettingsFields
from .settings_shims import SettingsShimMixin
from .settings_validators import SettingsValidationMixin


class Settings(SettingsValidationMixin, SettingsShimMixin, SettingsFields):
    """Application settings loaded from environment variables and `.env`."""
