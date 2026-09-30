"""Static safety checks for configuration logging."""

import ast
from pathlib import Path

SOURCE_PATH = (
    Path(__file__).parents[2] / "custom_components" / "foxess_em" / "__init__.py"
)


def test_debug_logging_never_passes_complete_config_mappings():
    tree = ast.parse(SOURCE_PATH.read_text())
    forbidden_names = {"entry_data", "entry_options"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"debug", "info", "warning", "error", "exception"}:
            continue
        for argument in node.args:
            if isinstance(argument, ast.Name):
                assert argument.id not in forbidden_names


def test_setup_source_does_not_log_secret_values():
    source = SOURCE_PATH.read_text()
    assert 'debug(f"{entry' not in source
    assert 'debug("%s", entry_data)' not in source
    assert 'debug("%s", entry_options)' not in source
