import unittest.mock
from typing import Dict

import pytest

from woke.testing.campaign import Methods, _generate_flows


def count_calls(methods: Methods) -> Dict[str, int]:
    return {method[1]: methods.count(method) for method in methods}


def run_and_count(methods: Methods, flows_count: int, run_count: int) -> Dict[str, int]:
    counts = {}
    for i in range(run_count):
        flows = _generate_flows(methods, flows_count, [])
        call_counts = count_calls(flows)
        for fnname in call_counts:
            if fnname not in counts:
                counts[fnname] = 0
            counts[fnname] += call_counts[fnname]
    return counts


def mock_fn(weight=None, min_times=None, max_times=None):
    fn = unittest.mock.MagicMock(
        weight=weight, min_times=min_times, max_times=max_times
    )
    if weight is None:
        del fn.weight
    if min_times is None:
        del fn.min_times
    if max_times is None:
        del fn.max_times
    return fn


@pytest.mark.slow
def test_no_weight():
    fn1 = mock_fn()
    fn2 = mock_fn()
    run_cnt = 10
    flow_cnt = 100

    with pytest.raises(ValueError):
        run_and_count([(fn1, "fn1"), (fn2, "fn2")], flow_cnt, run_cnt)


@pytest.mark.slow
def test_same_weight():
    fn1 = mock_fn(weight=10)
    fn2 = mock_fn(weight=10)
    run_cnt = 10
    flow_cnt = 100
    eps = 0.2

    counts = run_and_count([(fn1, "fn1"), (fn2, "fn2")], flow_cnt, run_cnt)
    assert (
        (flow_cnt * (1 - eps) / 2)
        < counts["fn1"] / run_cnt
        < (flow_cnt * (1 + eps) / 2)
    )
    assert (
        (flow_cnt * (1 - eps) / 2)
        < counts["fn2"] / run_cnt
        < (flow_cnt * (1 + eps) / 2)
    )


@pytest.mark.slow
def test_different_weight():
    fn1 = mock_fn(weight=1)
    fn2 = mock_fn(weight=4)
    run_cnt = 10
    flow_cnt = 100
    eps = 0.3

    counts = run_and_count([(fn1, "fn1"), (fn2, "fn2")], flow_cnt, run_cnt)
    assert (
        (flow_cnt * (1 - eps) / 5)
        < counts["fn1"] / run_cnt
        < (flow_cnt * (1 + eps) / 5)
    )
    assert (
        (flow_cnt * (1 - eps) * (4 / 5))
        < counts["fn2"] / run_cnt
        < (flow_cnt * (1 + eps) * (4 / 5))
    )


@pytest.mark.slow
def test_zero_weight():
    fn1 = mock_fn(weight=0)
    fn2 = mock_fn(weight=1)
    run_cnt = 10
    flow_cnt = 100

    counts = run_and_count([(fn1, "fn1"), (fn2, "fn2")], flow_cnt, run_cnt)
    assert "fn1" not in counts.keys()
    assert counts["fn2"] == flow_cnt * run_cnt


@pytest.mark.slow
def test_min_times():
    fn1 = mock_fn(weight=10, min_times=50)
    fn2 = mock_fn(weight=10)
    run_cnt = 10
    flow_cnt = 100
    eps = 0.3

    counts = run_and_count([(fn1, "fn1"), (fn2, "fn2")], flow_cnt, run_cnt)
    assert counts["fn1"] / run_cnt >= flow_cnt / 2
    assert (
        (flow_cnt * (1 - eps) / 2)
        < counts["fn1"] / run_cnt
        < (flow_cnt * (1 + eps) / 2)
    )
    assert (
        (flow_cnt * (1 - eps) / 2)
        < counts["fn2"] / run_cnt
        < (flow_cnt * (1 + eps) / 2)
    )


@pytest.mark.slow
def test_max_times():
    fn1 = mock_fn(weight=10, max_times=50)
    fn2 = mock_fn(weight=10)
    run_cnt = 10
    flow_cnt = 100
    eps = 0.3

    counts = run_and_count([(fn1, "fn1"), (fn2, "fn2")], flow_cnt, run_cnt)
    assert counts["fn1"] / run_cnt <= flow_cnt / 2
    assert (
        (flow_cnt * (1 - eps) / 2)
        < counts["fn1"] / run_cnt
        < (flow_cnt * (1 + eps) / 2)
    )
    assert (
        (flow_cnt * (1 - eps) / 2)
        < counts["fn2"] / run_cnt
        < (flow_cnt * (1 + eps) / 2)
    )


@pytest.mark.slow
def test_zero_weight_min_times():
    fn1 = mock_fn(weight=0, min_times=50)
    fn2 = mock_fn(weight=10)
    run_cnt = 10
    flow_cnt = 100
    eps = 0.3

    counts = run_and_count([(fn1, "fn1"), (fn2, "fn2")], flow_cnt, run_cnt)
    assert counts["fn1"] / run_cnt == flow_cnt / 2
    assert (
        (flow_cnt * (1 - eps) / 2)
        < counts["fn2"] / run_cnt
        < (flow_cnt * (1 + eps) / 2)
    )


@pytest.mark.slow
def test_small_weight_min_times():
    fn1 = mock_fn(weight=1, min_times=50)
    fn2 = mock_fn(weight=10)
    run_cnt = 10
    flow_cnt = 100
    eps = 0.3

    counts = run_and_count([(fn1, "fn1"), (fn2, "fn2")], flow_cnt, run_cnt)
    assert counts["fn1"] / run_cnt >= flow_cnt / 2
    assert (
        (flow_cnt * (1 - eps) / 2)
        < counts["fn2"] / run_cnt
        < (flow_cnt * (1 + eps) / 2)
    )


@pytest.mark.slow
def test_multiple_weights():
    fn1 = mock_fn(weight=1)
    fn2 = mock_fn(weight=1)
    fn3 = mock_fn(weight=1)
    fn4 = mock_fn(weight=1)
    fn5 = mock_fn(weight=1)
    run_cnt = 10
    flow_cnt = 200
    eps = 0.2

    counts = run_and_count(
        [(fn1, "fn1"), (fn2, "fn2"), (fn3, "fn3"), (fn4, "fn4"), (fn5, "fn5")],
        flow_cnt,
        run_cnt,
    )

    assert (
        (flow_cnt * (1 - eps) / 5)
        < counts["fn1"] / run_cnt
        < (flow_cnt * (1 + eps) / 5)
    )
    assert (
        (flow_cnt * (1 - eps) / 5)
        < counts["fn2"] / run_cnt
        < (flow_cnt * (1 + eps) / 5)
    )
    assert (
        (flow_cnt * (1 - eps) / 5)
        < counts["fn3"] / run_cnt
        < (flow_cnt * (1 + eps) / 5)
    )
    assert (
        (flow_cnt * (1 - eps) / 5)
        < counts["fn4"] / run_cnt
        < (flow_cnt * (1 + eps) / 5)
    )
    assert (
        (flow_cnt * (1 - eps) / 5)
        < counts["fn5"] / run_cnt
        < (flow_cnt * (1 + eps) / 5)
    )
