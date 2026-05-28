# Quickstart: CI Eval Gates Enforced

**Feature**: 006-ci-eval-gates · **Owner**: Amer · **Audience**: reviewers, the four owners, and anyone validating this PR locally

Use this guide to (1) run each gate locally exactly as CI does, (2) inspect a workflow run page after pushing the branch, and (3) understand what the artifacts look like.

---

## 1. Local: run a single gate end-to-end

```sh
# 1. Run the mock CLI to produce JSON.
python -m evals.classifier --output /tmp/classifier.json

# 2. Inspect the output.
cat /tmp/classifier.json
# {"metrics": {"macro_f1": 0.80}, "_mock": true}

# 3. Check the JSON against the threshold.
python scripts/check_threshold.py \
    --gate classifier \
    --metric macro_f1_min \
    --json /tmp/classifier.json
# PASS classifier.macro_f1: measured 0.80 >= min 0.80
echo $?  # 0
```

Repeat for the other four gates — every command pair completes in well under a second.

## 2. Local: simulate a failing gate

```sh
# Create a deliberately bad JSON.
echo '{"metrics": {"macro_f1": 0.78}}' > /tmp/bad.json

python scripts/check_threshold.py \
    --gate classifier \
    --metric macro_f1_min \
    --json /tmp/bad.json
# (stderr) FAIL classifier.macro_f1: measured 0.78 < min 0.80
echo $?  # 1
```

## 3. Local: simulate a malformed JSON

```sh
echo '{"metrics": {}}' > /tmp/missing.json

python scripts/check_threshold.py \
    --gate classifier \
    --metric macro_f1_min \
    --json /tmp/missing.json
# (stderr) ERROR metric key not found in eval JSON: metrics.macro_f1
echo $?  # 1
```

## 4. Run the helper's unit tests

```sh
pytest tests/scripts/test_check_threshold.py -v
pytest tests/evals/test_mock_evaluators.py -v
```

Both suites must pass; both run in under two seconds combined.

## 5. CI: what happens on a pull request

Open a PR from `006-ci-eval-gates` against `main`. The Actions tab shows **six** checks:

```text
✅ lint-test-build
✅ classifier-eval
✅ rag-eval
✅ agent-tool-eval
✅ red-team
✅ redaction-eval
```

Each eval check finishes shortly after `lint-test-build` (the mocks are instant). Click any check to expand the log; the `MOCK EVALUATOR:` line appears on stderr near the top of the eval step.

## 6. CI: where to find the JSON artifacts

On the run summary page, scroll to the bottom — a **Artifacts** section lists five entries:

- `classifier-eval-output`
- `rag-eval-output`
- `agent-tool-eval-output`
- `red-team-eval-output`
- `redaction-eval-output`

Each is a single JSON file (the `--output` path uploaded verbatim). Download and inspect to debug a failure or to compare values across runs.

## 7. CI: pushing to a feature branch (no PR yet)

```sh
git push origin 006-ci-eval-gates
```

The Actions tab shows **one** check: `lint-test-build`. Per the trigger policy (R7 in `research.md`), eval jobs do not run on feature-branch pushes. Open a PR or push to `main` to see them run.

## 8. Owner handoff: replacing a mock with a real evaluator

When Ayoub (for classifier / red-team / redaction) or Nasser (for rag / agent-tool) is ready to ship the real CLI:

1. Replace the contents of `evals/<gate>.py` with the real evaluator.
2. The real evaluator MUST satisfy [`contracts/eval-cli.md`](contracts/eval-cli.md) exactly — same module path, same `--output <path>` flag, same JSON shape.
3. The real evaluator MUST NOT emit `"_mock": true` in its JSON.
4. The real evaluator MUST NOT print `MOCK EVALUATOR` to stderr.
5. No change to `.github/workflows/ci.yml` is needed — the wiring is identical.
6. No change to `scripts/check_threshold.py` is needed — the contract is identical.
7. The PR replacing the mock SHOULD update `DECISIONS.md` to note that the mock is retired.

## 9. Verifying SC-005 (no drift between workflow and thresholds)

```sh
# List gates referenced in eval_thresholds.yaml.
python - <<'PY'
import yaml
with open("eval_thresholds.yaml") as f:
    t = yaml.safe_load(f)
for gate, metrics in t.items():
    for m in metrics:
        print(f"{gate}.{m}")
PY
# classifier.macro_f1_min
# agent_tool_selection.accuracy_min
# rag.hit_at_5_min
# rag.faithfulness_min
# red_team.required_refusal_rate
# redaction.required_secret_leak_count

# Cross-check against the ci.yml jobs (manual): five jobs, six (gate, metric) checks
# because rag-eval runs two threshold checks against one JSON file.
```

If the two lists ever drift, this PR's SC-005 was violated and a follow-up patch is required.

## 10. Verifying SC-006 (no eval runs on feature-branch pushes)

After pushing the branch but before opening a PR, open the latest workflow run. Confirm only `lint-test-build` ran. Then open the PR and confirm all six checks appear.
