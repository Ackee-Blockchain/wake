from __future__ import annotations

import copy
import json
import os
import sys
import traceback
from collections import defaultdict
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, DefaultDict, List, Optional, Tuple

from typing_extensions import get_type_hints

from wake.cli.console import console
from wake.development.core import Chain
from wake.development.globals import (
    get_config,
    get_current_test_id,
    get_executing_flow_num,
    get_fuzz_mode,
    get_sequence_initial_internal_state,
    get_shrank_path,
    get_shrink_exact_exception,
    get_shrink_exact_flow,
    get_shrink_target_invariants_only,
    random,
    set_executing_flow_num,
    set_executing_sequence_num,
    set_is_fuzzing,
    set_sequence_initial_internal_state,
)
from wake.development.transactions import Error, Panic
from wake.testing.core import default_chain as global_default_chain
from wake.utils.file_utils import is_relative_to

from ..core import get_connected_chains
from .fuzz_test import FuzzTest
from .generators import generate

EXACT_FLOW_INDEX = (
    get_shrink_exact_flow()
)  # Set True if you accept the same error that happened earlier than the crash log.

EXACT_EXCEPTION_MATCH = (
    get_shrink_exact_exception()
)  # True if you do not accept the same kind of error but different arguments.
# The meaning of the same kind of error is that
# # If the Error was in the transaction, the same error emits and ignores the argument's value. Except for errors with only the message, we compare the message.
# # If the Error was in a test like an assertion error, we care about the file and exception line in Python code.

ONLY_TARGET_INVARIANTS = (
    get_shrink_target_invariants_only()
)  # True if you want to check only target invariants.
# True makes one fuzz test run faster. but it may lose chance to shortcut that finding the same error earlier.


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


def compare_exceptions(e1: Exception, e2: Exception):

    if type(e1) is not type(e2):
        return False

    # "type(e1) is Error" would be more strict, but we accept all Error subclasses.
    # still no class are defined in wake. might be change in the future.
    if type(e1) == Error and type(e2) == Error:
        # If it was the Error(TransactionRevertedError), compare message content.
        if e1.message != e2.message:
            return False

    if type(e1) == Panic and type(e2) == Panic:
        if e1.code != e2.code:
            return False

    tb1 = traceback.extract_tb(e1.__traceback__)
    tb2 = traceback.extract_tb(e2.__traceback__)

    frame1 = None
    for frame1 in tb1:
        if is_relative_to(Path(frame1.filename), Path.cwd()) and not is_relative_to(
            Path(frame1.filename), Path().cwd() / "pytypes"
        ):
            break
    frame2 = None
    for frame2 in tb2:
        if is_relative_to(Path(frame2.filename), Path.cwd()) and not is_relative_to(
            Path(frame2.filename), Path().cwd() / "pytypes"
        ):
            break

    if frame1 is None or frame2 is None:
        print("frame is none!!!!!!!!!!!!!!")
        # return False
    if (
        frame1 is not None
        and frame2 is not None
        and (
            frame1.filename != frame2.filename
            or frame1.lineno != frame2.lineno
            or frame1.name != frame2.name
        )
    ):
        return False

    if EXACT_EXCEPTION_MATCH:
        if e1.args != e2.args:
            return False
    return True


def serialize_random_state(state: tuple[int, tuple[int, ...], float | None]) -> dict:
    """Convert random state to JSON-serializable format"""
    version, state_tuple, gauss = state
    return {
        "version": version,
        "state_tuple": list(state_tuple),  # convert tuple to list for JSON
        "gauss": gauss,
    }


def deserialize_random_state(
    state_dict: dict,
) -> tuple[int, tuple[int, ...], float | None]:
    """Convert JSON format back to random state tuple"""
    return (
        state_dict["version"],
        tuple(state_dict["state_tuple"]),  # convert list back to tuple
        state_dict["gauss"],
    )


class StateSnapShot:
    _python_state: FuzzTest | None
    chain_states: List[str]
    flow_number: int | None  # Current flow number
    random_state: Any | None
    default_chain: Chain | None

    def __init__(self):
        self._python_state = None
        self.chain_states = []
        self.flow_number = None

    def take_snapshot(
        self,
        python_instance: FuzzTest,
        new_instance,
        chains: Tuple[Chain, ...],
        overwrite: bool,
        random_state: Any | None = None,
    ):
        if not overwrite:
            assert self._python_state is None, "Python state already exists"
            assert self.chain_states == [], "Chain state already exists"
        else:
            assert self._python_state is not None, "Python state (snapshot) is missing"
            assert self.chain_states != [], "Chain state is missing"
            assert self.flow_number is not None, "Flow number is missing"
            print(
                "Overwriting state ",
                self.flow_number,
                " to ",
                python_instance._flow_num,
            )
            assert self.default_chain is not None, "Default chain is missing"
        # assert self._python_state is None, "Python state already exists"
        self._python_state = new_instance

        self.flow_number = python_instance._flow_num
        self._python_state.__dict__.update(copy.deepcopy(python_instance.__dict__))
        self.chain_states = [chain.snapshot() for chain in chains]
        self.default_chain = global_default_chain
        self.random_state = random_state

    def revert(
        self,
        python_instance: FuzzTest,
        chains: Tuple[Chain, ...],
        with_random_state: bool = False,
    ):
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
class ReproducibleFlowState:
    random_state: tuple[int, tuple[int, ...], float | None]
    flow_num: int
    flow_name: str
    flow_params: List[Any]

    def to_dict(self):
        return {
            "random_state": serialize_random_state(self.random_state),
            "flow_num": self.flow_num,
            "flow_name": self.flow_name,
            "flow_params": self.flow_params,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            random_state=deserialize_random_state(data["random_state"]),
            flow_num=data["flow_num"],
            flow_name=data["flow_name"],
            flow_params=data["flow_params"],
        )


@dataclass
class FlowState(ReproducibleFlowState):
    flow: Callable  # Runtime-only field for analysis
    required: bool = True  # Runtime-only field for analysis


@dataclass
class ShrankInfoFile:
    target_fuzz_node: str
    initial_state: dict
    required_flows: List[ReproducibleFlowState]

    def to_dict(self):
        return {
            "target_fuzz_node": self.target_fuzz_node,
            "initial_state": self.initial_state,
            "required_flows": [flow.to_dict() for flow in self.required_flows],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            target_fuzz_node=data["target_fuzz_node"],
            initial_state=data["initial_state"],
            required_flows=[
                ReproducibleFlowState.from_dict(flow) for flow in data["required_flows"]
            ],
        )


@contextmanager
def print_ignore(debug: bool = False):
    ctx_managers = []
    if not debug:
        ctx_managers.append(redirect_stdout(open(os.devnull, "w")))
        ctx_managers.append(redirect_stderr(open(os.devnull, "w")))
    for ctx_manager in ctx_managers:
        ctx_manager.__enter__()

    yield

    for ctx_manager in ctx_managers:
        ctx_manager.__exit__(None, None, None)
    ctx_managers.clear()


def fuzz_shrink(
    test_class: type[FuzzTest],
    sequences_count: int,
    flows_count: int,
    dry_run: bool = False,
):
    assert issubclass(test_class, FuzzTest)
    fuzz_mode = get_fuzz_mode()
    if fuzz_mode == 0:
        set_is_fuzzing(True)
        single_fuzz_test(test_class, sequences_count, flows_count, dry_run)
        set_is_fuzzing(False)
    elif fuzz_mode == 1:
        shrink_test(test_class, flows_count)
    elif fuzz_mode == 2:
        shrank_reproduce(test_class, dry_run)
    else:
        raise Exception("Invalid fuzz mode")


def shrank_reproduce(test_class: type[FuzzTest], dry_run: bool = False):
    test_instance = test_class()

    flows: List[Callable] = __get_methods(test_instance, "flow")
    invariants: List[Callable] = __get_methods(test_instance, "invariant")
    shrank_path = get_shrank_path()
    if shrank_path is None:
        raise Exception("Shrunken data file path not found")
    # read shrank json file
    with open(shrank_path, "r") as f:
        serialized_shrank_info = f.read()
    store_data: ShrankInfoFile = ShrankInfoFile.from_dict(
        json.loads(serialized_shrank_info)
    )

    random.setstate(deserialize_random_state(store_data.initial_state))
    test_instance._flow_num = 0
    test_instance._sequence_num = 0
    test_instance.pre_sequence()

    invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)
    for j in range(len(store_data.required_flows)):

        flow = next(
            (
                flow
                for flow in flows
                if store_data.required_flows[j].flow_name == flow.__name__
            ),
            None,
        )
        if flow is None:
            raise Exception("Flow not found")
        flow_params = store_data.required_flows[j].flow_params
        test_instance._flow_num = store_data.required_flows[j].flow_num
        if not hasattr(flow, "precondition") or getattr(flow, "precondition")(
            test_instance
        ):
            random.setstate(store_data.required_flows[j].random_state)
            test_instance.pre_flow(flow)
            flow(test_instance, *flow_params)
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

    print("Shrunken test passed")


def shrink_collecting_phase(
    test_instance: FuzzTest,
    flows,
    invariants,
    flow_states: List[FlowState],
    chains: Tuple[Chain, ...],
    flows_count: int,
    initial_state: Any,
    error_flow_num: int,
) -> Tuple[Exception, timedelta]:
    data_time = datetime.now()
    flows_counter: DefaultDict[Callable, int] = defaultdict(int)
    invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)
    # Snapshot all connected chains
    initial_chain_state_snapshots = [chain.snapshot() for chain in chains]
    random.setstate(initial_state)
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

                random_state = random.getstate()
                flow_states.append(
                    FlowState(
                        random_state=random_state,
                        flow_name=flow.__name__,
                        flow_params=flow_params,
                        flow_num=j,
                        flow=flow,
                    )
                )

                test_instance._flow_num = j
                test_instance.pre_flow(flow)
                flow(test_instance, *flow_params)  # Execute the selected flow
                flows_counter[flow] += 1
                test_instance.post_flow(flow)

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
            assert test_instance._flow_num == error_flow_num, "Unexpected failing flow"
        finally:
            for snapshot, chain in zip(initial_chain_state_snapshots, chains):
                chain.revert(snapshot)
            initial_chain_state_snapshots = []

    # calculate time spent
    second_time = datetime.now()
    time_spent = second_time - data_time
    print("Time spent for one fuzz test: ", time_spent)

    print("exception_content: ", exception_content)
    assert exception_content is not None
    return exception_content, time_spent


def shrink_test(test_class: type[FuzzTest], flows_count: int):
    import inspect
    import json

    error_flow_num = get_executing_flow_num()  # argument
    actual_error_flow_num = error_flow_num
    print(
        "Fuzz test shrink start! First of all, collect random/flow information!!! >_<"
    )
    initial_state: tuple[int, tuple[int, ...], float | None] = deserialize_random_state(
        get_sequence_initial_internal_state()
    )

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

    exception_content, time_spent_for_one_fuzz = shrink_collecting_phase(
        test_instance,
        flows,
        invariants,
        flow_states,
        chains,
        flows_count,
        initial_state,
        error_flow_num,
    )
    print(
        "Estimated completion time for shrinking:",
        (time_spent_for_one_fuzz * actual_error_flow_num) / 4
        + time_spent_for_one_fuzz * len(flows) * 3 / 4,
    )  # estimate around half of flow is not related to the error
    print("Starting shrinking")

    random.setstate(initial_state)
    # ignore print for pre_sequence logging
    with print_ignore():
        test_instance._flow_num = 0
        test_instance._sequence_num = 0
        test_instance.pre_sequence()
        states = StateSnapShot()
        states.take_snapshot(test_instance, test_class(), chains, overwrite=False)

    print("Removing flows by flow types start")
    print(
        "Estimated maximum completion time for flow type removal:",
        (len(flows) * time_spent_for_one_fuzz),
    )
    base_date_time = datetime.now()

    # sorted_flows sort depends on appeard count in flow_states
    # sort by flow_name.
    # try to remove flow from most appeared flow to least appeared flow.
    # so if most appeared flow is removable, it would significantly reduce the time.
    flow_states_map = defaultdict(int)
    for flow_state in flow_states:
        flow_states_map[flow_state.flow_name] += 1  # flow_name or flow
    sorted_flows = sorted(
        flows, key=lambda x: (-flow_states_map[x.__name__], x.__name__)
    )
    assert len(sorted_flows) == len(flows)
    number_of_multiple_flows = 0
    for flow_state in flow_states:
        if flow_states_map[flow_state.flow_name] > 1:
            number_of_multiple_flows += 1

    # Print sorted flows
    for flow in sorted_flows:
        print(f"Flow: {flow.__name__}, Count: {flow_states_map[flow.__name__]}")
    removed_sum = 0
    new_time_spent_for_one_fuzz = (
        time_spent_for_one_fuzz  # later compare with new and use smaller one.
    )
    # Flow type removal
    for i in range(len(sorted_flows)):
        base_time_spent_for_one_fuzz = datetime.now()
        invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)
        curr_removing_flow = sorted_flows[i]

        print("")
        print(f"Removing flow: {curr_removing_flow.__name__}")
        try:
            print(
                f"Flow type removal progress: {i}/{number_of_multiple_flows} = {(i*100/number_of_multiple_flows):.2f}%"
            )
        except ZeroDivisionError:
            print(f"Flow type removal progress: {i}/{1} = {0:.2f}%")
        print(
            f"Shrunken flows rate: {removed_sum}/{len(flow_states)} = {(removed_sum*100/len(flow_states)):.2f}%"
        )

        if (
            flow_states_map[curr_removing_flow.__name__] <= 1
        ):  # since count is 1 is same as brute force test
            # the 4 is the privious print lines
            clear_previous_lines(4)
            break  # since it is sorted, and not required to snapshot, already taken.
        success = False
        shortcut = False
        j: int = 0
        reason: str = ""
        with print_ignore(debug=False):
            try:
                for j in range(flows_count):
                    if j == -1:  # this condition applies only curr == 0
                        continue

                    if j > error_flow_num:
                        raise OverRunException()

                    curr_flow_state = flow_states[j]
                    random.setstate(curr_flow_state.random_state)
                    flow = curr_flow_state.flow
                    flow_params = curr_flow_state.flow_params
                    test_instance._flow_num = j
                    if flow_states[j].required and flow != curr_removing_flow:
                        if not hasattr(flow, "precondition") or getattr(
                            flow, "precondition"
                        )(test_instance):
                            test_instance.pre_flow(flow)
                            flow(test_instance, *flow_params)
                            test_instance.post_flow(flow)

                    test_instance.pre_invariants()
                    if (
                        not ONLY_TARGET_INVARIANTS
                        and flow_states[j].required
                        and flow != curr_removing_flow
                    ) or (
                        ONLY_TARGET_INVARIANTS and j == error_flow_num
                    ):  # this would be changed
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
                if (
                    not EXACT_FLOW_INDEX or test_instance._flow_num == error_flow_num
                ) and compare_exceptions(e, exception_content):
                    if test_instance._flow_num != error_flow_num:
                        shortcut = True
                        assert test_instance._flow_num == j

                    # The removed flow is not necessary to reproduce the same error.  Try to remove next flow
                    for flow_state_ in flow_states[:j]:  # 0 to until index j
                        if flow_state_.flow == curr_removing_flow:
                            flow_state_.required = False
                            removed_sum += 1
                    success = True
                    new_time_spent_for_one_fuzz = (
                        datetime.now() - base_time_spent_for_one_fuzz
                    )
                else:
                    # Removing the flow caused a different error. This flow should not removed to reproduce the error, restore current flow and try to remove the next flow
                    success = False
            finally:
                # Revert to the snapshot state which has data until the "curr".
                states.revert(test_instance, chains)
                states.take_snapshot(
                    test_instance, test_class(), chains, overwrite=False
                )

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
            print(
                "Remove result: ", curr_removing_flow.__name__, " ⛔", "Reason:", reason
            )

    time_spent_for_one_fuzz = min(time_spent_for_one_fuzz, new_time_spent_for_one_fuzz)
    print(
        f"Removed flows: {removed_sum}/{actual_error_flow_num} = {removed_sum/actual_error_flow_num*100:.2f}%"
    )
    print("Time spent for the flow type removal: ", datetime.now() - base_date_time)

    base_date_time = datetime.now()

    curr = 0  # current testing flow index
    prev_curr = -1
    print("Brute force removal start")
    print(
        f"Estimated maximum completion time for brute force removal: (remaining flow count={actual_error_flow_num-removed_sum}) * (time for one fuzz={time_spent_for_one_fuzz}) = {(actual_error_flow_num-removed_sum) * time_spent_for_one_fuzz}"
    )
    while curr < len(flow_states) and flow_states[curr].required == False:
        curr += 1
    # remove flow by brute force
    while curr <= error_flow_num:
        assert flow_states[curr].required == True
        flow_states[curr].required = False
        invariant_periods: DefaultDict[Callable[[None], None], int] = defaultdict(int)
        print("")
        print(f"Removing {curr} th flow {flow_states[curr].flow_name}")
        print(
            f"Brute force flow removal progress: {(curr* 100) / (error_flow_num+1):.2f}%"
        )
        print(
            f"Shrunken flows rate: {removed_sum}/{actual_error_flow_num} = {(removed_sum*100/actual_error_flow_num):.2f}%"
        )

        success = False
        shortcut = False
        reason: str = ""
        j: int = 0
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
                        states.take_snapshot(
                            test_instance, test_class(), chains, overwrite=True
                        )

                    print("flow: ", j, flow_states[j].flow.__name__)

                    curr_flow_state = flow_states[j]
                    random.setstate(curr_flow_state.random_state)
                    flow = curr_flow_state.flow
                    flow_params = curr_flow_state.flow_params

                    test_instance._flow_num = j
                    if flow_states[j].required:
                        if not hasattr(flow, "precondition") or getattr(
                            flow, "precondition"
                        )(test_instance):
                            test_instance.pre_flow(flow)
                            flow(test_instance, *flow_params)
                            test_instance.post_flow(flow)

                    test_instance.pre_invariants()
                    if (not ONLY_TARGET_INVARIANTS and flow_states[j].required) or (
                        ONLY_TARGET_INVARIANTS and j == error_flow_num
                    ):
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
                if (
                    not EXACT_FLOW_INDEX or test_instance._flow_num == error_flow_num
                ) and compare_exceptions(e, exception_content):
                    if test_instance._flow_num != error_flow_num:
                        print(
                            "test_instance._flow_num: ",
                            test_instance._flow_num,
                            "j: ",
                            j,
                            "error_flow_num: ",
                            error_flow_num,
                        )
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
                states.take_snapshot(
                    test_instance, test_class(), chains, overwrite=False
                )

        clear_previous_lines(4)

        if success:
            removed_sum += 1
            print(
                "Remove result: ",
                curr,
                "th flow: ",
                flow_states[curr].flow_name,
                " ✅",
                end="",
            )
            if shortcut:
                print(f" 🌟 shortcut from {error_flow_num} to {j}")

                for i in range(j, error_flow_num):
                    if flow_states[i].required == True:
                        removed_sum += 1
                error_flow_num = j
            else:
                print("")
        else:
            print(
                "Remove result: ",
                curr,
                "th flow: ",
                flow_states[curr].flow_name,
                " ⛔ ",
                "Reason:",
                reason,
            )
        prev_curr = curr
        curr += 1
        # Go to the next testing flow.
        while curr < len(flow_states) and flow_states[curr].required == False:
            curr += 1

    print("Shrinking completed")
    print("Time spent for the brute force removal: ", datetime.now() - base_date_time)
    print(
        f"Shrunken flows rate: {removed_sum}/{actual_error_flow_num} = {(removed_sum*100/actual_error_flow_num):.2f}%"
    )
    print("Those flows were required to reproduce the error")
    for i in range(0, error_flow_num + 1):
        if flow_states[i].required:
            print(flow_states[i].flow_name, " : ", flow_states[i].flow_params)
    print("")
    project_root_path = get_config().project_root_path
    print("Time spent for shrinking: ", datetime.now() - shrink_start_time)
    crash_logs_dir = project_root_path / ".wake" / "logs" / "shrank"

    crash_logs_dir.mkdir(parents=True, exist_ok=True)
    # write crash log file.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Assuming `call.execinfo` contains the crash information

    # initial_state
    required_flows: List[ReproducibleFlowState] = [
        flow_states[i] for i in range(len(flow_states)) if flow_states[i].required
    ]
    current_test_id = get_current_test_id()
    assert current_test_id is not None
    store_data: ShrankInfoFile = ShrankInfoFile(
        target_fuzz_node=current_test_id,
        initial_state=get_sequence_initial_internal_state(),
        required_flows=required_flows,
    )

    # Write to a JSON file
    shrank_file = crash_logs_dir / f"{timestamp}.json"
    # I would like if file already exists, then create new indexed file
    if shrank_file.exists():
        i = 0
        while shrank_file.with_suffix(f"_{i}.json").exists():
            i += 1
        shrank_file = shrank_file.with_suffix(f"_{i}.json")
    with open(shrank_file, "w") as f:
        json.dump(store_data.to_dict(), f, indent=2)
    print(f"Shrunken data file written to {shrank_file}")


def single_fuzz_test(
    test_class: type[FuzzTest],
    sequences_count: int,
    flows_count: int,
    dry_run: bool = False,
):
    """
    This function does exactly same as previous fuzz test.
    Also it correctly updates _flow_num and _sequence_num.
    """

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

        state = serialize_random_state(random.getstate())
        set_sequence_initial_internal_state(state)

        test_instance._flow_num = 0
        set_executing_flow_num(0)
        set_executing_sequence_num(i)
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
            set_executing_flow_num(j)
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
