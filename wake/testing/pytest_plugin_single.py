from functools import partial
from typing import Iterable, List, Optional

from pytest import Session

from datetime import datetime
import rich.traceback
from rich.console import Console

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
        if self._debug:
            attach_debugger(
                call.excinfo.type,
                call.excinfo.value,
                call.excinfo.tb,
                seed=self._random_seeds[0],
            )

        import os
        if get_fuzz_mode() != 0:
            return
        state = get_sequence_initial_internal_state()
        if state == b"":
            return
        crash_logs_dir = self._config.project_root_path / ".wake" / "logs" / "crashes"
        # shutil.rmtree(crash_logs_dir, ignore_errors=True)
        crash_logs_dir.mkdir(parents=True, exist_ok=True)
        # write crash log file.
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Assuming `call.execinfo` contains the crash information
        crash_log_file = crash_logs_dir / F"{timestamp}.txt"

        relative_path = os.path.relpath(node.fspath, self._config.project_root_path)


        # Write contents to the crash log file
        with crash_log_file.open('w') as f:
            f.write(f"Current test file: {relative_path}\n")
            f.write(f"executed flow number : {get_error_flow_num()}\n")
            f.write(f"Internal state of beginning of sequence : {state.hex()}\n")
            f.write(f"Assertion type: {call.excinfo.type}\n")
            f.write(f"Assertion value: {call.excinfo.value}\n")
            # Create the rich traceback object
            rich_tb = rich.traceback.Traceback.from_exception(
                call.excinfo.type, call.excinfo.value, call.excinfo.tb
            )
            file_console = Console(file=f, force_terminal=False)
            file_console.print(rich_tb)


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
