"""Constants for the pure enhanced planner."""
from enum import StrEnum

MIN_HISTORY_DAYS = 7
MAX_HISTORY_DAYS = 30

class ForecastMode(StrEnum):
    P10 = "p10"
    P50 = "p50"
    P90 = "p90"
    BLEND = "blend"

class LoadMatchMode(StrEnum):
    ALL_DAYS = "all_days"
    WEEKDAY_WEEKEND = "weekday_weekend"
