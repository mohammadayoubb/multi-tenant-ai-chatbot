import json
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


# (module_path, gate_key, [(threshold_metric_key, json_metric_key)])
EVALS = [
    ("evals.classifier", "classifier", [("macro_f1_min", "macro_f1")]),
    ("evals.agent_tool", "agent_tool_selection", [("accuracy_min", "accuracy")]),
    ("evals.red_team", "red_team", [("required_refusal_rate", "refusal_rate")]),
    ("evals.redaction", "redaction", [("required_secret_leak_count", "secret_leak_count")]),
]


def _run_mock(module: str, output_path: Path):
    return subprocess.run(
        [sys.executable, "-m", module, "--output", str(output_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


@pytest.mark.parametrize("module, gate, metrics", EVALS, ids=[m[0] for m in EVALS])
def test_eval_exits_zero_and_writes_json(module, gate, metrics, tmp_path):
    out = tmp_path / "out.json"
    r = _run_mock(module, out)
    assert r.returncode == 0, f"stderr: {r.stderr}"
    assert out.is_file(), "mock did not write output file"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload.get("metrics"), dict)
    for _, json_key in metrics:
        assert json_key in payload["metrics"], f"missing metrics.{json_key}"
        assert isinstance(payload["metrics"][json_key], (int, float))


@pytest.mark.parametrize("module, gate, metrics", EVALS, ids=[m[0] for m in EVALS])
def test_eval_value_satisfies_threshold(module, gate, metrics, tmp_path):
    """Eval metric values must satisfy the threshold direction for each metric."""
    thresholds = _load_thresholds()
    out = tmp_path / "out.json"
    _run_mock(module, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    for threshold_key, json_key in metrics:
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


@pytest.mark.parametrize("module, gate, metrics", EVALS, ids=[m[0] for m in EVALS])
def test_eval_passes_threshold_checker(module, gate, metrics, tmp_path):
    """Pipe each eval JSON through scripts/check_threshold.py and confirm exit 0."""
    out = tmp_path / "out.json"
    _run_mock(module, out)
    for threshold_key, _ in metrics:
        r = subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--gate",
                gate,
                "--metric",
                threshold_key,
                "--json",
                str(out),
            ],
            capture_output=True, text=True, check=False,
        )
        assert r.returncode == 0, (
            f"{gate}.{threshold_key} did not pass checker.\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert "PASS" in r.stdout


def test_rag_eval_is_real_and_passes_threshold_checker(tmp_path):
    out = tmp_path / "rag.json"
    r = _run_mock("evals.rag", out)
    assert r.returncode == 0, f"stderr: {r.stderr}"
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload.get("_mock") is not True
    assert {"hit_at_5", "mrr", "faithfulness"} <= set(payload["metrics"])
    assert isinstance(payload.get("cases"), list)

    for threshold_key in ("hit_at_5_min", "mrr_min", "faithfulness_min"):
        checked = subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--gate",
                "rag",
                "--metric",
                threshold_key,
                "--json",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, (
            f"rag.{threshold_key} did not pass checker.\n"
            f"stdout: {checked.stdout}\nstderr: {checked.stderr}"
        )
        assert "PASS" in checked.stdout
