from __future__ import annotations


from collections import defaultdict
from typing import Callable, DefaultDict, List, Optional, Any, Tuple

from typing_extensions import get_type_hints

from wake.development.globals import random

from ..core import get_connected_chains
from .generators import generate

from dataclasses import dataclass

from .fuzz_test import FuzzTest

from wake.development.globals import random, set_sequence_initial_internal_state, get_fuzz_mode, get_sequence_initial_internal_state, set_error_flow_num, get_error_flow_num, get_config, get_shrinked_path

from wake.development.core import Chain
import pickle

from pathlib import Path
from datetime import datetime

import traceback
from wake.utils.file_utils import is_relative_to
from wake.development.transactions import Error
import copy


import os

from wake.cli.console import console
from contextlib import contextmanager, redirect_stdout, redirect_stderr




def __get_methods(target, attr: str) -> List[Callable]:
    ret = []
    for x in dir(target):
        if hasattr(target.__class__, x):
            m = getattr(target.__class__, x)
            if hasattr(m, attr) and getattr(m, attr):
                ret.append(m)
    return ret


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

    frame1 = None
    for frame1 in tb1:
        if is_relative_to(
            Path(frame1.filename), Path.cwd()
        ) and not is_relative_to(
            Path(frame1.filename), Path().cwd() / "pytypes"
        ):
            break
    frame2 = None
    for frame2 in tb2:
        if is_relative_to(
            Path(frame2.filename), Path.cwd()
        ) and not is_relative_to(
            Path(frame2.filename), Path().cwd() / "pytypes"
        ):
            break

    if frame1 is None or frame2 is None:
        print("frame is none!!!!!!!!!!!!!!")
        # return False
    if frame1 is not None and frame2 is not None and (frame1.filename != frame2.filename
            or  frame1.lineno != frame2.lineno
            or frame1.name != frame2.name
            ):
        return False
    return True


class StateSnapShot:
    _python_state: FuzzTest | None
    chain_states: List[str]
    flow_number: int | None # current flow number

    def __init__(self):
        self._python_state = None
        self.chain_states = []
        self.flow_number = None

    def take_snapshot(self, python_instance: FuzzTest, new_instance, chains: Tuple[Chain, ...], overwrite: bool):
        if not overwrite:
            assert self._python_state is None, "Python state already exists"
            assert self.chain_states == [], "Chain state already exists"
        else:
            assert self._python_state is not None, "No python state (snapshot)"
            assert self.chain_states != [], "No chain state"
            assert self.flow_number is not None, "No flow number"
            print("overwriting state ", self.flow_number, " to ", python_instance._flow_num)
        # assert self._python_state is None, "Python state already exists"

        self._python_state = new_instance

        self.flow_number = python_instance._flow_num
        self._python_state.__dict__.update(copy.deepcopy(python_instance.__dict__))
        self.chain_states = [chain.snapshot() for chain in chains]


    def revert(self, python_instance: FuzzTest, chains: Tuple[Chain, ...]):
        assert self.chain_states != [], "No chain snapshot"
        assert self._python_state is not None, "No python state"
        assert self.flow_number is not None, "No flow number"

        print("curr", python_instance._flow_num)
        print("new", self._python_state._flow_num)
        # assert python_instance._flow_num != self._python_state._flow_num, "Flow number mismatch"
        python_instance.__dict__.update(copy.deepcopy(self._python_state.__dict__))

        assert python_instance._flow_num == self._python_state._flow_num, "update failed"
        self._python_state = None

        for temp_chain, chain in zip(self.chain_states, chains):
            chain.revert(temp_chain)
        self.chain_states = []



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


def fuzz_shrink(test_class: type[FuzzTest], sequences_count: int, flows_count: int, dry_run: bool = False):
    assert issubclass(test_class, FuzzTest)
    fuzz_mode = get_fuzz_mode()
    if fuzz_mode == 0:
          # Instantiate the user-defined test class
        # Fetch connected chains and methods (flows and invariants)
        single_fuzz_test(test_class, sequences_count, flows_count, dry_run)
    elif fuzz_mode == 1:

        shrink_test(test_class, flows_count, dry_run)
        pass

    elif fuzz_mode == 2:
        shrank_reproduce(test_class, flows_count, dry_run)

def shrank_reproduce(test_class: type[FuzzTest], flows_count, dry_run: bool = False):
    test_instance = test_class()

    flows: List[Callable] = __get_methods(test_instance, "flow")
    invariants: List[Callable] = __get_methods(test_instance, "invariant")
    shrinked_path = get_shrinked_path()
    if shrinked_path is None:
        raise Exception("Shrinked path not found")
    with open(shrinked_path, 'rb') as f:
            store_data: ShrinkedInfoFile = pickle.load(f)

    test_instance._flow_num = 0
    test_instance._sequence_num = 0
    test_instance.pre_sequence()

    invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(
        int
    )
    for j in range(len(store_data.required_flows)):
        flow = next((flow for flow in flows if store_data.required_flows[j].flow_name == flow.__name__), None)
        if flow is None:
            raise Exception("Flow not found")
        flow_params = store_data.required_flows[j].flow_params

        random.setstate(pickle.loads(store_data.required_flows[j].random_state))
        test_instance.pre_flow(flow)
        flow(test_instance, *flow_params)
        test_instance.post_flow(flow)

        try:
            random.setstate(pickle.loads(store_data.required_flows[j].before_inv_random_state))
        except Exception as e:
            pass

        if not dry_run:
            test_instance.pre_invariants()
            for inv in invariants:
                if invariant_periods[inv] == 0:
                    test_instance.pre_invariant(inv)
                    inv(test_instance)
                    test_instance.post_invariant(inv)
                invariant_periods[inv] += 1
                if invariant_periods[inv] == getattr(inv, "period"):
                    invariant_periods[inv] = 0
            test_instance.post_invariants()

    print("seems fixed >_<")


def shrink_test(test_class: type[FuzzTest], flows_count, dry_run: bool = False):

    error_flow_num = get_error_flow_num() # argument
    print("Fuzz test shrink start! First of all, collect random and flow information!!! >_<")
    test_instance = test_class()
    chains = get_connected_chains()
    flows: List[Callable] = __get_methods(test_instance, "flow")
    invariants: List[Callable] = __get_methods(test_instance, "invariant")
    dry_run = False

    ctx_managers = []

    @contextmanager
    def print_ignore():
        ctx_managers.append(redirect_stdout(open(os.devnull, 'w')))
        ctx_managers.append(redirect_stderr(open(os.devnull, 'w')))
        for ctx_manager in ctx_managers:
            ctx_manager.__enter__()

        yield

        for ctx_manager in ctx_managers:
            ctx_manager.__exit__(None, None, None)
        ctx_managers.clear()

    flow_state: List[FlowState] = []

    flows_counter: DefaultDict[Callable, int] = defaultdict(int)
    invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)

    # Snapshot all connected chains
    initial_chain_state_snapshots = [chain.snapshot() for chain in chains]

    initial_state = get_sequence_initial_internal_state() # argument

    random.setstate(pickle.loads(initial_state))
    with print_ignore():
        test_instance._flow_num = 0
        test_instance.pre_sequence()

        exception = False
        exception_content = None
        try:
            with redirect_stdout(open(os.devnull, 'w')), redirect_stderr(open(os.devnull, 'w')):
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
                            or getattr(f, "precondition")(test_instance)
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
                            and not getattr(f, "precondition")(test_instance)
                        ]
                        raise Exception(
                            f"Could not find a valid flow to run.\nFlows that have reached their max_times: {max_times_flows}\nFlows that do not satisfy their precondition: {precondition_flows}"
                        )

                    # Pick a flow and generate the parameters
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

                    test_instance._flow_num = j
                    test_instance.pre_flow(flow)
                    flow(test_instance, *flow_params)  # Execute the selected flow
                    flows_counter[flow] += 1
                    test_instance.post_flow(flow)

                    flow_state[j].before_inv_random_state = pickle.dumps(random.getstate())

                    if not dry_run:
                        test_instance.pre_invariants()
                        for inv in invariants:
                            if invariant_periods[inv] == 0:
                                test_instance.pre_invariant(inv)
                                inv(test_instance)
                                test_instance.post_invariant(inv)

                            invariant_periods[inv] += 1
                            if invariant_periods[inv] == getattr(inv, "period"):
                                invariant_periods[inv] = 0
                        test_instance.post_invariants()
                test_instance.post_sequence()

        except Exception as e:
            exception_content = e
            print(type(e))
            print(e)
            exception = True
            assert test_instance._flow_num == error_flow_num, "Unexpected failing flow"
        finally:
            for snapshot, chain in zip(initial_chain_state_snapshots, chains):
                chain.revert(snapshot)
            initial_chain_state_snapshots = []
        if exception == False:
            raise Exception("Exception not raised unexpected state changes")


    console.print("Starting shrinking")

    curr = 0 # current testing flow index
    class OverRunException(Exception):
        def __init__(self):
            super().__init__("Overrun")

    random.setstate(pickle.loads(initial_state))

    with print_ignore():
        test_instance._flow_num = 0
        test_instance._sequence_num = 0
        test_instance.pre_sequence()

        states = StateSnapShot()
        states.take_snapshot(test_instance,test_class(), chains, overwrite=False)

    while curr <= error_flow_num:
        assert flow_state[curr].required == True
        flow_state[curr].required = False
        invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(
            int
        )
        console.print("progress: ", (curr* 100) / (error_flow_num+1), "%")
        exception = False
        with print_ignore():
            try:
                for j in range(curr-1, flows_count):

                    if j == -1: # this condition applies only curr == 0
                        continue

                    if j > error_flow_num:
                        raise OverRunException()

                    if j == curr:
                        states.take_snapshot(test_instance, test_class(), chains, overwrite=True)

                    print("flow: ", j, flow_state[j].flow.__name__ )

                    curr_flow_state = flow_state[j]
                    random.setstate(pickle.loads(curr_flow_state.random_state))
                    flow = curr_flow_state.flow
                    flow_params = curr_flow_state.flow_params


                    if flow_state[j].required:
                        test_instance._flow_num = j
                        test_instance.pre_flow(flow)
                        flow(test_instance, *flow_params)
                        test_instance.post_flow(flow)


                    assert flow_state[j].before_inv_random_state is not None
                    if curr_flow_state.before_inv_random_state != b"":
                        random.setstate(pickle.loads(curr_flow_state.before_inv_random_state))
                    if not dry_run:
                        test_instance.pre_invariants()
                        for inv in invariants:
                            if invariant_periods[inv] == 0:
                                test_instance.pre_invariant(inv)
                                inv(test_instance)
                                test_instance.post_invariant(inv)

                            invariant_periods[inv] += 1
                            if invariant_periods[inv] == getattr(inv, "period"):
                                invariant_periods[inv] = 0
                        test_instance.post_invariants()
                test_instance.post_sequence()
            except OverRunException:
                exception = False # since it is not test exception
            except Exception as e:
                exception = True
                # Check exception type and exception lines in the testing file.
                ignore_flows = True

                if (ignore_flows or test_instance._flow_num == error_flow_num) and compare_exceptions(e, exception_content):

                    # the removed flow is not required to reproduce same error. @ try remove next flow
                    print("remove worked!!")
                    assert flow_state[curr].required == False
                else:
                    print(e)
                    # the removing flow caused different error . @this flow should not removed restore current flow and remove next flow
                    flow_state[curr].required = True

                    print("remove failed!!")

            finally:
                # revert to starting state
                # for snapshot, chain in zip(initial_chain_state_snapshots, chains):
                #     chain.revert(snapshot)
                print("revert state!!")
                states.revert(test_instance, chains)
                states.take_snapshot(test_instance, test_class(), chains, overwrite=False)

            if exception == False:
                print("overrun!")
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



def single_fuzz_test(test_class: type[FuzzTest], sequences_count: int, flows_count: int, dry_run: bool = False):
    test_instance = test_class()
    chains = get_connected_chains()
    flows: List[Callable] = __get_methods(test_instance, "flow")
    invariants: List[Callable] = __get_methods(test_instance, "invariant")
    dry_run = False

    for i in range(sequences_count):
        flows_counter: DefaultDict[Callable, int] = defaultdict(int)
        invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)

        # Snapshot all connected chains
        snapshots = [chain.snapshot() for chain in chains]


        set_sequence_initial_internal_state(
                pickle.dumps(
                random.getstate()
            )
        )

        test_instance._flow_num = 0
        test_instance._sequence_num = i
        test_instance.pre_sequence()


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
                    or getattr(f, "precondition")(test_instance)
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
                    and not getattr(f, "precondition")(test_instance)
                ]
                raise Exception(
                    f"Could not find a valid flow to run.\nFlows that have reached their max_times: {max_times_flows}\nFlows that do not satisfy their precondition: {precondition_flows}"
                )

            # Pick a flow and generate the parameters
            flow = random.choices(valid_flows, weights=weights)[0]
            flow_params = [
                generate(v)
                for k, v in get_type_hints(flow, include_extras=True).items()
                if k != "return"
            ]

            test_instance._flow_num = j
            set_error_flow_num(j)
            test_instance.pre_flow(flow)
            flow(test_instance, *flow_params)  # Execute the selected flow
            flows_counter[flow] += 1
            test_instance.post_flow(flow)

            if not dry_run:
                test_instance.pre_invariants()
                for inv in invariants:
                    if invariant_periods[inv] == 0:
                        test_instance.pre_invariant(inv)
                        inv(test_instance)
                        test_instance.post_invariant(inv)

                    invariant_periods[inv] += 1
                    if invariant_periods[inv] == getattr(inv, "period"):
                        invariant_periods[inv] = 0
                test_instance.post_invariants()

        test_instance.post_sequence()

        # Revert all chains back to their initial snapshot
        for snapshot, chain in zip(snapshots, chains):
            chain.revert(snapshot)
