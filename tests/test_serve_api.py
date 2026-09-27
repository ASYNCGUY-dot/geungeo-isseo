import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claimledger.snapshot import SnapshotError
from scripts import serve_api


def _export(path: Path) -> Path:
    row = {
        "report_no": "R1",
        "name": "루테인",
        "company": "가",
        "primary_function": "[루테인] 노화로 인해 감소될 수 있는 황반색소밀도를 유지하여 눈 건강에 도움을 줄 수 있음",
        "raw_materials": "마리골드꽃추출물",
        "intake_method": "1일 1회",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_build_app_loads_snapshot_with_given_time(tmp_path: Path) -> None:
    args = serve_api.parse_args(
        ["--source-export", str(_export(tmp_path / "e.jsonl")), "--source-retrieved-at", "2026-08-27T12:42:29+00:00"]
    )

    body = TestClient(serve_api.build_app(args)).get("/api/v1/health").json()

    assert args.host == "127.0.0.1"
    assert body["product_count"] == 1
    assert body["source_retrieved_at"] == "2026-08-27T12:42:29+00:00"


def test_main_runs_uvicorn_on_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(serve_api.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))

    code = serve_api.main(
        ["--source-export", str(_export(tmp_path / "e.jsonl")), "--source-retrieved-at", "2026-08-27T12:42:29+00:00"]
    )

    assert code == 0
    assert calls == [{"host": "127.0.0.1", "port": 8000}]


def test_build_app_rejects_naive_time(tmp_path: Path) -> None:
    args = serve_api.parse_args(
        ["--source-export", str(_export(tmp_path / "e.jsonl")), "--source-retrieved-at", "2026-08-27T12:42:29"]
    )

    with pytest.raises(SnapshotError):
        serve_api.build_app(args)
