import json
import os
import time
from functools import partial
from pathlib import Path
from queue import SimpleQueue
from threading import Thread
from typing import Iterable, List, Optional, Tuple, Union

import pytest
from pytest import (
    CallInfo,
    Collector,
    CollectReport,
    Config,
    Item,
    Session,
    TestReport,
    UsageError,
)

from wake.cli.console import console
from wake.compiler.build_data_model import ProjectBuild
from wake.config import WakeConfig
from wake.development.globals import (
    attach_debugger,
    chain_interfaces_manager,
    get_coverage_handler,
    get_executing_flow_num,
    get_executing_sequence_num,
    get_fuzz_mode,
    get_fuzz_test_stats,
    get_is_fuzzing,
    get_sequence_initial_internal_state,
    random,
    reset_exception_handled,
    set_coverage_handler,
    set_current_test_id,
    set_exception_handler,
    set_executing_flow_num,
    set_fuzz_mode,
    set_sequence_initial_internal_state,
    set_shrank_path,
)
from wake.testing.coverage import CoverageHandler, export_coverage, prepare_info
from wake.testing.native_coverage import NativeCoverageHandler


def export_thread(queue: SimpleQueue, build: ProjectBuild):
    _, total_statements, source_unit_name_to_path = prepare_info(build)

    while True:
        item = queue.get()
        if item is None:
            break

        export_coverage(build, total_statements, source_unit_name_to_path, item)


class PytestWakePluginSingle:
    _config: WakeConfig
    _cov_proc_count: Optional[int]
    _random_seeds: List[bytes]
    _debug: bool
    _crash_log_meta_data: List[Tuple[str, str]]
    _test_mode: int
    _test_info_path: str
    _test_random_state: dict

    def __init__(
        self,
        config: WakeConfig,
        debug: bool,
        cov_proc_count: Optional[int],
        random_seeds: Iterable[bytes],
        test_mode: int,
        test_info_path: str,
    ):
        self._config = config
        self._debug = debug
        self._cov_proc_count = cov_proc_count
        self._random_seeds = list(random_seeds)
        self._crash_log_meta_data = []
        self._test_mode = test_mode
        self._test_info_path = test_info_path
        self._test_random_state = {}

    def get_shrink_argument_path(self, shrink_path_str: str, dir_name: str) -> Path:

        path = Path(shrink_path_str)
        if path.exists():
            return path

        crash_logs_dir = self._config.project_root_path / ".wake" / "logs" / dir_name
        if not crash_logs_dir.exists():
            raise UsageError(f"Crash logs directory not found: {crash_logs_dir}")

        crash_logs = sorted(
            crash_logs_dir.glob("*.json"), key=os.path.getmtime, reverse=True
        )
        try:
            index = int(shrink_path_str)
            if index < 0 or index >= len(crash_logs):
                raise ValueError()
        except ValueError:
            raise UsageError(f"Shrink log not found: {shrink_path_str}")

        if abs(index) > len(crash_logs):
            raise UsageError(f"Invalid crash log index: {index}")
        return Path(crash_logs[index])

    def pytest_collection_modifyitems(
        self, session: Session, config: Config, items: List[Item]
    ):
        import json

        # select correct item from
        if self._test_mode == 0 or self._test_mode == 4:
            # normal fuzzing
            if self._test_mode == 4:
                set_fuzz_mode(4)
            return
        elif self._test_mode == 1:
            # shrink
            set_fuzz_mode(1)
            shrink_crash_path = self.get_shrink_argument_path(
                self._test_info_path, "crashes"
            )
            try:
                with open(shrink_crash_path, "r") as file:
                    crash_log_dict = json.load(file)
            except json.JSONDecodeError:
                raise UsageError(
                    f"Invalid JSON format in crash log file: {shrink_crash_path}"
                )

            test_node_id = crash_log_dict["test_node_id"]
            set_executing_flow_num(crash_log_dict["crash_flow_number"])
            set_sequence_initial_internal_state(crash_log_dict["initial_random_state"])

            for item in items:
                if item.nodeid == test_node_id:
                    items[:] = [item]  # Execute only the target fuzz node.
                    break
            else:
                raise UsageError(
                    f"No test found matching the path '{test_node_id}' from crash log"
                )

        elif self._test_mode == 2:
            # shrank reproduce
            set_fuzz_mode(2)
            shrank_data_path = self.get_shrink_argument_path(
                self._test_info_path, "shrank"
            )
            print("shrank from shrank data: ", shrank_data_path)
            try:
                with open(shrank_data_path, "r") as f:
                    target_fuzz_node = json.load(f)["target_fuzz_node"]
            except json.JSONDecodeError:
                raise UsageError(
                    f"Invalid JSON format in shrank data file: {shrank_data_path}"
                )

            for item in items:
                if item.nodeid == target_fuzz_node:
                    items[:] = [item]  # Execute only the target fuzz node.
                    break
            else:
                raise UsageError(
                    f"No test found matching the path '{target_fuzz_node}' from crash log"
                )

            set_shrank_path(shrank_data_path)
        elif self._test_mode == 3:
            # Ru
            shrink_crash_path = self.get_shrink_argument_path(
                self._test_info_path, "crashes"
            )
            try:
                with open(shrink_crash_path, "r") as file:
                    crash_log_dict = json.load(file)
            except json.JSONDecodeError:
                raise UsageError(
                    f"Invalid JSON format in crash log file: {shrink_crash_path}"
                )

            test_node_id = crash_log_dict["test_node_id"]
            for item in items:
                if item.nodeid == test_node_id:
                    items[:] = [item]  # Execute only the target fuzz node.
                    break
            else:
                raise UsageError(
                    f"No test found matching the path '{test_node_id}' from crash log"
                )

            self._test_random_state = crash_log_dict["initial_random_state"]



    def pytest_runtest_setup(self, item: Item):
        reset_exception_handled()
        set_current_test_id(item.nodeid)

    def pytest_runtest_logstart(
        self, nodeid: str, location: Tuple[str, Optional[int], str]
    ):
        # ensure that the test path is terminated with a newline
        print("")

    def pytest_exception_interact(
        self,
        node: Union[Item, Collector],
        call: CallInfo,
        report: Union[CollectReport, TestReport],
    ):
        import json
        import os
        from datetime import datetime

        if self._debug:
            attach_debugger(
                call.excinfo.type,
                call.excinfo.value,
                call.excinfo.tb,
                seed=self._random_seeds[0],
            )

        if get_fuzz_mode() != 0:
            return
        random_state_dict = get_sequence_initial_internal_state()
        if random_state_dict == {}:
            return
        if call.excinfo is None:
            return
        crash_logs_dir = self._config.project_root_path / ".wake" / "logs" / "crashes"
        # shutil.rmtree(crash_logs_dir, ignore_errors=True)
        crash_logs_dir.mkdir(parents=True, exist_ok=True)
        # write crash log file.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Assuming `call.execinfo` contains the crash information
        crash_log_file = crash_logs_dir / f"{timestamp}.json"

        crash_data = {
            "test_node_id": node.nodeid,
            "crash_flow_number": get_executing_flow_num(),
            "exception_content": {
                "type": str(call.excinfo.type),
                "value": str(call.excinfo.value),
            },
            "initial_random_state": random_state_dict,
        }
        with crash_log_file.open("w") as f:
            json.dump(crash_data, f, indent=2)

        self._crash_log_meta_data.append(
            (
                str(node.nodeid),
                os.path.relpath(crash_log_file, self._config.project_root_path),
            )
        )

    def pytest_runtestloop(self, session: Session):
        if (
            session.testsfailed
            and not session.config.option.continue_on_collection_errors
        ):
            raise session.Interrupted(
                "%d error%s during collection"
                % (session.testsfailed, "s" if session.testsfailed != 1 else "")
            )

        if session.config.option.collectonly:
            return True

        coverage = self._cov_proc_count == 1 or self._cov_proc_count == -1

        if self._test_mode == 3:
            from wake.testing.fuzzing.fuzz_shrink import deserialize_random_state

            random.setstate(deserialize_random_state(self._test_random_state))
            console.print(f"Using random state\n {self._test_random_state}")
        else:
            random.seed(self._random_seeds[0])
            console.print(f"Using random seed '{self._random_seeds[0].hex()}'")

        if self._debug:
            set_exception_handler(partial(attach_debugger, seed=self._random_seeds[0]))

        if coverage:
            queue = SimpleQueue()

            if self._config.testing.cmd != "revm":
                last_coverage_sync = time.perf_counter()
                handler = CoverageHandler(self._config)
                set_coverage_handler(handler)

                def coverage_callback():
                    nonlocal last_coverage_sync
                    t = time.perf_counter()
                    if (
                        t - last_coverage_sync
                        >= self._config.testing.coverage_sync_timeout
                    ):
                        queue.put(handler.get_contract_ide_coverage())

                handler.set_callback(coverage_callback)
            else:
                from wake_rs import set_coverage_callback

                handler = NativeCoverageHandler(self._config)
                set_coverage_callback(lambda coverage: queue.put(coverage))

            # clear coverage file
            export_coverage(handler.latest_build, {}, {}, {})

            thread = Thread(target=export_thread, args=(queue, handler.latest_build))
            thread.start()
        else:
            handler = None

        try:
            for i, item in enumerate(session.items):
                nextitem = session.items[i + 1] if i + 1 < len(session.items) else None
                item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
                if session.shouldfail:
                    raise session.Failed(session.shouldfail)
                if session.shouldstop:
                    raise session.Interrupted(session.shouldstop)
        finally:
            if isinstance(handler, CoverageHandler):
                queue.put(handler.get_contract_ide_coverage())
                queue.put(None)
            elif isinstance(handler, NativeCoverageHandler):
                from wake_rs import sync_coverage

                sync_coverage()
                queue.put(None)

            chain_interfaces_manager.close_all()

        return True

    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        terminalreporter.section("Wake")

        for name, stats in sorted(get_fuzz_test_stats().items(), key=lambda x: x[0]):
            terminalreporter.write_line(f"Fuzz test '{name}':")

            for flow, rets in sorted(stats.items(), key=lambda x: x[0]):
                terminalreporter.write_line(f"  {flow}:")
                terminalreporter.write_line(f"    Success: {rets.pop(None, 0)}")
                for ret, count in sorted(rets.items(), key=lambda x: x[0] or ""):
                    terminalreporter.write_line(f"    {ret}: {count}")

            terminalreporter.write_line("")

        terminalreporter.write_line("Random seed: " + self._random_seeds[0].hex())
        if get_is_fuzzing():
            terminalreporter.write_line(
                "Executed sequence number: " + str(get_executing_sequence_num())
            )
            terminalreporter.write_line(
                "Executed flow number: " + str(get_executing_flow_num())
            )

        if self._crash_log_meta_data:
            terminalreporter.write_line("Crash logs:")
            for node, crash_log in self._crash_log_meta_data:
                terminalreporter.write_line(f"{node}: {crash_log}")
