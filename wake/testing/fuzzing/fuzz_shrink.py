from __future__ import annotations


from collections import defaultdict
from typing import Callable, DefaultDict, List, Optional, Any, Tuple

from typing_extensions import get_type_hints

from wake.development.globals import random

from ..core import get_connected_chains
from .generators import generate

from dataclasses import dataclass

from .fuzz_test import FuzzTest

from wake.development.globals import random, set_sequence_initial_internal_state, get_fuzz_mode, get_sequence_initial_internal_state, set_error_flow_num, get_error_flow_num, get_config, get_shrank_path

from wake.development.core import Chain
import pickle

from pathlib import Path
from datetime import datetime, timedelta

import traceback
from wake.utils.file_utils import is_relative_to
from wake.development.transactions import Error
import copy
import os
import sys
from wake.cli.console import console
from contextlib import contextmanager, redirect_stdout, redirect_stderr

from wake.testing.core import default_chain as global_default_chain

EXACT_FLOW_INDEX = False # False if you accept it could reproduce same error earlier.

EXECT_EXCEPTION_MATCH = False # False if you accept the same kind of error.
# The meaining of the same kind of error is that
# If the error was in transaction, Same Error is emit and ignore arguments value. except for Error with only message, we compare the message.
# If the error was in test like assertion error, we care the file and  exception line in python code.

ONLY_TARGET_INVARIANTS = False # True if you want to Care only target invariants.

def __get_methods(target, attr: str) -> List[Callable]:
    ret = []
    for x in dir(target):
        if hasattr(target.__class__, x):
            m = getattr(target.__class__, x)
            if hasattr(m, attr) and getattr(m, attr):
                ret.append(m)
    return ret


def clear_previous_lines(num_lines):
    for _ in range(num_lines):
        sys.stdout.write("\033[F")  # Move cursor up one line
        sys.stdout.write("\033[K")  # Clear the line

def compare_exceptions(e1, e2):
    if EXECT_EXCEPTION_MATCH:
        if e1 == e2:
            return True
        else:
            return False

    if type(e1) != type(e2):
        return False

    # from wake.development.transactions import Error
    if type(e1) == Error and type(e2) == Error:
        # If it was the Error(TransactionRevertedError), compare message content.
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
    flow_number: int | None # Current flow number
    random_state: Any | None
    default_chain: Chain | None

    def __init__(self):
        self._python_state = None
        self.chain_states = []
        self.flow_number = None

    def take_snapshot(self, python_instance: FuzzTest, new_instance, chains: Tuple[Chain, ...], overwrite: bool, random_state: Any | None = None):
        if not overwrite:
            assert self._python_state is None, "Python state already exists"
            assert self.chain_states == [], "Chain state already exists"
        else:
            assert self._python_state is not None, "Python state (snapshot) is missing"
            assert self.chain_states != [], "Chain state is missing"
            assert self.flow_number is not None, "Flow number is missing"
            print("Overwriting state ", self.flow_number, " to ", python_instance._flow_num)
            assert self.default_chain is not None, "Default chain is missing"
        # assert self._python_state is None, "Python state already exists"
        self._python_state = new_instance

        self.flow_number = python_instance._flow_num
        self._python_state.__dict__.update(copy.deepcopy(python_instance.__dict__))
        self.chain_states = [chain.snapshot() for chain in chains]
        self.default_chain = global_default_chain
        self.random_state = random_state

    def revert(self, python_instance: FuzzTest, chains: Tuple[Chain, ...], with_random_state: bool = False):
        global global_default_chain
        assert self.chain_states != [], "Chain snapshot is missing"
        assert self._python_state is not None, "Python state snapshot is missing "
        assert self.flow_number is not None, "Flow number is missing"
        assert self.default_chain is not None, "Default chain is missing"

        python_instance.__dict__ = self._python_state.__dict__

        self._python_state = None
        for temp_chain, chain in zip(self.chain_states, chains):
            chain.revert(temp_chain)
        self.chain_states = []
        if with_random_state:
            assert self.random_state is not None, "Random state is missing"
            random.setstate(self.random_state)
        global_default_chain = self.default_chain


class OverRunException(Exception):
    def __init__(self):
        super().__init__("Overrun")

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
class FlowStateForFile:
    random_state: bytes
    flow_num: int
    flow_name: str
    flow_params: List[Any]  # Store the list of arguments
    required: bool = True
    before_inv_random_state: bytes = b""

@dataclass
class ShrankInfoFile:
    target_fuzz_path: str
    initial_state: bytes
    required_flows: List[FlowStateForFile]

@contextmanager
def print_ignore(debug: bool = False):
    ctx_managers = []
    if not debug:
        ctx_managers.append(redirect_stdout(open(os.devnull, 'w')))
        ctx_managers.append(redirect_stderr(open(os.devnull, 'w')))
    for ctx_manager in ctx_managers:
        ctx_manager.__enter__()

    yield

    for ctx_manager in ctx_managers:
        ctx_manager.__exit__(None, None, None)
    ctx_managers.clear()

def fuzz_shrink(test_class: type[FuzzTest], sequences_count: int, flows_count: int, dry_run: bool = False):
    assert issubclass(test_class, FuzzTest)
    fuzz_mode = get_fuzz_mode()
    if fuzz_mode == 0:
        single_fuzz_test(test_class, sequences_count, flows_count, dry_run)
    elif fuzz_mode == 1:
        shrink_test(test_class, flows_count)
    elif fuzz_mode == 2:
        shrank_reproduce(test_class, dry_run)
    elif fuzz_mode == 3:
        flow_step_execution(test_class, flows_count)
    else:
        raise Exception("Invalid fuzz mode")

def shrank_reproduce(test_class: type[FuzzTest], dry_run: bool = False):
    test_instance = test_class()

    flows: List[Callable] = __get_methods(test_instance, "flow")
    invariants: List[Callable] = __get_methods(test_instance, "invariant")
    shrank_path = get_shrank_path()
    if shrank_path is None:
        raise Exception("Shrunken data file path not found")
    with open(shrank_path, 'rb') as f:
            store_data: ShrankInfoFile = pickle.load(f)

    random.setstate(pickle.loads(store_data.initial_state))
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
        test_instance._flow_num = store_data.required_flows[j].flow_num
        if not hasattr(flow, "precondition") or getattr(flow, "precondition")(test_instance):
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

    print("Shrunken test passed")

def shrink_collecting_phase(test_instance: FuzzTest, flows, invariants, flow_states:List[FlowState], chains: Tuple[Chain, ...], flows_count: int) -> Tuple[Exception, timedelta]:
    data_time = datetime.now()
    flows_counter: DefaultDict[Callable, int] = defaultdict(int)
    invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)
    # Snapshot all connected chains
    initial_chain_state_snapshots = [chain.snapshot() for chain in chains]
    error_flow_num = get_error_flow_num() # argument
    initial_state = get_sequence_initial_internal_state() # argument

    random.setstate(pickle.loads(initial_state))
    with print_ignore():
        test_instance._flow_num = 0
        test_instance.pre_sequence()
        exception_content = None
        try:
            for j in range(flows_count):


                if j > error_flow_num:
                    raise OverRunException()
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
                flow_states.append(FlowState(
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

                flow_states[j].before_inv_random_state = pickle.dumps(random.getstate())

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
            raise AssertionError("Unexpected un-failing flow")
        except Exception as e:
            exception_content = e
            assert test_instance._flow_num == get_error_flow_num(), "Unexpected failing flow"
        finally:
            for snapshot, chain in zip(initial_chain_state_snapshots, chains):
                chain.revert(snapshot)
            initial_chain_state_snapshots = []

    # calculate time spent
    second_time = datetime.now()
    time_spent = (second_time - data_time)
    print("Time spent for one fuzz test: ", time_spent)
    assert exception_content is not None
    return exception_content, time_spent

def flow_step_execution(test_class: type[FuzzTest], flows_count: int):
    error_flow_num = get_error_flow_num()
    user_number = input(f"SNAPSHOT FLOW NUMBER ({error_flow_num}) >")
    if user_number != "":
        error_flow_num = int(user_number)

    assert error_flow_num  != flows_count, "Does not support post sequence, comming soon"
    test_instance = test_class()
    chains = get_connected_chains()
    flows: List[Callable] = __get_methods(test_instance, "flow")
    invariants: List[Callable] = __get_methods(test_instance, "invariant")
    flows_counter: DefaultDict[Callable, int] = defaultdict(int)
    invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)
    print("Shrinking flow length: ", error_flow_num)

    if error_flow_num < 1:
        raise Exception("Flow number is less than 1, not supported for shrinking")

    random.setstate(pickle.loads(get_sequence_initial_internal_state()))
    # ignore print for pre_sequence logging
    test_instance._flow_num = 0
    test_instance.pre_sequence()
    try:
        for j in range(error_flow_num):
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
            test_instance.pre_flow(flow)
            flow(test_instance, *flow_params)  # Execute the selected flow
            flows_counter[flow] += 1
            test_instance.post_flow(flow)
            # DO NOT RUN INVARIANTS HERE
            # REQUIREMENT: DO NOT CHANGE STATE IN INVARIANTS
    except Exception as e:
        print(f"MUST NOT FAIL HERE {e}")
        raise e

    # take snapshot of previous state!!
    states = StateSnapShot()
    states.take_snapshot(test_instance, test_class(), chains, overwrite=False, random_state=random.getstate())
    error_place = None
    j = 0
    for j in range(test_instance._flow_num, flows_count):
        try:
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
            test_instance.pre_flow(flow)
            commands = []
            commands.append("s")
            commands.append("s")
            error_place = "flow"
            from ipdb.__main__ import _init_pdb
            frame = sys._getframe() # Get the parent frame
            p = _init_pdb(commands=['s'])  # Initialize with two step commands
            p.set_trace(frame)
            # this flow cause error or vioration of invariant.
            flow(test_instance, *flow_params)  # Execute the selected flow
            # After flow execution, I would have option to take snapshot and execute or
            # Revert to previous state and execute this flow again.
            # Print flow information before execution

            flows_counter[flow] += 1
            error_place = "post_flow"
            test_instance.post_flow(flow)
            error_place = "pre_invariants"
            test_instance.pre_invariants()
            error_place = "invariants"
            for inv in invariants:
                if invariant_periods[inv] == 0:
                    test_instance.pre_invariant(inv)
                    inv(test_instance)
                    test_instance.post_invariant(inv)

                invariant_periods[inv] += 1
                if invariant_periods[inv] == getattr(inv, "period"):
                    invariant_periods[inv] = 0
        except Exception as e:
            exception_content = e
            print(f"Error at {error_place} with\n{e}")
        finally:
            # repeat option till user type valid input
            quit = False
            while True:
                print("Flow Step Execution")
                print("Options:")
                print("1. take snapshot and continue")
                print("2. Revert and repeat current flow")
                print("3. run post_sequence and exit")
                choice = input("Enter your choice (1-3): ").strip()
                if choice == "1":
                    states.take_snapshot(test_instance, test_class(), chains, overwrite=True, random_state=random.getstate())
                    break
                elif choice == "2":
                    states.revert(test_instance, chains, with_random_state=True)
                    states.take_snapshot(test_instance, test_class(), chains, overwrite=False, random_state=random.getstate())
                    j -= 1
                    break
                elif choice == "3":
                    quit = True
                    break
                else:
                    print("Invalid choice. Please try again.")
            if quit:
                break
    test_instance.post_sequence()

def shrink_test(test_class: type[FuzzTest], flows_count: int):
    error_flow_num = get_error_flow_num() # argument
    actual_error_flow_num = error_flow_num
    print("Fuzz test shrink start! First of all, collect random/flow information!!! >_<")
    shrink_start_time = datetime.now()
    print("Start time: ", shrink_start_time)
    test_instance = test_class()
    chains = get_connected_chains()
    flows: List[Callable] = __get_methods(test_instance, "flow")
    invariants: List[Callable] = __get_methods(test_instance, "invariant")
    flow_states: List[FlowState] = []
    print("Shrinking flow length: ", error_flow_num)

    if error_flow_num < 1:
        raise Exception("Flow number is less than 1, not supported for shrinking")

    exception_content, time_spent_for_one_fuzz = shrink_collecting_phase(test_instance,flows, invariants, flow_states, chains, flows_count)
    print("Estimated completion time for shrinking:", (time_spent_for_one_fuzz*get_error_flow_num())/4 + time_spent_for_one_fuzz * len(flows) * 3 / 4) # estimate around half of flow is not related to the error
    print("Starting shrinking")

    random.setstate(pickle.loads(get_sequence_initial_internal_state()))
    # ignore print for pre_sequence logging
    with print_ignore():
        test_instance._flow_num = 0
        test_instance._sequence_num = 0
        test_instance.pre_sequence()
        states = StateSnapShot()
        states.take_snapshot(test_instance,test_class(), chains, overwrite=False)

    print("Removing flows by flow types start")
    print("Estimated maximum completion time for flow type removal:", (len(flows)* time_spent_for_one_fuzz))
    base_date_time = datetime.now()

    # sorted_flows sort depends on appeard count in flow_states
    # sort by flow_name.
    # try to remove flow from most appeared flow to least appeared flow.
    # so if most appeared flow is removable, it would significantly reduce the time.
    flow_states_map = defaultdict(int)
    for flow_state in flow_states:
        flow_states_map[flow_state.flow_name] += 1 # flow_name or flow
    sorted_flows = sorted(flows, key=lambda x: (-flow_states_map[x.__name__], x.__name__))
    assert len(sorted_flows) == len(flows)
    number_of_multiple_flows = 0
    for flow_state in flow_states:
        if flow_states_map[flow_state.flow_name] > 1:
            number_of_multiple_flows += 1

    # Print sorted flows
    for flow in sorted_flows:
        print(f"Flow: {flow.__name__}, Count: {flow_states_map[flow.__name__]}")
    removed_sum = 0
    new_time_spent_for_one_fuzz = time_spent_for_one_fuzz # later compare with new and use smaller one.
    # Flow type removal
    for i in range(len(sorted_flows)):
        base_time_spent_for_one_fuzz = datetime.now()
        invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)
        curr_removing_flow = sorted_flows[i]

        print("")
        print(f"Removing flow: {curr_removing_flow.__name__}")
        try:
            print(f"Flow type removal progress: {i}/{number_of_multiple_flows} = {(i*100/number_of_multiple_flows):.2f}%")
        except ZeroDivisionError:
            print(f"Flow type removal progress: {i}/{1} = {0:.2f}%")
        print(f"Shrunken flows rate: {removed_sum}/{len(flow_states)} = {(removed_sum*100/len(flow_states)):.2f}%")

        if flow_states_map[curr_removing_flow.__name__] <= 1: # since count is 1 is same as brute force test
            # the 4 is the privious print lines
            clear_previous_lines(4)
            break # since it is sorted, and not required to snapshot, already taken.
        success = False
        shortcut = False
        with print_ignore(debug=False):
            try:
                for j in range(flows_count):
                    if j == -1: # this condition applies only curr == 0
                        continue

                    if j > error_flow_num:
                        raise OverRunException()

                    curr_flow_state = flow_states[j]
                    random.setstate(pickle.loads(curr_flow_state.random_state))
                    flow = curr_flow_state.flow
                    flow_params = curr_flow_state.flow_params
                    test_instance._flow_num = j
                    if flow_states[j].required and flow != curr_removing_flow:
                        if not hasattr(flow, "precondition") or getattr(flow, "precondition")(test_instance):
                            test_instance.pre_flow(flow)
                            flow(test_instance, *flow_params)
                            test_instance.post_flow(flow)

                    if curr_flow_state.before_inv_random_state != b"":
                        random.setstate(pickle.loads(curr_flow_state.before_inv_random_state))

                    test_instance.pre_invariants()
                    if ((not ONLY_TARGET_INVARIANTS and flow_states[j].required and flow != curr_removing_flow)
                        or (ONLY_TARGET_INVARIANTS and j == error_flow_num)): # this would be changed
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
                print("overrun!")
                reason = "Over run (did not reproduce error)"

            except Exception as e:
                reason = "at " + str(j) + " with " + str(e)
                # Check exception type and exception lines in the test file.
                if (not EXACT_FLOW_INDEX or test_instance._flow_num == error_flow_num) and compare_exceptions(e, exception_content):
                    if test_instance._flow_num != error_flow_num:
                        shortcut = True
                        assert test_instance._flow_num == j

                    # The removed flow is not necessary to reproduce the same error.  Try to remove next flow
                    for flow_state_ in flow_states[:j]: # 0 to until index j
                        if flow_state_.flow == curr_removing_flow:
                            flow_state_.required = False
                            removed_sum += 1
                    success = True
                    new_time_spent_for_one_fuzz = datetime.now() - base_time_spent_for_one_fuzz
                else:
                    # Removing the flow caused a different error. This flow should not removed to reproduce the error, restore current flow and try to remove the next flow
                    success = False
            finally:
                # Revert to the snapshot state which has data until the "curr".
                states.revert(test_instance, chains)
                states.take_snapshot(test_instance, test_class(), chains, overwrite=False)

        clear_previous_lines(4)
        if success:
            print("Remove result: ", curr_removing_flow.__name__, " ✅", end="")
            if shortcut:
                print(f" 🌟 shortcut from {error_flow_num} to {j}")
                removed_sum += error_flow_num - j
                error_flow_num = j
            else:
                print("")
        else:
            print("Remove result: ", curr_removing_flow.__name__, " ⛔", "Reason:", reason)

    time_spent_for_one_fuzz = min(time_spent_for_one_fuzz, new_time_spent_for_one_fuzz)
    print(f"Removed flows: {removed_sum}/{actual_error_flow_num} = {removed_sum/actual_error_flow_num*100:.2f}%")
    print("Time spent for the flow type removal: ", datetime.now() - base_date_time)

    base_date_time = datetime.now()

    curr = 0 # current testing flow index
    prev_curr = -1
    print("Brute force removal start")
    print(f"Estimated maximum completion time for brute force removal: (remaining flow count={actual_error_flow_num-removed_sum}) * (time for one fuzz={time_spent_for_one_fuzz}) = {(actual_error_flow_num-removed_sum) * time_spent_for_one_fuzz}")
    while curr < len(flow_states) and flow_states[curr].required == False:
        curr += 1
    # remove flow by brute force
    while curr <= error_flow_num:
        assert flow_states[curr].required == True
        flow_states[curr].required = False
        invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(
            int
        )
        print("")
        print(f"Removing {curr} th flow {flow_states[curr].flow_name}")
        print(f"Brute force flow removal progress: {(curr* 100) / (error_flow_num+1):.2f}%")
        print(f"Shrunken flows rate: {removed_sum}/{actual_error_flow_num} = {(removed_sum*100/actual_error_flow_num):.2f}%")

        success = False
        shortcut = False
        reason = None
        with print_ignore(debug=False):
            try:
                # Python state and chain state is same as snapshot
                # and start running from flow at "prev_curr".
                for j in range(prev_curr, flows_count):

                    if j == -1:
                        continue

                    if j > error_flow_num:
                        raise OverRunException()

                    # Execute untill curr flow.(curr flow is not executed yet) and take snapshot, since we still do not know if it is required or not.
                    # curr == 0 state is already taken.
                    if j == curr and curr != 0:
                        states.take_snapshot(test_instance, test_class(), chains, overwrite=True)

                    print("flow: ", j, flow_states[j].flow.__name__ )

                    curr_flow_state = flow_states[j]
                    random.setstate(pickle.loads(curr_flow_state.random_state))
                    flow = curr_flow_state.flow
                    flow_params = curr_flow_state.flow_params

                    test_instance._flow_num = j
                    if flow_states[j].required:
                        if not hasattr(flow, "precondition") or getattr(flow, "precondition")(test_instance):
                            test_instance.pre_flow(flow)
                            flow(test_instance, *flow_params)
                            test_instance.post_flow(flow)

                    if curr_flow_state.before_inv_random_state != b"":
                        random.setstate(pickle.loads(curr_flow_state.before_inv_random_state))

                    test_instance.pre_invariants()
                    if ((not ONLY_TARGET_INVARIANTS and flow_states[j].required)
                        or (ONLY_TARGET_INVARIANTS and j == error_flow_num)):
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
                flow_states[curr].required = True
                success = False
                reason = "Over run (Did not reproduce error)"
            except Exception as e:
                reason = "at " + str(j) + " with " + str(e)
                # Check exception type and exception lines in the test file.
                if (not EXACT_FLOW_INDEX or test_instance._flow_num == error_flow_num) and compare_exceptions(e, exception_content):
                    if test_instance._flow_num != error_flow_num:
                        print("test_instance._flow_num: ", test_instance._flow_num, "j: ", j, "error_flow_num: ", error_flow_num)
                        shortcut = True
                        assert test_instance._flow_num == j
                    # The removed flow is not necessary to reproduce the same error.  Try to remove next flow
                    assert flow_states[curr].required == False
                    success = True
                else:
                    # Removing the flow caused a different error. This flow should not removed to reproduce the error, restore current flow and try to remove the next flow
                    flow_states[curr].required = True
                    success = False

            finally:
                # Revert to the snapshot state which has data until the "curr".
                states.revert(test_instance, chains)
                states.take_snapshot(test_instance, test_class(), chains, overwrite=False)

        clear_previous_lines(4)

        if success:
            removed_sum += 1
            print("Remove result: ", curr, "th flow: ", flow_states[curr].flow_name, " ✅", end="")
            if shortcut:
                print(f" 🌟 shortcut from {error_flow_num} to {j}")

                for i in range(j, error_flow_num):
                    if flow_states[i].required == True:
                        removed_sum += 1
                error_flow_num = j
            else:
                print("")
        else:
            print("Remove result: ", curr, "th flow: ", flow_states[curr].flow_name, " ⛔ ", "Reason:", reason)
        prev_curr = curr
        curr += 1
        # Go to the next testing flow.
        while  curr < len(flow_states) and flow_states[curr].required == False:
            curr += 1

    print("Shrinking completed")
    print("Time spent for the brute force removal: ", datetime.now() - base_date_time)
    print(f"Shrunken flows rate: {removed_sum}/{actual_error_flow_num} = {(removed_sum*100/actual_error_flow_num):.2f}%")
    print("Those flows were required to reproduce the error")
    for i in range(0, error_flow_num+1):
        if flow_states[i].required:
            print(flow_states[i].flow_name, " : ", flow_states[i].flow_params)
    print("")
    project_root_path = get_config().project_root_path
    print("Time spent for shrinking: ", datetime.now() - shrink_start_time)
    crash_logs_dir = project_root_path / ".wake" / "logs" / "shrank"

    crash_logs_dir.mkdir(parents=True, exist_ok=True)
    # write crash log file.
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Assuming `call.execinfo` contains the crash information
    crash_log_file = crash_logs_dir / F"{timestamp}.bin"

    import inspect
    current_file_path = os.path.abspath(inspect.getfile(test_class))

    # Calculate the relative path
    relative_test_path = os.path.relpath(current_file_path, project_root_path)

    #initial_state
    required_flows: List[FlowStateForFile] = []
    for i in range(len(flow_states)):
        if flow_states[i].required:
            required_flows.append(FlowStateForFile(
                random_state=flow_states[i].random_state,
                flow_num=flow_states[i].flow_num,
                flow_name=flow_states[i].flow_name,
                # ignore flow_states[i].flow
                flow_params=flow_states[i].flow_params,
                required=flow_states[i].required,
                before_inv_random_state=flow_states[i].before_inv_random_state
            ))

    store_data: ShrankInfoFile = ShrankInfoFile(
        target_fuzz_path=relative_test_path,
        initial_state=get_sequence_initial_internal_state(),
        required_flows=required_flows
    )
    # Write to a JSON file
    with open(crash_log_file, 'wb') as f:
        pickle.dump(store_data, f)
    print(f"Shrunken data file written to {crash_log_file}")



def single_fuzz_test(test_class: type[FuzzTest], sequences_count: int, flows_count: int, dry_run: bool = False):
    '''
    This function does exactly same as previous fuzz test.
    Also it correctly updates _flow_num and _sequence_num.
    '''

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
