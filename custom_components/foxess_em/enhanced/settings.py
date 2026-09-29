"""Safe normalization of persisted enhanced planner settings."""

from ..const import (
    ENHANCED_ENABLED,
    ENHANCED_HISTORY_DAYS,
    ENHANCED_MODE,
    ENHANCED_MODES,
)


def normalize_settings(data):
    """Return safe enhanced settings."""
    enabled = data.get(ENHANCED_ENABLED, False)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
    else:
        enabled = bool(enabled)
    mode = data.get(ENHANCED_MODE, "p50")
    if mode not in ENHANCED_MODES:
        mode = "p50"
    try:
        history = int(data.get(ENHANCED_HISTORY_DAYS, 14))
    except (TypeError, ValueError):
        history = 14
    if not 7 <= history <= 30:
        history = 14
    return {
        ENHANCED_ENABLED: enabled,
        ENHANCED_MODE: mode,
        ENHANCED_HISTORY_DAYS: history,
    }
