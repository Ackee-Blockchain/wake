from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict, List, Optional, Any

from typing_extensions import get_type_hints

from wake.development.globals import random, set_sequence_initial_internal_state, get_fuzz_mode, get_sequence_initial_internal_state, set_error_flow_num, get_error_flow_num, get_config, get_shrinked_path

from ..core import get_connected_chains
from .generators import generate

import pickle
from dataclasses import dataclass

from wake.utils.file_utils import is_relative_to
from pathlib import Path
from datetime import datetime

import traceback

from wake.development.transactions import Error

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

@dataclass
class FlowState:
    random_state: bytes
    flow_num: int
    flow_name: str
    flow: Callable  # Store the function itself
    flow_params: List[Any]  # Store the list of arguments
    required: bool = True
    before_inv_random_state: bytes = b""



@dataclass
class ShrinkedInfoFile:
    initial_state: bytes
    required_flows: List[FlowState]


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
            exception_content = None
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
            except Exception as e:
                exception_content = e
                print(type(e))
                print(e)

                ## LOGGING EXCEPTION RESULT
                # It could log only flow number,
                # but ideally, it should log the lines of code in the test.

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

                print("Shrinking flow: ", curr)

                print("progress: ", (curr* 100) / (error_flow_num+1), "%")
                random.setstate(pickle.loads(initial_state))

                self._flow_num = 0
                self._sequence_num = 0
                self.pre_sequence()
                exception = False
                try:
                    for j in range(flows_count):

                        if j > error_flow_num:
                            raise OverRunException()

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


                        assert flow_state[j].before_inv_random_state is not None
                        random.setstate(pickle.loads(curr_flow_state.before_inv_random_state))
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
                except OverRunException:
                    exception = False # since it is not test exception
                except Exception as e:
                    exception = True
                    for snapshot, chain in zip(snapshots, chains):
                        chain.revert(snapshot)

                    def compare_exceptions(e1, e2):
                        if type(e1) != type(e2):
                            # print("type not equal")
                            return False

                        if type(e1) == Error and type(e2) == Error:
                            # if error was transaction message error the compare message content as well
                            if e1.message != e2.message:
                                return False

                        tb1 = traceback.extract_tb(e1.__traceback__)
                        tb2 = traceback.extract_tb(e2.__traceback__)
                        frames_up = 0
                        frame1 = None
                        for frame1 in tb1:
                            if is_relative_to(
                                Path(frame1.filename), Path.cwd()
                            ) and not is_relative_to(
                                Path(frame1.filename), Path().cwd() / "pytypes"
                            ):
                                break
                        frame2 = None
                        for frame2 in tb1:
                            if is_relative_to(
                                Path(frame2.filename), Path.cwd()
                            ) and not is_relative_to(
                                Path(frame2.filename), Path().cwd() / "pytypes"
                            ):
                                break

                        # print(frame1)
                        # print(frame2)
                        if frame1 is None or frame2 is None:
                            print("frame is none!!!!!!!!!!!!!!")
                            # return False
                        if frame1 is not None and frame2 is not None and (frame1.filename != frame2.filename
                                or  frame1.lineno != frame2.lineno
                                or frame1.name != frame2.name
                                ):
                            return False
                        return True

                    # Check exception type and exception lines in the testing file.
                    ignore_flows = True

                    if (ignore_flows or self._flow_num == error_flow_num) and compare_exceptions(e, exception_content):

                        # the removed flow is not required to reproduce same error. @ try remove next flow
                        print("remove worked!!")
                        assert flow_state[curr].required == False
                    else:
                        print(e)
                        # the removing flow caused different error . @this flow should not removed restore current flow and remove next flow
                        flow_state[curr].required = True

                        print("remove failed!!")

                if exception == False:
                    for snapshot, chain in zip(snapshots, chains):
                        chain.revert(snapshot)

                    print("probably overrun!")
                    flow_state[curr].required = True
                    # the removed flow is required to reproduce same error. @ this flow should not removed # restore current flow and remove next flow
                curr += 1

            print("Shrinking completed")
            print("Error flow number: ", error_flow_num)
            print("Shrinked flow count:", sum([1 for i in range(len(flow_state)) if flow_state[i].required == True]))
            print("Those flow were required to reproduce the error")
            for i in range(len(flow_state)):
                if flow_state[i].required:
                    print(flow_state[i].flow_name, " : ", flow_state[i].flow_params)


            crash_logs_dir = get_config().project_root_path / ".wake" / "logs" / "shrinked"
            # shutil.rmtree(crash_logs_dir, ignore_errors=True)
            crash_logs_dir.mkdir(parents=True, exist_ok=True)
            # write crash log file.
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # Assuming `call.execinfo` contains the crash information
            crash_log_file = crash_logs_dir / F"{timestamp}.bin"


            #initial_state

            required_flows: List[FlowState] = []
            for i in range(len(flow_state)):
                if flow_state[i].required:
                    required_flows.append(flow_state[i])

            store_data: ShrinkedInfoFile = ShrinkedInfoFile(
                initial_state=initial_state,
                required_flows=required_flows
            )
            # Write to a JSON file
            with open(crash_log_file, 'wb') as f:
                pickle.dump(store_data, f)

            print(f"shrinked file written to {crash_log_file}")

        elif fuzz_mode == 2:

            shrinked_path = get_shrinked_path()
            if shrinked_path is None:
                raise Exception("Shrinked path not found")
            with open(shrinked_path, 'rb') as f:
                 store_data: ShrinkedInfoFile = pickle.load(f)

            self._flow_num = 0
            self._sequence_num = 0
            self.pre_sequence()
            flows: List[Callable] = self.__get_methods("flow")

            invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(
                int
            )
            for j in range(len(store_data.required_flows)):
                flow = next((flow for flow in flows if store_data.required_flows[j].flow_name == flow.__name__), None)
                if flow is None:
                    raise Exception("Flow not found")
                flow_params = store_data.required_flows[j].flow_params

                random.setstate(pickle.loads(store_data.required_flows[j].random_state))
                self.pre_flow(flow)
                flow(self, *flow_params)
                self.post_flow(flow)
                random.setstate(pickle.loads(store_data.required_flows[j].before_inv_random_state))
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
