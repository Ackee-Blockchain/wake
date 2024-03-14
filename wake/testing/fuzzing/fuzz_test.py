from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict, List, Optional

from typing_extensions import get_type_hints

from wake.development.globals import random

from ..core import get_connected_chains
from .generators import generate


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

    def __get_methods(self, attr: str) -> List[Callable]:
        ret = []
        for x in dir(self):
            if hasattr(self.__class__, x):
                m = getattr(self.__class__, x)
                if hasattr(m, attr) and getattr(m, attr):
                    ret.append(m)
        return ret

    def run(
        self,
        sequences_count: int,
        flows_count: int,
        *,
        dry_run: bool = False,
    ):
        chains = get_connected_chains()

        flows: List[Callable] = self.__get_methods("flow")
        invariants: List[Callable] = self.__get_methods("invariant")

        for i in range(sequences_count):
            flows_counter: DefaultDict[Callable, int] = defaultdict(int)
            invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(
                int
            )

            snapshots = [chain.snapshot() for chain in chains]
            self._flow_num = 0
            self._sequence_num = i
            self.pre_sequence()

            for j in range(flows_count):
                valid_flows = [
                    f
                    for f in flows
                    if (
                        not hasattr(f, "max_times")
                        or flows_counter[f] < getattr(f, "max_times")
                    )
                    and (
                        not hasattr(f, "precondition")
                        or getattr(f, "precondition")(self)
                    )
                ]
                weights = [getattr(f, "weight") for f in valid_flows]
                if len(valid_flows) == 0:
                    max_times_flows = [
                        f
                        for f in flows
                        if hasattr(f, "max_times")
                        and flows_counter[f] >= getattr(f, "max_times")
                    ]
                    precondition_flows = [
                        f
                        for f in flows
                        if hasattr(f, "precondition")
                        and not getattr(f, "precondition")(self)
                    ]
                    raise Exception(
                        f"Could not find a valid flow to run.\nFlows that have reached their max_times: {max_times_flows}\nFlows that do not satisfy their precondition: {precondition_flows}"
                    )
                flow = random.choices(valid_flows, weights=weights)[0]
                flow_params = [
                    generate(v)
                    for k, v in get_type_hints(flow, include_extras=True).items()
                    if k != "return"
                ]

                self._flow_num = j
                self.pre_flow(flow)
                flow(self, *flow_params)
                flows_counter[flow] += 1
                self.post_flow(flow)

                if not dry_run:
                    self.pre_invariants()
                    for inv in invariants:
                        if invariant_periods[inv] == 0:
                            self.pre_invariant(inv)
                            inv(self)
                            self.post_invariant(inv)

                        invariant_periods[inv] += 1
                        if invariant_periods[inv] == getattr(inv, "period"):
                            invariant_periods[inv] = 0
                    self.post_invariants()

            self.post_sequence()

            for snapshot, chain in zip(snapshots, chains):
                chain.revert(snapshot)

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
