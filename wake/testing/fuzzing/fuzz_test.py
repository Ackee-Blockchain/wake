from __future__ import annotations

from typing import Callable, Optional

def flow(
    *,
    weight: int = 100,
    max_times: Optional[int] = None,
    precondition: Optional[Callable[[FuzzTest], bool]] = None,
):
    def decorator(fn):
        fn.flow = True
        fn.weight = weight
        if max_times is not None:
            fn.max_times = max_times
        if precondition is not None:
            fn.precondition = precondition
        return fn

    return decorator


def invariant(*, period: int = 1):
    def decorator(fn):
        fn.invariant = True
        fn.period = period
        return fn

    return decorator


class FuzzTest:
    _sequence_num: int
    _flow_num: int

    @property
    def sequence_num(self):
        return self._sequence_num

    @property
    def flow_num(self):
        return self._flow_num

    @classmethod
    def run(
        cls,
        sequences_count: int,
        flows_count: int,
        *,
        dry_run: bool = False,
    ):
        from .fuzz_shrink import fuzz_shrink
        fuzz_shrink(cls, sequences_count, flows_count, dry_run)

    def pre_sequence(self) -> None:
        pass

    def post_sequence(self) -> None:
        pass

    def pre_flow(self, flow: Callable) -> None:
        pass

    def post_flow(self, flow: Callable) -> None:
        pass

    def pre_invariants(self) -> None:
        pass

    def post_invariants(self) -> None:
        pass

    def pre_invariant(self, invariant: Callable) -> None:
        pass

    def post_invariant(self, invariant: Callable) -> None:
        pass
