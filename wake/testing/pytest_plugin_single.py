from functools import partial
import os
from typing import Iterable, List, Optional

from pytest import Session

from wake.cli.console import console
from wake.config import WakeConfig
from wake.development.globals import (
    attach_debugger,
    chain_interfaces_manager,
    get_coverage_handler,
    random,
    reset_exception_handled,
    set_coverage_handler,
    set_exception_handler,
    get_sequence_initial_internal_state,
    get_error_flow_num,
    get_fuzz_mode,
)
from wake.testing.coverage import (
    CoverageHandler,
    export_merged_ide_coverage,
    write_coverage,
)
import pickle

class PytestWakePluginSingle:
    _config: WakeConfig
    _cov_proc_count: Optional[int]
    _random_seeds: List[bytes]
    _random_states: List[Optional[bytes]]
    _debug: bool

    def __init__(
        self,
        config: WakeConfig,
        debug: bool,
        cov_proc_count: Optional[int],
        random_seeds: Iterable[bytes],
        random_states: Iterable[Optional[bytes]],
    ):
        self._config = config
        self._debug = debug
        self._cov_proc_count = cov_proc_count
        self._random_seeds = list(random_seeds)
        self._random_states = list(random_states)

    def pytest_runtest_setup(self, item):
        reset_exception_handled()

    def pytest_exception_interact(self, node, call, report):
        import json
        from datetime import datetime
        import os

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
        crash_logs_dir = self._config.project_root_path / ".wake" / "logs" / "crashes"
        # shutil.rmtree(crash_logs_dir, ignore_errors=True)
        crash_logs_dir.mkdir(parents=True, exist_ok=True)
        # write crash log file.
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Assuming `call.execinfo` contains the crash information
        crash_log_file = crash_logs_dir / F"{timestamp}.json"

         # Find the test file in the traceback that's within project root
        tb = call.excinfo.tb
        test_file_path = None
        while tb:
            filename = tb.tb_frame.f_code.co_filename
            try:
                # Check if the file is within project root
                relative = os.path.relpath(filename, self._config.project_root_path)
                if not relative.startswith('..') and filename.endswith('.py'):
                    test_file_path = relative
                    break
            except ValueError:
                # relpath raises ValueError if paths are on different drives
                pass
            if hasattr(tb, 'tb_next'):
                tb = tb.tb_next

        if test_file_path is None:
            test_file_path = node.fspath  # fallback to node's path if no test file found

        crash_data = {
            "test_file": test_file_path,
            "crash_flow_number": get_error_flow_num(),
            "exception_content": {
                "type": str(call.excinfo.type),
                "value": str(call.excinfo.value),
            },
            "initial_random_state": random_state_dict,
        }
        with crash_log_file.open('w') as f:
            json.dump(crash_data, f, indent=2)

        console.print(f"Crash log written to {crash_log_file}")

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


        if len(self._random_states) > 0:
            assert self._random_states[0] is not None
            random.setstate(pickle.loads(self._random_states[0]))
            console.print(f"Using random state '{random.getstate()[1]}'")
        else:
            random.seed(self._random_seeds[0])
            console.print(f"Using random seed '{self._random_seeds[0].hex()}'")

        if self._debug:
            set_exception_handler(partial(attach_debugger, seed=self._random_seeds[0]))
        if coverage:
            set_coverage_handler(CoverageHandler(self._config))

        try:
            for i, item in enumerate(session.items):
                nextitem = session.items[i + 1] if i + 1 < len(session.items) else None
                item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
                if session.shouldfail:
                    raise session.Failed(session.shouldfail)
                if session.shouldstop:
                    raise session.Interrupted(session.shouldstop)
        finally:
            if coverage:
                coverage_handler = get_coverage_handler()
                assert coverage_handler is not None

                c = export_merged_ide_coverage(
                    [coverage_handler.get_contract_ide_coverage()]
                )
                write_coverage(c, self._config.project_root_path / "wake-coverage.cov")

            chain_interfaces_manager.close_all()

        return True

    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        terminalreporter.section("Wake")
        terminalreporter.write_line("Random seed: " + self._random_seeds[0].hex())
        terminalreporter.write_line("Executed flow number: " + str(get_error_flow_num()))
