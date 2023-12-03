import logging
import multiprocessing
import multiprocessing.connection
import multiprocessing.synchronize
import os
import pickle
import random
import sys
import time
import types
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import rich.progress
from pathvalidate import sanitize_filename  # type: ignore
from rich.traceback import Traceback
from tblib import pickling_support

from wake.cli.console import console
from wake.config import WakeConfig
from wake.development.globals import (
    attach_debugger,
    chain_interfaces_manager,
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
from wake.utils.tee import StderrTee, StdoutTee


def _run_core(
    fuzz_test: Callable,
    index: int,
    random_seed: bytes,
    finished_event: multiprocessing.synchronize.Event,
    err_child_conn: multiprocessing.connection.Connection,
    cov_child_conn: multiprocessing.connection.Connection,
    coverage: Optional[CoverageHandler],
):
    console.print(f"Using random seed '{random_seed.hex()}' for process #{index}")

    fuzz_test()

    err_child_conn.send(None)
    if coverage is not None:
        # final coverage update
        cov_child_conn.send(coverage.get_contract_ide_coverage())
    finished_event.set()


def _run(
    fuzz_test: Callable,
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

        _run_core(
            fuzz_test,
            index,
            random_seed,
            finished_event,
            err_child_conn,
            cov_child_conn,
            coverage,
        )
    except Exception:
        pass
    finally:
        chain_interfaces_manager.close_all()
        for ctx_manager in ctx_managers:
            ctx_manager.__exit__(None, None, None)


def compute_coverage_per_function(
    ide_cov: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, int]:
    funcs_cov = {}
    fn_names = []
    for path_rec in ide_cov.values():
        fn_names.extend([rec["name"] for rec in path_rec if rec["coverageHits"] > 0])

    for fn_path, path_rec in ide_cov.items():
        for fn_rec in path_rec:
            if fn_rec["coverageHits"] == 0:
                continue
            if fn_names.count(fn_rec["name"]) > 1:
                funcs_cov[f"{fn_path}:{fn_rec['name']}"] = fn_rec["coverageHits"]
            else:
                funcs_cov[fn_rec["name"]] = fn_rec["coverageHits"]

    return funcs_cov


def fuzz(
    config: WakeConfig,
    func_name: str,
    fuzz_test: types.FunctionType,
    process_count: int,
    random_seeds: Iterable[bytes],
    logs_dir: Path,
    attach_first: bool,
    cov_proc_num: int,
    verbose_coverage: bool,
):
    if cov_proc_num != 0:
        empty_coverage = CoverageHandler(config)
        # clear coverage file
        write_coverage({}, config.project_root_path / "wake-coverage.cov")
    else:
        empty_coverage = None
    processes = dict()
    for i, seed in zip(range(process_count), random_seeds):
        console.print(f"Using random seed '{seed.hex()}' for process #{i}")
        finished_event = multiprocessing.Event()
        err_parent_conn, err_child_con = multiprocessing.Pipe()
        cov_parent_conn, cov_child_con = multiprocessing.Pipe()

        log_path = logs_dir / sanitize_filename(
            f"{fuzz_test.__module__}.{func_name}_{i}.ansi"
        )

        p = multiprocessing.Process(
            target=_run,
            args=(
                fuzz_test,
                i,
                seed,
                log_path,
                attach_first and i == 0,
                finished_event,
                err_child_con,
                cov_child_con,
                empty_coverage if i < cov_proc_num else None,
            ),
        )
        processes[i] = (p, finished_event, err_parent_conn, cov_parent_conn)
        p.start()

    try:
        with rich.progress.Progress(
            rich.progress.SpinnerColumn(finished_text="[green]⠿"),
            "[progress.description][yellow]{task.description}, "
            "[green]{task.fields[thr_rem]}[yellow] "
            "processes remaining{task.fields[coverage_info]}",
        ) as progress:
            exported_coverages: Dict[
                int, Dict[Path, Dict[IdePosition, IdeFunctionCoverageRecord]]
            ] = {}

            if attach_first:
                progress.stop()
            task = progress.add_task(
                "Testing", thr_rem=len(processes), coverage_info="", total=1
            )

            while len(processes):
                to_be_removed = []
                for i, (p, e, err_parent_conn, cov_parent_conn) in processes.items():
                    finished = e.wait(0.125)
                    if finished:
                        to_be_removed.append(i)

                        exception_info = err_parent_conn.recv()
                        if exception_info is not None:
                            exception_info = pickle.loads(exception_info)

                        if exception_info is not None:
                            if not attach_first or i == 0:
                                tb = Traceback.from_exception(
                                    exception_info[0],
                                    exception_info[1],
                                    exception_info[2],
                                )

                                if not attach_first:
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
                            if not attach_first:
                                progress.start()

                        progress.update(
                            task, thr_rem=len(processes) - len(to_be_removed)
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
                                res, config.project_root_path / "wake-coverage.cov"
                            )
                        cov_info = ""
                        if not attach_first and verbose_coverage:
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
