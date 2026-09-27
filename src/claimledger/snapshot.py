import json
from datetime import datetime
from pathlib import Path

from claimledger.domain import ProductCandidate


class SnapshotError(ValueError):
    pass


def parse_aware_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SnapshotError(f"{label} is not an ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SnapshotError(f"{label} must include a timezone")
    return parsed


def load_c003_snapshot(path: Path, retrieved_at: datetime) -> list[ProductCandidate]:
    """Load the six-field C003 JSONL snapshot with the caller-supplied retrieval time."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise SnapshotError("retrieved_at must include a timezone")
    products: list[ProductCandidate] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                products.append(
                    ProductCandidate(**json.loads(line), source_id="C003", retrieved_at=retrieved_at)
                )
    return products


__all__ = ["SnapshotError", "load_c003_snapshot", "parse_aware_datetime"]
