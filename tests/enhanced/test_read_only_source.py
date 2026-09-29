from pathlib import Path

ROOT = Path(__file__).parents[2] / "custom_components" / "foxess_em" / "enhanced"


def test_enhanced_read_only_modules_have_no_write_dependencies():
    forbidden = (
        "FoxService",
        "ChargeService",
        "Schedule",
        "modbus",
        "async_call_service",
    )
    for path in ROOT.glob("*.py"):
        source = path.read_text()
        assert not any(token in source for token in forbidden), path
