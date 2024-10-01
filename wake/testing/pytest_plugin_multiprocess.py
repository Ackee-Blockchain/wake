import logging
import multiprocessing.connection
import os
import pickle
import queue
import signal
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import TracebackType
from typing import List, Optional, Type

import pytest
from pathvalidate import sanitize_filename
from pytest import Session
from tblib import pickling_support

from wake.cli.console import console
from wake.development.globals import (
    attach_debugger,
    chain_interfaces_manager,
    random,
    reset_exception_handled,
    set_coverage_handler,
    set_exception_handler,
)
from ipdb.__main__ import _init_pdb
from wake.testing.coverage import CoverageHandler
from wake.utils.tee import StderrTee, StdoutTee

from wake.testing.custom_pdb import CustomPdb


class PytestWakePluginMultiprocess:
    _index: int
    _conn: multiprocessing.connection.Connection
    _coverage: Optional[CoverageHandler]
    _log_file: Path
    _random_seed: bytes
    _tee: bool
    _debug: bool
    _exception_handled: bool

    _ctx_managers: List
    _keyboard_interrupt: bool

    def __init__(
        self,
        index: int,
        conn: multiprocessing.connection.Connection,
        queue: multiprocessing.Queue,
        coverage: Optional[CoverageHandler],
        log_dir: Path,
        random_seed: bytes,
        tee: bool,
        debug: bool,
    ):
        self._conn = conn
        self._index = index
        self._queue = queue
        self._coverage = coverage
        self._log_file = log_dir / sanitize_filename(f"process-{index}.ansi")
        self._random_seed = random_seed
        self._tee = tee
        self._debug = debug
        self._exception_handled = False

        self._keyboard_interrupt = False
        self._ctx_managers = []

    def _setup_stdio(self):
        if self._tee:
            self._ctx_managers.append(StdoutTee(self._log_file))
            self._ctx_managers.append(StderrTee(self._log_file))
        else:
            self._ctx_managers.append(redirect_stdout(self._f))
            self._ctx_managers.append(redirect_stderr(self._f))

        for ctx_manager in self._ctx_managers:
            ctx_manager.__enter__()

    def _cleanup_stdio(self):
        for ctx_manager in self._ctx_managers:
            ctx_manager.__exit__(None, None, None)
        self._ctx_managers.clear()

    def _exception_handler(
        self,
        e_type: Optional[Type[BaseException]],
        e: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:

        # After the keyboard interrupt, we do not interested in debugging.
        if self._keyboard_interrupt:
            return

        if self._exception_handled:
            return

        self._cleanup_stdio()
        self._exception_handled = True

        assert e_type is not None
        assert e is not None
        assert tb is not None

        try:
            pickled = pickle.dumps((e_type, e, tb))
        except Exception:
            pickled = pickle.dumps((e_type, Exception(repr(e)), tb))
        self._queue.put(("exception", self._index, pickled), block=True)

        attach: bool = self._conn.recv()
        try:
            if attach:
                sys.stdin = os.fdopen(0)
                attach_debugger(e_type, e, tb, seed=self._random_seed)
        finally:
            self._setup_stdio()
            self._conn.send(("exception_handled",))

    def pytest_configure(self, config: pytest.Config):
        self._f = open(self._log_file, "w")
        self._setup_stdio()
        logging.basicConfig(
            stream=sys.stdout,
            force=True,  # pyright: ignore reportGeneralTypeIssues
        )

    def pytest_unconfigure(self, config: pytest.Config):
        chain_interfaces_manager.close_all()
        self._cleanup_stdio()
        self._f.close()

    def pytest_collection_finish(self, session: Session):
        self._conn.send(("pytest_collection_finish", [i.nodeid for i in session.items]))

    def pytest_runtest_setup(self, item):
        reset_exception_handled()
        self._exception_handled = False

    def pytest_internalerror(
        self, excrepr, excinfo: pytest.ExceptionInfo[BaseException]
    ):
        try:
            pickled = pickle.dumps((excinfo.type, excinfo.value, excinfo.traceback))
        except Exception:
            pickled = pickle.dumps(
                (excinfo.type, Exception(repr(excinfo.value)), excinfo.traceback)
            )
        self._queue.put(("pytest_internalerror", self._index, pickled), block=True)

    def pytest_exception_interact(self, node, call, report):
        if self._debug and not self._exception_handled:
            self._exception_handler(
                call.excinfo.type, call.excinfo.value, call.excinfo.tb
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

        last_coverage_sync = time.perf_counter()

        def coverage_callback() -> None:
            nonlocal last_coverage_sync
            t = time.perf_counter()
            if self._coverage is not None and t - last_coverage_sync > 5:
                try:
                    self._queue.put(
                        (
                            "coverage",
                            self._index,
                            self._coverage.get_contract_ide_coverage(),
                        ),
                        timeout=0.125,
                    )
                    last_coverage_sync = t
                except queue.Full:
                    pass

        def custom_debugger():
            self._cleanup_stdio()
            import inspect

            current_frame = inspect.currentframe()
            assert current_frame is not None
            caller_frame = current_frame.f_back
            assert caller_frame is not None
            filename = caller_frame.f_code.co_filename
            lineno = caller_frame.f_lineno
            function_name = caller_frame.f_code.co_name

            source_lines, starting_line_no = inspect.getsourcelines(caller_frame)
            lines_to_show = 10
            relative_lineno = lineno - starting_line_no

            start_line = max(0, relative_lineno - lines_to_show // 2)
            end_line = min(len(source_lines), relative_lineno + lines_to_show // 2)

            source_lines_subset = source_lines[start_line:end_line]

            max_line_number = starting_line_no + end_line
            line_number_width = len(str(max_line_number))

            for idx, line in enumerate(source_lines_subset):
                if start_line + idx == relative_lineno:
                    source_lines_subset[idx] = f"--> {starting_line_no + start_line + idx:>{line_number_width}} {line}"  # Add '>>>' marker
                else:
                    source_lines_subset[idx] = f"    {starting_line_no + start_line + idx:>{line_number_width}} {line}"

            source_code = ''.join(source_lines_subset)

            debugging_data = pickle.dumps((filename, lineno, function_name, source_code))
            self._queue.put(("breakpoint", self._index, debugging_data), block=True)
            attach: bool = self._conn.recv()
            if attach:
                prev = sys.stdin
                sys.stdin = os.fdopen(0)
                frame = sys._getframe(1)
                p = CustomPdb(self)
                p.set_trace(frame)
            else:
                # trace nothing, same as continue
                self._conn.send(("breakpoint_handled",))

        sys.breakpointhook = custom_debugger

        pickling_support.install()

        def sigint_handler(signum, frame):
            self._keyboard_interrupt = True
            self._queue.put(("keyboard_interrupt", self._index))
            pytest.exit("Keyboard interrupt", returncode=0)

        signal.signal(signal.SIGINT, sigint_handler)

        if self._debug:
            set_exception_handler(self._exception_handler)
        if self._coverage is not None:
            set_coverage_handler(self._coverage)
            self._coverage.set_callback(coverage_callback)

        try:
            indexes = self._conn.recv()
            for i in range(len(indexes)):
                # set random seed before each test item
                random.seed(self._random_seed)
                console.print(f"Setting random seed '{self._random_seed.hex()}'")

                item = session.items[indexes[i]]
                nextitem = (
                    session.items[indexes[i + 1]] if i + 1 < len(indexes) else None
                )
                item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
                if session.shouldfail:
                    raise session.Failed(session.shouldfail)
                if session.shouldstop:
                    raise session.Interrupted(session.shouldstop)

            if self._coverage is not None:
                # final coverage sync
                self._queue.put(
                    (
                        "coverage",
                        self._index,
                        self._coverage.get_contract_ide_coverage(),
                    )
                )
        finally:
            chain_interfaces_manager.close_all()
            self._queue.put(("closing", self._index))
            return True

    def pytest_runtest_protocol(self, item, nextitem):
        self._queue.put(("pytest_runtest_protocol", self._index, item.nodeid))

    # do not forward pytest_runtest_logstart and pytest_runtest_logfinish as they write item location to stdout which may be different for each process

    def pytest_runtest_logreport(self, report: pytest.TestReport):
        # not sending exception report since the reason of exception is keyboard interrupt or at least triggered by keyboard interrupt
        if self._keyboard_interrupt:
            return
        self._queue.put(("pytest_runtest_logreport", self._index, report))

    def pytest_warning_recorded(self, warning_message, when, nodeid, location):
        self._queue.put(
            (
                "pytest_warning_recorded",
                self._index,
                warning_message,
                when,
                nodeid,
                location,
            )
        )

    def pytest_sessionfinish(self, session: Session, exitstatus: int):
        self._queue.put(("pytest_sessionfinish", self._index, exitstatus))

    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        terminalreporter.section("Wake")
        terminalreporter.write_line("Random seed: " + self._random_seed.hex())
