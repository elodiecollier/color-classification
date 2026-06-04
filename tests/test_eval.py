"""Tests for the accuracy harness (cli/eval) — pure scoring + label integrity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli.eval import (
    CaseResult,
    accuracy,
    confusions,
    evaluate,
    per_bucket_recall,
    to_buckets,
)
from core.models import ColorBucket

B = ColorBucket


def _result(expected, actual):
    return CaseResult("img", frozenset(expected), frozenset(actual))


def test_to_buckets_validates():
    assert to_buckets(["green", "blue"]) == frozenset({B.GREEN, B.BLUE})
    with pytest.raises(ValueError):
        to_buckets(["mauve"])  # not in the taxonomy


def test_evaluate_scores_exact_set_match():
    cases = [
        {"image": "a", "expected": ["green"]},
        {"image": "b", "expected": ["black", "white"]},
        {"image": "c", "expected": ["brown"]},
    ]
    actual = {
        "a": frozenset({B.GREEN}),            # exact -> ok
        "b": frozenset({B.WHITE, B.BLACK}),   # set-equal regardless of order -> ok
        "c": frozenset({B.ORANGE}),           # wrong -> not ok
    }
    results = evaluate(cases, lambda case: actual[case["image"]])
    assert [r.ok for r in results] == [True, True, False]
    assert accuracy(results) == pytest.approx(2 / 3)


def test_accuracy_empty_is_zero():
    assert accuracy([]) == 0.0


def test_per_bucket_recall():
    results = [
        _result([B.GREEN], [B.GREEN]),          # green hit
        _result([B.BROWN], [B.ORANGE]),         # brown missed
        _result([B.BLACK, B.WHITE], [B.BLACK]),  # black hit, white missed
    ]
    recall = per_bucket_recall(results)
    assert recall[B.GREEN] == (1, 1)
    assert recall[B.BROWN] == (0, 1)
    assert recall[B.BLACK] == (1, 1)
    assert recall[B.WHITE] == (0, 1)


def test_confusions_count_substitutions():
    results = [
        _result([B.BROWN], [B.ORANGE]),   # brown -> orange
        _result([B.BROWN], [B.ORANGE]),   # brown -> orange (again)
        _result([B.GREEN], [B.GREEN]),    # correct -> no confusion
        _result([B.GREEN, B.BLUE], [B.GREEN]),  # blue missed but no substitute -> no pair
    ]
    conf = confusions(results)
    assert conf[(B.BROWN, B.ORANGE)] == 2
    assert (B.GREEN, B.BLUE) not in conf  # miss-without-substitute isn't a confusion
    assert sum(conf.values()) == 2


def test_real_labels_are_valid_and_images_exist():
    cases = json.loads(Path("fixtures/eval_labels.json").read_text())
    assert len(cases) >= 10
    for case in cases:
        to_buckets(case["expected"])  # every expected label is a real bucket
        assert (Path("fixtures/images") / case["image"]).exists(), case["image"]
