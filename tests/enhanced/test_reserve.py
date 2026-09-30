from custom_components.foxess_em.enhanced.reserve import calculate_reserve


def test_reserve_uses_recent_positive_errors_and_bounds():
    r = calculate_reserve(
        [-2, 1, 3, 9],
        sample_window=3,
        percentile=50,
        safety_factor=2,
        min_reserve=2,
        max_reserve=10,
    )
    assert r.errors_kwh == (1.0, 3.0, 9.0)
    assert r.reserve_kwh == 6.0


def test_reserve_empty_or_negative_is_minimum_with_diagnostic():
    r = calculate_reserve([-3, 0], min_reserve=1)
    assert r.reserve_kwh == 1 and r.status == "fallback"


def test_reserve_accepts_actual_and_forecast_series():
    assert (
        calculate_reserve(
            actual_net=[5, 9], forecast_net=[4, 10], percentile=100
        ).reserve_kwh
        == 1
    )
