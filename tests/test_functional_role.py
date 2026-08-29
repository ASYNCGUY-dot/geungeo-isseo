import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from claimledger.extension_selection import COMPARISON_GROUPS
from claimledger.functional_role import (
    FunctionalRoleRuleRegistry,
    load_functional_role_registry,
)

NOW = datetime(2026, 8, 30, tzinfo=UTC)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "functional_role_rules.json"


def _fixture_data() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _write_registry(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "functional-role-rules.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _load(tmp_path: Path, data: dict[str, object]) -> FunctionalRoleRuleRegistry:
    return load_functional_role_registry(_write_registry(tmp_path, data), evaluated_at=NOW)


def test_load_functional_role_registry_accepts_exact_current_five_group_contract() -> None:
    registry = load_functional_role_registry(FIXTURE_PATH, evaluated_at=NOW)

    assert registry.contract_version == "functional-role-rules-v1"
    assert tuple(rule.group for rule in registry.rules) == COMPARISON_GROUPS
    assert all(rule.status.value == "active" for rule in registry.rules)
    assert all(rule.content_sha256.isupper() for rule in registry.rules)
    with pytest.raises(ValueError):
        registry.rules[0].source_id = "mutated"


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered"])
def test_registry_rejects_a_missing_or_duplicate_comparison_group(
    tmp_path: Path,
    mutation: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    if mutation == "missing":
        rules.pop()
    elif mutation == "duplicate":
        rules[-1]["group"] = "milk_thistle"
    else:
        rules.reverse()

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "proposed"),
        ("status", "expired"),
        ("effective_to", "2026-08-29"),
        ("effective_from", "2026-08-31"),
    ],
)
def test_registry_rejects_proposed_expired_or_not_yet_effective_rules(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0][field] = value

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verified_current_at", "2026-08-22T23:59:59Z"),
        ("verified_current_at", "2026-08-30T00:00:01Z"),
    ],
)
def test_registry_rejects_stale_or_future_verification_times(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0][field] = value

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    "source_url",
    [
        "ftp://www.mfds.go.kr/synthetic-fixture/rule",
        "https://mfds.go.kr.attacker.example/synthetic-fixture/rule",
        "https://user:password@www.mfds.go.kr/synthetic-fixture/rule",
        "https://www.mfds.go.kr/synthetic-fixture/rule#fragment",
        "https://www.mfds.go.kr:not-a-port/synthetic-fixture/rule",
        "https://example.test/synthetic-fixture/rule",
    ],
)
def test_registry_rejects_non_official_or_non_http_sources(
    tmp_path: Path,
    source_url: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0]["source_url"] = source_url

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize("content_sha256", ["a" * 64, "A" * 63, "G" * 64])
def test_registry_rejects_lowercase_or_non_sha256_content_hashes(
    tmp_path: Path,
    content_sha256: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0]["content_sha256"] = content_sha256

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accepted_functional_forms", []),
        ("recognized_function_texts", []),
        ("accepted_functional_forms", ["홍삼농축액", "  가  "]),
        ("accepted_functional_forms", ["홍삼농축액", "가"]),
        ("recognized_function_texts", ["간 건강", "간   건강"]),
        ("recognized_function_texts", ["간 건강", "간 건강"]),
    ],
)
def test_registry_rejects_empty_unsorted_or_duplicate_phrase_lists(
    tmp_path: Path,
    field: str,
    value: list[str],
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0][field] = value

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_id", "=HYPERLINK(\"bad\")"),
        ("source_id", "  =HYPERLINK(bad)"),
        ("canonical_ingredient", "+SUM(1,1)"),
        ("source_locator", "api_key=live-secret-value-123456"),
        ("source_locator", "FOOD_SAFETY_API_KEY"),
        ("extracted_by", "sk-proj-abcdefghijklmnop"),
    ],
)
def test_registry_rejects_formula_prefixes_and_secret_patterns(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    data = _fixture_data()
    rules = data["rules"]
    assert isinstance(rules, list)
    rules[0][field] = value

    with pytest.raises(ValueError):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("extra_rule", "unused"),
        ("extra_registry", "unused"),
        ("naive_datetime", "retrieved_at"),
        ("naive_evaluated_at", ""),
    ],
)
def test_registry_rejects_extra_fields_and_naive_datetimes(
    tmp_path: Path,
    mutation: str,
    field: str,
) -> None:
    data = copy.deepcopy(_fixture_data())
    rules = data["rules"]
    assert isinstance(rules, list)
    if mutation == "extra_rule":
        rules[0][field] = "not allowed"
    elif mutation == "extra_registry":
        data[field] = "not allowed"
    elif mutation == "naive_datetime":
        rules[0][field] = "2026-08-30T00:00:00"
    else:
        with pytest.raises(ValueError):
            load_functional_role_registry(
                _write_registry(tmp_path, data),
                evaluated_at=datetime(2026, 8, 30),  # noqa: DTZ001
            )
        return

    with pytest.raises(ValidationError):
        _load(tmp_path, data)
