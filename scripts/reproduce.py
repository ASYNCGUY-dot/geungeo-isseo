"""Run every reproducible check in one command (the Docker image's verification entry point).

The C003 snapshot is not tracked, so its SHA-256 is compared with an evaluation manifest first; a
missing or different file stops the run. Then the unit tests, the attribution evaluation sets and
the independent claim-level set run with their zero-error gates. The development cases are scored
without a gate: five of their labels record the policy before headerless attribution.

Exit codes: 0 every gate passed, 1 a gate failed, 3 input error.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
ATTRIBUTION_LABELS = (
    ("attribution-eval-v1", "labels.csv"),
    ("attribution-eval-v1", "labels-independent.csv"),
    ("attribution-eval-v2", "labels-sonnet.csv"),
    ("attribution-eval-v2", "labels-opus.csv"),
    ("attribution-eval-v3", "labels-sonnet.csv"),
    ("attribution-eval-v3", "labels-opus.csv"),
)


class Step(NamedTuple):
    name: str
    argv: list[str]
    gate: bool


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the reproducible checks")
    parser.add_argument("--source-export", type=Path, default=ROOT / "data" / "c003-products.jsonl")
    parser.add_argument(
        "--snapshot-manifest", type=Path,
        default=ROOT / "data" / "eval" / "claim-eval-v2" / "manifest.json",
        help="evaluation manifest holding the expected snapshot hash and retrieval time",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "reproduce")
    parser.add_argument("--skip-tests", action="store_true")
    return parser.parse_args(argv)


def snapshot_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def steps(source_export: Path, retrieved_at: str, output_dir: Path, skip_tests: bool) -> list[Step]:
    python = sys.executable
    source = ["--source-export", str(source_export), "--source-retrieved-at", retrieved_at]
    evaluate = [python, str(ROOT / "scripts" / "evaluate_dev_cases.py")]
    planned: list[Step] = []
    if not skip_tests:
        planned.append(Step("unit tests", [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"], True))
    for eval_id, labels in ATTRIBUTION_LABELS:
        folder = ROOT / "data" / "eval" / eval_id
        planned.append(Step(
            f"{eval_id} {labels}",
            [
                python, str(ROOT / "scripts" / "score_attribution_eval.py"),
                "--manifest", str(folder / "manifest.json"), "--labels", str(folder / labels), *source,
                "--output", str(output_dir / f"{eval_id}-{Path(labels).stem}.json"),
                "--require-zero-false-attribution",
            ],
            True,
        ))
    planned.append(Step(
        "claim-eval-v2 (independent)",
        [
            *evaluate, "--cases", str(ROOT / "data" / "eval" / "claim-eval-v2" / "cases.json"), *source,
            "--output", str(output_dir / "claim-eval-v2.json"), "--require-zero-false-clearance",
        ],
        True,
    ))
    planned.append(Step(
        "claim-eval-v1 (development)",
        [
            *evaluate, "--cases", str(ROOT / "data" / "eval" / "claim-eval-v1" / "cases.json"), *source,
            "--output", str(output_dir / "claim-eval-v1.json"), "--require-zero-false-clearance",
        ],
        True,
    ))
    planned.append(Step(
        "dev cases (no gate, older-policy labels)",
        [
            *evaluate, "--cases", str(ROOT / "data" / "dev-cases" / "core-mvp-dev-v1.json"), *source,
            "--output", str(output_dir / "core-mvp-dev-v1.json"),
        ],
        False,
    ))
    return planned


def main(argv: Sequence[str] | None = None, run: Callable[..., object] = subprocess.run) -> int:
    args = parse_args(argv)
    try:
        expected = json.loads(args.snapshot_manifest.read_text(encoding="utf-8"))["source"]
        actual = snapshot_sha256(args.source_export)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}")
        return 3
    if actual != expected["sha256"]:
        print(f"error: snapshot hash {actual} differs from the manifest {expected['sha256']}")
        return 3
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for step in steps(args.source_export, expected["retrieved_at"], args.output_dir, args.skip_tests):
        print(f"== {step.name}", flush=True)
        code = run(step.argv, cwd=ROOT, stdout=subprocess.DEVNULL if step.name != "unit tests" else None).returncode
        results.append({"name": step.name, "gate": step.gate, "exit_code": code})
        print(f"   exit {code}{'' if step.gate else ' (not a gate)'}", flush=True)
    passed = all(result["exit_code"] == 0 for result in results if result["gate"])
    summary = {"passed": passed, "snapshot_sha256": actual, "retrieved_at": expected["retrieved_at"], "steps": results}
    (args.output_dir / "reproduce-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print("PASSED" if passed else "FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
