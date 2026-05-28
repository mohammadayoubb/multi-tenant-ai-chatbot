import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS_PATH = REPO_ROOT / "eval_thresholds.yaml"
CHECKER = REPO_ROOT / "scripts" / "check_threshold.py"


def _load_thresholds():
    return yaml.safe_load(THRESHOLDS_PATH.read_text(encoding="utf-8"))


# (module_path, gate_key, [(threshold_metric_key, json_metric_key, owner)])
MOCKS = [
    ("evals.classifier", "classifier", [("macro_f1_min", "macro_f1", "Ayoub")]),
    ("evals.rag", "rag", [
        ("hit_at_5_min", "hit_at_5", "Nasser"),
        ("faithfulness_min", "faithfulness", "Nasser"),
    ]),
    ("evals.agent_tool", "agent_tool_selection", [("accuracy_min", "accuracy", "Nasser")]),
    ("evals.red_team", "red_team", [("required_refusal_rate", "refusal_rate", "Ayoub")]),
    ("evals.redaction", "redaction", [("required_secret_leak_count", "secret_leak_count", "Ayoub")]),
]


def _run_mock(module: str, output_path: Path):
    return subprocess.run(
        [sys.executable, "-m", module, "--output", str(output_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


@pytest.mark.parametrize("module, gate, metrics", MOCKS, ids=[m[0] for m in MOCKS])
def test_mock_exits_zero_and_writes_json(module, gate, metrics, tmp_path):
    out = tmp_path / "out.json"
    r = _run_mock(module, out)
    assert r.returncode == 0, f"stderr: {r.stderr}"
    assert out.is_file(), "mock did not write output file"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload.get("metrics"), dict)
    for _, json_key, _ in metrics:
        assert json_key in payload["metrics"], f"missing metrics.{json_key}"
        assert isinstance(payload["metrics"][json_key], (int, float))
    assert payload.get("_mock") is True, "every mock must declare _mock: true"


@pytest.mark.parametrize("module, gate, metrics", MOCKS, ids=[m[0] for m in MOCKS])
def test_mock_stderr_banner(module, gate, metrics, tmp_path):
    r = _run_mock(module, tmp_path / "out.json")
    owners = "|".join(sorted({m[2] for m in metrics}))
    # the mock stderr uses the module-leaf name (e.g., agent_tool), not the gate key (agent_tool_selection)
    module_leaf = module.split(".", 1)[1]
    pattern = rf"^MOCK EVALUATOR: {re.escape(module_leaf)} is not yet implemented — owner: ({owners})$"
    matches = [line for line in r.stderr.splitlines() if re.match(pattern, line)]
    assert matches, f"expected one MOCK EVALUATOR line matching {pattern!r}, got stderr:\n{r.stderr}"


@pytest.mark.parametrize("module, gate, metrics", MOCKS, ids=[m[0] for m in MOCKS])
def test_mock_value_satisfies_threshold(module, gate, metrics, tmp_path):
    """Mock metric values must satisfy the threshold direction for each metric."""
    thresholds = _load_thresholds()
    out = tmp_path / "out.json"
    _run_mock(module, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    for threshold_key, json_key, _ in metrics:
        threshold = thresholds[gate][threshold_key]
        measured = payload["metrics"][json_key]
        if threshold_key.endswith("_min"):
            assert measured >= threshold, (
                f"{gate}.{json_key} mock={measured} < min={threshold}"
            )
        elif threshold_key.startswith("required_"):
            assert measured == threshold, (
                f"{gate}.{json_key} mock={measured} != required={threshold}"
            )
        else:
            pytest.fail(f"unrecognized threshold key shape: {threshold_key}")


@pytest.mark.parametrize("module, gate, metrics", MOCKS, ids=[m[0] for m in MOCKS])
def test_mock_passes_threshold_checker(module, gate, metrics, tmp_path):
    """Pipe each mock's JSON through scripts/check_threshold.py and confirm exit 0."""
    out = tmp_path / "out.json"
    _run_mock(module, out)
    for threshold_key, _, _ in metrics:
        r = subprocess.run(
            [sys.executable, str(CHECKER),
             "--gate", gate, "--metric", threshold_key,
             "--json", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert r.returncode == 0, (
            f"{gate}.{threshold_key} did not pass checker.\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert "PASS" in r.stdout
