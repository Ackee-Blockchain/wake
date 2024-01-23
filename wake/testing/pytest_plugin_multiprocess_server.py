import multiprocessing
import multiprocessing.connection
import pickle
import shutil
from contextlib import nullcontext
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import pytest
import rich.progress
import rich.traceback

from wake.cli.console import console
from wake.config import WakeConfig
from wake.testing.coverage import (
    CoverageHandler,
    IdeFunctionCoverageRecord,
    IdePosition,
    export_merged_ide_coverage,
    write_coverage,
)

from .pytest_plugin_multiprocess import PytestWakePluginMultiprocess


class PytestWakePluginMultiprocessServer:
    _config: WakeConfig
    _coverage: int
    _proc_count: int
    _processes: Dict[
        int, Tuple[multiprocessing.Process, multiprocessing.connection.Connection]
    ]
    _random_seeds: List[bytes]
    _attach_first: bool
    _debug: bool
    _pytest_args: List[str]
    _queue: multiprocessing.Queue
    _exported_coverages: Dict[
        int, Dict[Path, Dict[IdePosition, IdeFunctionCoverageRecord]]
    ]

    def __init__(
        self,
        config: WakeConfig,
        coverage: int,
        proc_count: int,
        random_seeds: List[bytes],
        attach_first: bool,
        debug: bool,
        dist: str,
        pytest_args: List[str],
    ):
        self._config = config
        self._coverage = coverage
        self._proc_count = proc_count
        self._processes = {}
        self._random_seeds = random_seeds
        self._attach_first = attach_first
        self._debug = debug
        self._dist = dist
        self._pytest_args = pytest_args
        self._exported_coverages = {i: {} for i in range(self._proc_count)}

    def pytest_sessionstart(self, session: pytest.Session):
        if self._coverage != 0:
            empty_coverage = CoverageHandler(self._config)
            # clear coverage file
            write_coverage({}, self._config.project_root_path / "wake-coverage.cov")
        else:
            empty_coverage = None

        logs_dir = self._config.project_root_path / ".wake" / "logs" / "testing"
        shutil.rmtree(logs_dir, ignore_errors=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        self._queue = multiprocessing.Queue(1000)

        for i in range(self._proc_count):
            parent_conn, child_conn = multiprocessing.Pipe()
            p = multiprocessing.Process(
                target=pytest.main,
                args=(self._pytest_args,),
                kwargs={
                    "plugins": [
                        PytestWakePluginMultiprocess(
                            i,
                            child_conn,  # pyright: ignore reportGeneralTypeIssues
                            self._queue,
                            empty_coverage,
                            logs_dir,
                            self._random_seeds[i],
                            self._attach_first and i == 0,
                            self._debug,
                        ),
                    ]
                },
            )

            self._processes[i] = (  # pyright: ignore reportGeneralTypeIssues
                p,
                parent_conn,
            )
            p.start()

    def pytest_sessionfinish(self, session: pytest.Session):
        self._queue.cancel_join_thread()
        for p, conn in self._processes.values():
            p.terminate()
            p.join()
            conn.close()

        self._queue.close()

        # flush coverage
        res = export_merged_ide_coverage(list(self._exported_coverages.values()))
        write_coverage(res, self._config.project_root_path / "wake-coverage.cov")

    def pytest_report_teststatus(
        self,
        report: Union[pytest.CollectReport, pytest.TestReport],
        config: pytest.Config,
    ):
        return

    def pytest_runtestloop(self, session: pytest.Session):
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

        collected = []
        for i in range(self._proc_count):
            cmd, data = self._processes[i][1].recv()
            assert cmd == "pytest_collection_finish"
            collected.append(data)

        for i in range(1, self._proc_count):
            if collected[0] != collected[i]:
                raise Exception(
                    f"Collected different tests in processes:\n{collected[0]}\n{collected[i]}"
                )

        for i in range(self._proc_count):
            if self._dist == "uniform":
                step = len(collected[0]) // self._proc_count
                if i == self._proc_count - 1:
                    self._processes[i][1].send(list(range(i * step, len(collected[0]))))
                else:
                    self._processes[i][1].send(list(range(i * step, (i + 1) * step)))
            elif self._dist == "duplicated":
                self._processes[i][1].send(list(range(len(collected[0]))))
            else:
                raise Exception(f"Unknown distribution: {self._dist}")

        attach_first = False
        test_reports: Dict[int, Dict[str, str]] = {
            i: {} for i in range(self._proc_count)
        }
        current_tests = {i: None for i in range(self._proc_count)}
        reports = []

        ctx = (
            rich.progress.Progress(
                rich.progress.SpinnerColumn(finished_text="[green]⠿"),
                "[progress.description][yellow]{task.description} ",
                console=console,
            )
            if not self._attach_first
            else nullcontext()
        )

        try:
            with ctx as progress:
                if progress is not None:
                    tasks = [
                        progress.add_task(f"#{i} starting", total=1)
                        for i in range(self._proc_count)
                    ]
                else:
                    tasks = []

                while self._processes:
                    msg = self._queue.get()
                    index = msg[1]
                    if msg[0] == "pytest_runtest_protocol":
                        current_tests[index] = msg[2]

                        if progress is not None:
                            self._update_progress(
                                progress,
                                index,
                                tasks[index],
                                current_tests[index],
                                test_reports[index],
                            )
                    elif msg[0] == "coverage":
                        self._exported_coverages[index] = msg[2]
                        res = export_merged_ide_coverage(
                            list(self._exported_coverages.values())
                        )
                        write_coverage(
                            res, self._config.project_root_path / "wake-coverage.cov"
                        )
                    elif msg[0] == "exception":
                        exception_info = pickle.loads(msg[2])
                        tb = rich.traceback.Traceback.from_exception(
                            exception_info[0],
                            exception_info[1],
                            exception_info[2],
                        )

                        if progress is not None:
                            progress.stop()

                            console.print(tb)
                            console.print(
                                f"Process #{index} failed with an exception above."
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

                        self._processes[index][1].send(attach)

                        # wait for debugger to finish
                        assert self._processes[index][1].recv() == (
                            "exception_handled",
                        )
                        if progress is not None:
                            progress.start()
                    elif msg[0] == "pytest_runtest_logreport":
                        report: pytest.TestReport = msg[2]
                        reports.append(report)
                        self._process_teststatus(index, session, report, test_reports)

                        if progress is not None:
                            self._update_progress(
                                progress,
                                index,
                                tasks[index],
                                current_tests[index],
                                test_reports[index],
                            )
                    elif msg[0] == "pytest_warning_recorded":
                        session.config.hook.pytest_warning_recorded.call_historic(
                            kwargs={
                                "warning_message": msg[2],
                                "when": msg[3],
                                "nodeid": msg[4],
                                "location": msg[5],
                            },
                        )
                    elif msg[0] == "pytest_sessionfinish":
                        if progress is not None:
                            progress.update(tasks[index], description=f"Finished")

                        self._processes.pop(index)
                    elif msg[0] == "pytest_internalerror":
                        exc_info = pytest.ExceptionInfo.from_exc_info(
                            pickle.loads(msg[2])
                        )
                        print(f"Process #{index} failed with an internal error:")
                        session.config.hook.pytest_internalerror(
                            excrepr=exc_info.getrepr(style="short"), excinfo=exc_info
                        )
        finally:
            print("")
            for report in reports:
                session.config.hook.pytest_runtest_logreport(report=report)

        return True

    def _update_progress(
        self,
        progress: rich.progress.Progress,
        index: int,
        task_id: rich.progress.TaskID,
        current_test: Optional[str],
        test_reports: Dict[str, str],
    ):
        progress.update(
            task_id,
            description=(
                f"#{index} running {current_test}\n{''.join(test_reports.values())}"
                if current_test is not None
                else f"#{index} starting\n{''.join(test_reports.values())}"
            ),
        )

    def _process_teststatus(
        self,
        index: int,
        session: pytest.Session,
        report: pytest.TestReport,
        test_reports: Dict[int, Dict[str, str]],
    ):
        category, letter, word = session.config.hook.pytest_report_teststatus(
            report=report, config=session.config
        )
        if not isinstance(word, tuple):
            markup = None
        else:
            word, markup = word

        if not letter and not word:
            return

        if markup is None:
            was_xfail = hasattr(report, "wasxfail")
            if report.passed and not was_xfail:
                markup = {"green": True}
            elif report.passed and was_xfail:
                markup = {"yellow": True}
            elif report.failed:
                markup = {"red": True}
            elif report.skipped:
                markup = {"yellow": True}
            else:
                markup = {}

        msg_start = []
        msg_end = []
        for m in markup.keys():
            msg_start.append(f"[{m}]")
            msg_end.append(f"[/{m}]")
        msg_end.reverse()

        if session.config.option.verbose <= 0:
            test_reports[index][
                report.nodeid
            ] = f"{''.join(msg_start)}{letter}{''.join(msg_end)}"
        else:
            test_reports[index][
                report.nodeid
            ] = f"{''.join(msg_start)}{word}{''.join(msg_end)}"
