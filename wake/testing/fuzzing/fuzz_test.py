from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict, List, Optional, Any

from typing_extensions import get_type_hints

from wake.development.globals import random, set_sequence_initial_internal_state, get_fuzz_mode, get_sequence_initial_internal_state, set_error_flow_num, get_error_flow_num

from ..core import get_connected_chains
from .generators import generate

import pickle
from dataclasses import dataclass

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
        fuzz_mode = get_fuzz_mode()
        if fuzz_mode == 0:
            for i in range(sequences_count):
                flows_counter: DefaultDict[Callable, int] = defaultdict(int)
                invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(
                    int
                )

                snapshots = [chain.snapshot() for chain in chains]

                set_sequence_initial_internal_state(
                        pickle.dumps(
                        random.getstate()
                    )
                )

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
                    set_error_flow_num(j)
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

        elif(fuzz_mode == 1):
            print("fuzz test shrink start! First of all correct random and flow information!!! >_<")

            @dataclass
            class FlowState:
                random_state: bytes
                flow_num: int
                flow_name: str
                flow: Callable  # Store the function itself
                flow_params: List[Any]  # Store the list of arguments
                required: bool = True
                before_inv_random_state: bytes = b""

            error_flow_num = get_error_flow_num()
            flow_state: List[FlowState] = []

            flows_counter: DefaultDict[Callable, int] = defaultdict(int)
            invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(
                int
            )

            snapshots = [chain.snapshot() for chain in chains]

            initial_state = get_sequence_initial_internal_state()
            random.setstate(pickle.loads(initial_state))

            self._flow_num = 0
            self._sequence_num = 0
            self.pre_sequence()

            exception = False
            try:
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
                    random_state = pickle.dumps(random.getstate())
                    flow_state.append(FlowState(
                        random_state=random_state,
                        flow_name=flow.__name__,
                        flow=flow,
                        flow_params=flow_params,
                        flow_num=j
                    ))

                    self._flow_num = j
                    self.pre_flow(flow)
                    flow(self, *flow_params)
                    flows_counter[flow] += 1
                    self.post_flow(flow)

                    flow_state[j].before_inv_random_state = pickle.dumps(random.getstate())

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
            except Exception:
                exception = True

                for snapshot, chain in zip(snapshots, chains):
                    chain.revert(snapshot)

                assert self._flow_num == error_flow_num, "Unexpected failing flow"
            if exception == False:
                raise Exception("Exception not raised unexpected state changes")

            print("Random state corrected: ", error_flow_num)
            print("Starting shrinking")

            curr = 0 # current testing flow index

            class OverRunException(Exception):
                def __init__(self):
                    super().__init__("Overrun")

            while curr <= error_flow_num:
                assert flow_state[curr].required == True
                flow_state[curr].required = False
                flows_counter: DefaultDict[Callable, int] = defaultdict(int)
                invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(
                    int
                )
                snapshots = [chain.snapshot() for chain in chains]


                random.setstate(pickle.loads(initial_state))

                self._flow_num = 0
                self._sequence_num = 0
                self.pre_sequence()
                exception = False
                try:
                    for j in range(flows_count):

                        print(j, " ", error_flow_num)
                        if j > error_flow_num:
                            raise OverRunException()

                        print(j, "th flow")
                        curr_flow_state = flow_state[j]
                        random.setstate(pickle.loads(curr_flow_state.random_state))
                        flow = curr_flow_state.flow
                        flow_params = curr_flow_state.flow_params


                        if flow_state[j].required:
                            self._flow_num = j
                            self.pre_flow(flow)
                            flow(self, *flow_params)
                            flows_counter[flow] += 1
                            self.post_flow(flow)
                            print(flow.__name__, ": is executed")
                        else:
                            print("skip flow")

                        assert flow_state[j].before_inv_random_state is not None
                        random.setstate(pickle.loads(curr_flow_state.before_inv_random_state))
                        print("flow executed")
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
                        print(f"success {j} th")
                    self.post_sequence()
                except OverRunException:
                    print("overrun")
                    exception = False # since it is not test exception
                except Exception as e:
                    exception = True
                    print("exception in ", j)
                    for snapshot, chain in zip(snapshots, chains):
                        chain.revert(snapshot)

                    if self._flow_num == error_flow_num:
                        # the removed flow is not required to reproduce same error. @ try remove next flow
                        print("remove worked!!, ", curr)
                        assert flow_state[curr].required == False
                    else:
                        print(e)
                        # the removing flow caused different error . @this flow should not removed restore current flow and remove next flow
                        flow_state[curr].required = True

                        print("remove failed!!, ", curr)

                if exception == False:
                    for snapshot, chain in zip(snapshots, chains):
                        chain.revert(snapshot)

                    print("probably overrun!")
                    flow_state[curr].required = True
                    # the removed flow is required to reproduce same error. @ this flow should not removed # restore current flow and remove next flow

                print("True!!", flow_state[curr].required, curr)
                curr += 1




            print("Shrinking completed")
            print("Error flow number: ", error_flow_num)
            print("Shrinked flow count:", sum([1 for i in range(len(flow_state)) if flow_state[i].required == True]))
            print("Those flow were required to reproduce the error")
            for i in range(len(flow_state)):
                if flow_state[i].required:
                    print(flow_state[i].flow_name, " : ", flow_state[i].flow_params)



        else:
            raise Exception("Invalid fuzz mode")

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
