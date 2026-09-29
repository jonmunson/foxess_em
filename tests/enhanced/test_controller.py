from custom_components.foxess_em.enhanced.controller import EnhancedController
from custom_components.foxess_em.enhanced.planner import PlannerInput


def snapshot():
    return PlannerInput(2, 0, 50, 2), 1


def test_controller_provider_disabled_and_listener_unsubscribe():
    calls = []
    controller = EnhancedController(True, snapshot)
    unsubscribe = controller.add_update_listener(lambda: calls.append(1))
    controller.update_callback()
    assert controller.status == "ok" and calls == [1]
    unsubscribe()
    controller.update_callback()
    assert calls == [1]
    disabled = EnhancedController(
        False, lambda: (_ for _ in ()).throw(AssertionError())
    )
    assert disabled.update_callback().status == "disabled"


def test_controller_provider_error_is_diagnostic():
    controller = EnhancedController(True, lambda: (_ for _ in ()).throw(RuntimeError()))
    result = controller.update_callback()
    assert result.status == "error"
    assert result.diagnostics == ("provider_error:RuntimeError",)
