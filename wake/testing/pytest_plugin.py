import logging
import multiprocessing
import multiprocessing.connection
import multiprocessing.synchronize
import os
import pickle
import random
import shutil
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import rich.progress
from pytest import Session
from rich.traceback import Traceback
from tblib import pickling_support

from wake.cli.console import console
from wake.config import WakeConfig
from wake.development.globals import (
    attach_debugger,
    chain_interfaces_manager,
    get_coverage_handler,
    reset_exception_handled,
    set_coverage_handler,
    set_exception_handler,
)
from wake.testing.coverage import (
    CoverageHandler,
    IdeFunctionCoverageRecord,
    IdePosition,
    export_merged_ide_coverage,
    write_coverage,
)
from wake.testing.fuzzing.fuzzer import compute_coverage_per_function
from wake.utils.tee import StderrTee, StdoutTee


class PytestWakePlugin:
    _config: WakeConfig
    _proc_count: Optional[int]
    _cov_proc_count: Optional[int]
    _random_seeds: List[bytes]
    _attach_first: bool
    _debug: bool

    def __init__(
        self,
        config: WakeConfig,
        debug: bool,
        proc_count: Optional[int],
        cov_proc_count: Optional[int],
        random_seeds: Iterable[bytes],
        attach_first: bool,
    ):
        self._config = config
        self._debug = debug
        self._proc_count = proc_count
        self._cov_proc_count = cov_proc_count
        self._random_seeds = list(random_seeds)
        self._attach_first = attach_first

    def pytest_runtest_setup(self, item):
        reset_exception_handled()

    def _run_test(
        self,
        session: Session,
        index: int,
        random_seed: bytes,
        log_file: Path,
        tee: bool,
        finished_event: multiprocessing.synchronize.Event,
        err_child_conn: multiprocessing.connection.Connection,
        cov_child_conn: multiprocessing.connection.Connection,
        coverage: Optional[CoverageHandler],
    ):
        def exception_handler(e: Exception) -> None:
            for ctx_manager in ctx_managers:
                ctx_manager.__exit__(None, None, None)
            ctx_managers.clear()

            exc_info = sys.exc_info()
            try:
                pickled = pickle.dumps(exc_info)
            except Exception:
                pickled = pickle.dumps(
                    (exc_info[0], Exception(repr(exc_info[1])), exc_info[2])
                )
            err_child_conn.send(pickled)
            finished_event.set()

            try:
                attach: bool = err_child_conn.recv()
                if attach:
                    sys.stdin = os.fdopen(0)
                    attach_debugger(e)
            finally:
                finished_event.set()

        last_coverage_sync = time.perf_counter()

        def coverage_callback() -> None:
            nonlocal last_coverage_sync
            t = time.perf_counter()
            if coverage is not None and t - last_coverage_sync > 5:
                cov_child_conn.send(coverage.get_contract_ide_coverage())
                last_coverage_sync = t

        ctx_managers = []

        pickling_support.install()
        random.seed(random_seed)

        set_exception_handler(exception_handler)
        if coverage is not None:
            set_coverage_handler(coverage)
            coverage.set_callback(coverage_callback)

        try:
            if tee:
                ctx_managers.append(StdoutTee(log_file))
                ctx_managers.append(StderrTee(log_file))
            else:
                logging.basicConfig(filename=log_file)
                f = open(log_file, "w")
                ctx_managers.append(f)
                ctx_managers.append(redirect_stdout(f))
                ctx_managers.append(redirect_stderr(f))

            for ctx_manager in ctx_managers:
                ctx_manager.__enter__()

            console.print(
                f"Using random seed '{random_seed.hex()}' for process #{index}"
            )

            for i, item in enumerate(session.items):
                nextitem = session.items[i + 1] if i + 1 < len(session.items) else None
                item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
                if session.shouldfail:
                    err_child_conn.send(
                        pickle.dumps(session.Failed(session.shouldfail))
                    )
                    finished_event.set()
                if session.shouldstop:
                    err_child_conn.send(
                        pickle.dumps(session.Interrupted(session.shouldstop))
                    )
                    finished_event.set()

            err_child_conn.send(None)
            if coverage is not None:
                # final coverage update
                cov_child_conn.send(coverage.get_contract_ide_coverage())
            finished_event.set()
        except Exception:
            pass
        finally:
            chain_interfaces_manager.close_all()
            for ctx_manager in ctx_managers:
                ctx_manager.__exit__(None, None, None)

    def _runtestloop_single(self, session: Session):
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

    def _runtestloop_multiprocess(self, session: Session):
        assert self._proc_count is not None
        verbose_coverage = False  # TODO
        # TODO use self._debug

        if self._cov_proc_count != 0:
            empty_coverage = CoverageHandler(self._config)
            # clear coverage file
            write_coverage({}, self._config.project_root_path / "wake-coverage.cov")
        else:
            empty_coverage = None

        logs_dir = self._config.project_root_path / ".wake" / "logs" / "testing"
        shutil.rmtree(logs_dir, ignore_errors=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        processes = {}
        for i in range(self._proc_count):
            finished_event = multiprocessing.Event()
            err_parent_conn, err_child_con = multiprocessing.Pipe()
            cov_parent_conn, cov_child_con = multiprocessing.Pipe()

            log_path = logs_dir / f"{i}.ansi"

            p = multiprocessing.Process(
                target=self._run_test,
                args=(
                    session,
                    i,
                    self._random_seeds[i],
                    log_path,
                    self._attach_first and i == 0,
                    finished_event,
                    err_child_con,
                    cov_child_con,
                    empty_coverage
                    if self._cov_proc_count == -1 or i < self._cov_proc_count
                    else None,
                ),
            )
            processes[i] = (p, finished_event, err_parent_conn, cov_parent_conn)
            p.start()

        try:
            with rich.progress.Progress(
                rich.progress.SpinnerColumn(finished_text="[green]⠿"),
                "[progress.description][yellow]{task.description}, "
                "[green]{task.fields[proc_rem]}[yellow] "
                "processes remaining{task.fields[coverage_info]}",
                console=console,
            ) as progress:
                exported_coverages: Dict[
                    int, Dict[Path, Dict[IdePosition, IdeFunctionCoverageRecord]]
                ] = {}

                if self._attach_first:
                    progress.stop()
                task = progress.add_task(
                    "Running", proc_rem=len(processes), coverage_info="", total=1
                )

                while len(processes):
                    to_be_removed = []
                    for i, (
                        p,
                        e,
                        err_parent_conn,
                        cov_parent_conn,
                    ) in processes.items():
                        finished = e.wait(0.125)
                        if finished:
                            to_be_removed.append(i)

                            exception_info = err_parent_conn.recv()
                            if exception_info is not None:
                                exception_info = pickle.loads(exception_info)

                            if exception_info is not None:
                                if (
                                    (not self._attach_first or i == 0)
                                    and not exception_info[0] is session.Failed
                                    and not exception_info[0] is session.Interrupted
                                ):
                                    tb = Traceback.from_exception(
                                        exception_info[0],
                                        exception_info[1],
                                        exception_info[2],
                                    )

                                    if not self._attach_first:
                                        progress.stop()

                                    console.print(tb)
                                    console.print(
                                        f"Process #{i} failed with an exception above."
                                    )

                                    attach = None
                                    while attach is None:
                                        response = input(
                                            "Would you like to attach the debugger? [y/n] "
                                        )
                                        if response == "y":
                                            attach = True
                                        elif response == "n":
                                            attach = False
                                else:
                                    attach = False

                                e.clear()
                                err_parent_conn.send(attach)
                                e.wait()
                                if not self._attach_first:
                                    progress.start()

                            progress.update(
                                task, proc_rem=len(processes) - len(to_be_removed)
                            )
                            if i == 0:
                                progress.start()

                        tmp = None
                        while cov_parent_conn.poll(0):
                            try:
                                tmp = cov_parent_conn.recv()
                            except EOFError:
                                break
                        if tmp is not None:
                            exported_coverages[i] = tmp
                            res = export_merged_ide_coverage(
                                list(exported_coverages.values())
                            )
                            if res:
                                write_coverage(
                                    res,
                                    self._config.project_root_path
                                    / "wake-coverage.cov",
                                )
                            cov_info = ""
                            if not self._attach_first and verbose_coverage:
                                cov_info = "\n[dark_goldenrod]" + "\n".join(
                                    [
                                        f"{fn_name}: [green]{fn_calls}[dark_goldenrod]"
                                        for (fn_name, fn_calls) in sorted(
                                            compute_coverage_per_function(res).items(),
                                            key=lambda x: x[1],
                                            reverse=True,
                                        )
                                    ]
                                )
                            progress.update(task, coverage_info=cov_info)
                        if finished:
                            cov_parent_conn.close()

                    for i in to_be_removed:
                        processes.pop(i)

                progress.update(task, description="Finished", completed=1)
        finally:
            for i, (p, e, err_parent_conn, cov_parent_conn) in processes.items():
                if p.is_alive():
                    p.terminate()
                p.join()

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

        if self._proc_count is None:
            self._runtestloop_single(session)
        else:
            self._runtestloop_multiprocess(session)

        return True
