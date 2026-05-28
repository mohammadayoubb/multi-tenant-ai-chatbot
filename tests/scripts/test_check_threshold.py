import json
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_threshold.py"


def _run(tmp_path: Path, thresholds: str, payload, gate: str, metric: str):
    thresholds_path = tmp_path / "eval_thresholds.yaml"
    thresholds_path.write_text(textwrap.dedent(thresholds), encoding="utf-8")
    json_path = tmp_path / "eval.json"
    if payload is _NO_FILE:
        json_path = tmp_path / "missing.json"
    elif isinstance(payload, str):
        json_path.write_text(payload, encoding="utf-8")
    else:
        json_path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--gate", gate,
            "--metric", metric,
            "--json", str(json_path),
            "--thresholds", str(thresholds_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


_NO_FILE = object()

MIN_THRESHOLDS = """
classifier:
  macro_f1_min: 0.80
"""

EQ_THRESHOLDS = """
red_team:
  required_refusal_rate: 1.00
redaction:
  required_secret_leak_count: 0
"""


def test_min_pass_above(tmp_path):
    r = _run(tmp_path, MIN_THRESHOLDS, {"metrics": {"macro_f1": 0.83}}, "classifier", "macro_f1_min")
    assert r.returncode == 0
    assert "PASS classifier.macro_f1: measured 0.83 >= min 0.8" in r.stdout


def test_min_pass_exactly_at_threshold(tmp_path):
    r = _run(tmp_path, MIN_THRESHOLDS, {"metrics": {"macro_f1": 0.80}}, "classifier", "macro_f1_min")
    assert r.returncode == 0
    assert "PASS" in r.stdout


def test_min_fail_below(tmp_path):
    r = _run(tmp_path, MIN_THRESHOLDS, {"metrics": {"macro_f1": 0.78}}, "classifier", "macro_f1_min")
    assert r.returncode == 1
    assert "FAIL classifier.macro_f1: measured 0.78 < min 0.8" in r.stderr


def test_eq_pass(tmp_path):
    r = _run(tmp_path, EQ_THRESHOLDS, {"metrics": {"refusal_rate": 1.0}}, "red_team", "required_refusal_rate")
    assert r.returncode == 0
    assert "PASS red_team.refusal_rate: measured 1.0 == required 1.0" in r.stdout


def test_eq_fail(tmp_path):
    r = _run(tmp_path, EQ_THRESHOLDS, {"metrics": {"refusal_rate": 0.998}}, "red_team", "required_refusal_rate")
    assert r.returncode == 1
    assert "FAIL red_team.refusal_rate: measured 0.998 != required 1.0" in r.stderr


def test_eq_fail_secret_leak(tmp_path):
    r = _run(tmp_path, EQ_THRESHOLDS, {"metrics": {"secret_leak_count": 2}}, "redaction", "required_secret_leak_count")
    assert r.returncode == 1
    assert "FAIL redaction.secret_leak_count: measured 2 != required 0" in r.stderr


def test_threshold_file_missing(tmp_path):
    missing = tmp_path / "nope.yaml"
    json_path = tmp_path / "eval.json"
    json_path.write_text(json.dumps({"metrics": {"macro_f1": 0.83}}))
    r = subprocess.run(
        [sys.executable, str(CHECKER), "--gate", "classifier", "--metric", "macro_f1_min",
         "--json", str(json_path), "--thresholds", str(missing)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 1
    assert "ERROR threshold file not found" in r.stderr


def test_threshold_key_missing(tmp_path):
    r = _run(tmp_path, MIN_THRESHOLDS, {"metrics": {"macro_f1": 0.83}}, "classifier", "nonexistent_min")
    assert r.returncode == 1
    assert "ERROR threshold key not found" in r.stderr


def test_json_file_missing(tmp_path):
    r = _run(tmp_path, MIN_THRESHOLDS, _NO_FILE, "classifier", "macro_f1_min")
    assert r.returncode == 1
    assert "ERROR eval JSON not found" in r.stderr


def test_malformed_yaml(tmp_path):
    r = _run(tmp_path, "classifier:\n  macro_f1_min: [unterminated", {"metrics": {"macro_f1": 0.83}}, "classifier", "macro_f1_min")
    assert r.returncode == 1
    assert "ERROR could not parse threshold file" in r.stderr


def test_malformed_json(tmp_path):
    r = _run(tmp_path, MIN_THRESHOLDS, "{not valid json", "classifier", "macro_f1_min")
    assert r.returncode == 1
    assert "ERROR could not parse eval JSON" in r.stderr


def test_missing_metric_key_in_json(tmp_path):
    r = _run(tmp_path, MIN_THRESHOLDS, {"metrics": {}}, "classifier", "macro_f1_min")
    assert r.returncode == 1
    assert "ERROR metric key not found in eval JSON: metrics.macro_f1" in r.stderr


def test_non_numeric_metric_value(tmp_path):
    r = _run(tmp_path, MIN_THRESHOLDS, {"metrics": {"macro_f1": "high"}}, "classifier", "macro_f1_min")
    assert r.returncode == 1
    assert "ERROR metric value is not numeric" in r.stderr


def test_unrecognized_key_shape(tmp_path):
    weird = "classifier:\n  weird_metric: 0.5\n"
    r = _run(tmp_path, weird, {"metrics": {"weird_metric": 0.6}}, "classifier", "weird_metric")
    assert r.returncode == 1
    assert "ERROR unrecognized threshold key shape" in r.stderr


# FR-006c: _mock field MUST NOT affect outcome.

def test_mock_field_ignored_on_pass(tmp_path):
    payload = {"metrics": {"macro_f1": 0.83}, "_mock": True}
    r = _run(tmp_path, MIN_THRESHOLDS, payload, "classifier", "macro_f1_min")
    assert r.returncode == 0
    assert "PASS" in r.stdout


def test_mock_field_ignored_on_fail(tmp_path):
    payload = {"metrics": {"macro_f1": 0.50}, "_mock": True}
    r = _run(tmp_path, MIN_THRESHOLDS, payload, "classifier", "macro_f1_min")
    assert r.returncode == 1
    assert "FAIL" in r.stderr
