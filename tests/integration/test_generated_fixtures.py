# tests/integration/test_generated_fixtures.py

from __future__ import annotations

from pathlib import Path

from heic_jpg_tidy.models import Decision, ReasonCode, RuleConfig
from heic_jpg_tidy.scanner import find_file_groups
from heic_jpg_tidy.workflow import evaluate_groups

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "generated"


def evaluate_fixture(name: str, config: RuleConfig | None = None):
    groups = find_file_groups(FIXTURES_ROOT / name)
    return evaluate_groups(groups, config or RuleConfig())


def test_matching_pair_is_move_candidate() -> None:
    result = evaluate_fixture("matching_pair")

    assert len(result.evaluations) == 1
    assert result.evaluations[0].decision is Decision.MOVE_CANDIDATE
    assert result.evaluations[0].reason_codes == (ReasonCode.MATCH_CONFIRMED,)


def test_dimensions_mismatch_requires_review() -> None:
    result = evaluate_fixture("dimensions_mismatch")

    assert len(result.evaluations) == 1
    assert result.evaluations[0].decision is Decision.REVIEW
    assert result.evaluations[0].reason_codes == (ReasonCode.DIMENSIONS_MISMATCH,)


def test_datetime_mismatch_requires_review() -> None:
    result = evaluate_fixture("datetime_mismatch")

    assert len(result.evaluations) == 1
    assert result.evaluations[0].decision is Decision.REVIEW
    assert result.evaluations[0].reason_codes == (ReasonCode.DATETIME_MISMATCH,)


def test_ambiguous_group_is_not_evaluated_as_a_pair() -> None:
    result = evaluate_fixture("ambiguous_group")

    assert result.evaluations == ()
    assert len(result.ambiguous_groups) == 1


def test_corrupt_jpg_becomes_image_read_error() -> None:
    result = evaluate_fixture("corrupt_pair")

    assert len(result.evaluations) == 1
    assert result.evaluations[0].decision is Decision.REVIEW
    assert result.evaluations[0].reason_codes == (ReasonCode.IMAGE_READ_ERROR,)
