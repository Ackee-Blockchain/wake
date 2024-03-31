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
)
from wake.testing.coverage import (
    CoverageHandler,
    export_merged_ide_coverage,
    write_coverage,
)


class PytestWakePluginSingle:
    _config: WakeConfig
    _cov_proc_count: Optional[int]
    _random_seeds: List[bytes]
    _debug: bool

    def __init__(
        self,
        config: WakeConfig,
        debug: bool,
        cov_proc_count: Optional[int],
        random_seeds: Iterable[bytes],
    ):
        self._config = config
        self._debug = debug
        self._cov_proc_count = cov_proc_count
        self._random_seeds = list(random_seeds)

    def pytest_runtest_setup(self, item):
        reset_exception_handled()

    def pytest_exception_interact(self, node, call, report):
        if self._debug:
            attach_debugger(call.excinfo.type, call.excinfo.value, call.excinfo.tb)

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

        random.seed(self._random_seeds[0])
        console.print(f"Using random seed '{self._random_seeds[0].hex()}'")

        if self._debug:
            set_exception_handler(attach_debugger)
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
