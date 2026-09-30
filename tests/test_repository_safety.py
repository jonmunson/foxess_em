import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCAN_ROOTS = (ROOT / "custom_components", ROOT / "tests" / "fixtures")
PRIVATE_IPV4 = re.compile(r"\b(?:10|127|192\.168|169\.254)\.(?:\d{1,3}\.){2}\d{1,3}\b")
SECRET_VALUE = re.compile(
    r"(?i)\b(?:api[_-]?key|token|password|secret)\b\s*[:=]\s*['\"]([A-Za-z0-9_./+=-]{12,})['\"]"
)


def tracked_scan_files():
    output = subprocess.check_output(["git", "ls-files", "--", "custom_components", "tests/fixtures"], cwd=ROOT, text=True)
    return [ROOT / line for line in output.splitlines() if line]


def test_tracked_source_and_fixtures_contain_no_private_exports_or_obvious_secrets():
    violations = []
    for path in tracked_scan_files():
        text = path.read_text(errors="replace")
        if PRIVATE_IPV4.search(text):
            violations.append(f"private IPv4 address in {path.relative_to(ROOT)}")
        if SECRET_VALUE.search(text):
            violations.append(f"credential-like value in {path.relative_to(ROOT)}")
    assert not violations, "\n".join(violations)


def test_local_replay_and_export_paths_are_ignored():
    for relative in ("tests/fixtures/local/example.json", "data/replay/example.json", "exports/example.json"):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", relative], cwd=ROOT, text=True, capture_output=True
        )
        assert result.returncode == 0, f"not ignored: {relative}"
