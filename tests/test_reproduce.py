"""Tests for the one-command reproducible run (no network, subprocesses are faked)."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import reproduce

RETRIEVED_AT = "2026-08-27T12:42:29.050550+00:00"


def _snapshot(tmp_path: Path, content: bytes = b'{"report_no": "1"}\n') -> tuple[Path, Path]:
    export = tmp_path / "c003.jsonl"
    export.write_bytes(content)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"source": {
        "sha256": hashlib.sha256(b'{"report_no": "1"}\n').hexdigest().upper(), "retrieved_at": RETRIEVED_AT,
    }}), encoding="utf-8")
    return export, manifest


def _run(tmp_path: Path, export: Path, manifest: Path, failing: tuple[str, ...] = ()) -> tuple[int, list[list[str]]]:
    calls: list[list[str]] = []

    def fake(argv: list[str], **_: object) -> SimpleNamespace:
        calls.append(argv)
        return SimpleNamespace(returncode=1 if any(mark in " ".join(argv) for mark in failing) else 0)

    code = reproduce.main([
        "--source-export", str(export), "--snapshot-manifest", str(manifest),
        "--output-dir", str(tmp_path / "out"),
    ], run=fake)
    return code, calls


def test_a_different_snapshot_stops_before_any_step(tmp_path: Path) -> None:
    export, manifest = _snapshot(tmp_path, content=b"another file\n")
    code, calls = _run(tmp_path, export, manifest)
    assert code == 3 and calls == []
    missing, _ = _run(tmp_path, tmp_path / "absent.jsonl", manifest)
    assert missing == 3


def test_all_gates_run_with_the_manifest_retrieval_time(tmp_path: Path) -> None:
    export, manifest = _snapshot(tmp_path)
    code, calls = _run(tmp_path, export, manifest)
    joined = [" ".join(call).replace("\\", "/") for call in calls]
    assert code == 0
    assert any("-m pytest" in call for call in joined)
    claim = [call for call in joined if "claim-eval-v2/cases.json" in call]
    assert len(claim) == 1 and "--require-zero-false-clearance" in claim[0] and RETRIEVED_AT in claim[0]
    ads = [call for call in joined if "claim-eval-v3/cases.json" in call]
    assert len(ads) == 1 and "score_ad_eval.py" in ads[0] and "--require-zero-false-clearance" in ads[0]
    assert RETRIEVED_AT in ads[0]
    attribution = [call for call in joined if "score_attribution_eval.py" in call]
    assert len(attribution) == 6 and all("--require-zero-false-attribution" in call for call in attribution)
    dev = [call for call in joined if "core-mvp-dev-v1.json" in call]
    assert len(dev) == 1 and "--require-zero-false-clearance" not in dev[0]
    summary = json.loads((tmp_path / "out" / "reproduce-summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True and summary["snapshot_sha256"] == hashlib.sha256(export.read_bytes()).hexdigest().upper()
    assert summary["steps"][0]["name"] == "unit tests"


def test_only_gated_steps_decide_the_exit_code(tmp_path: Path) -> None:
    export, manifest = _snapshot(tmp_path)
    assert _run(tmp_path, export, manifest, failing=("core-mvp-dev-v1.json",))[0] == 0
    code, calls = _run(tmp_path, export, manifest, failing=("claim-eval-v2/cases.json", "claim-eval-v2\\cases.json"))
    assert code == 1
    # Later steps still run so the summary shows every result.
    assert any("core-mvp-dev-v1.json" in " ".join(call) for call in calls)
    summary = json.loads((tmp_path / "out" / "reproduce-summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] is False


def test_tests_can_be_skipped(tmp_path: Path) -> None:
    export, manifest = _snapshot(tmp_path)
    calls: list[list[str]] = []
    code = reproduce.main([
        "--source-export", str(export), "--snapshot-manifest", str(manifest),
        "--output-dir", str(tmp_path / "out"), "--skip-tests",
    ], run=lambda argv, **_: calls.append(argv) or SimpleNamespace(returncode=0))
    # The temporary path itself contains "pytest", so match the module invocation.
    assert code == 0 and calls and not any("-m pytest" in " ".join(call) for call in calls)
