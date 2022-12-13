import copy
import inspect
import json
import logging
import multiprocessing
import multiprocessing.connection
import multiprocessing.synchronize
import os
import pickle
import random
import subprocess
import sys
import time
import types
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from time import sleep
from typing import Callable, Dict, Iterable, Optional
from urllib.error import URLError

import rich.progress
from ipdb.__main__ import _init_pdb
from IPython.core.debugger import BdbQuit_excepthook
from IPython.utils.io import Tee
from pathvalidate import sanitize_filename  # type: ignore
from rich.traceback import Traceback
from tblib import pickling_support

from woke.cli.console import console
from woke.config import WokeConfig
from woke.testing.core import default_chain
from woke.testing.coverage import Coverage, CoverageProvider, get_merged_ide_coverage


def _setup(port: int, network_id: str) -> subprocess.Popen:
    if network_id == "anvil":
        args = [
            "anvil",
            "--port",
            str(port),
            "--prune-history",
            "--gas-price",
            "0",
            "--base-fee",
            "0",
            "--steps-tracing",
        ]
    elif network_id == "ganache":
        args = ["ganache-cli", "--port", str(port)]
    elif network_id == "hardhat":
        args = ["npx", "hardhat", "node", "--port", str(port)]
    else:
        raise ValueError(f"Unknown network ID '{network_id}'")

    return subprocess.Popen(args, stdout=subprocess.DEVNULL)


def _attach_debugger() -> None:
    # TODO Implement `ipdb` package functionalities
    # This function relies on `ipdb` internal functions
    # We could implement all the `ipdb` functionalities ourselves (it is rather small codebase)
    if sys.excepthook != BdbQuit_excepthook:
        BdbQuit_excepthook.excepthook_ori = sys.excepthook
        sys.excepthook = BdbQuit_excepthook
    p = _init_pdb(
        commands=["import IPython", "alias embed() IPython.embed(colors='neutral')"]
    )
    p.reset()
    p.interaction(None, sys.exc_info()[2])


def _run_core(
    fuzz_test: Callable,
    index: int,
    random_seed: bytes,
    finished_event: multiprocessing.synchronize.Event,
    err_child_conn: multiprocessing.connection.Connection,
    cov_child_conn: multiprocessing.connection.Connection,
    coverage: Optional[Coverage],
):
    print(f"Using seed '{random_seed.hex()}' for process #{index}")

    try:
        default_chain.reset()
    except NotImplementedError:
        logging.warning("Development chain does not support resetting")

    args = []
    for arg in inspect.getfullargspec(fuzz_test).args:
        if arg == "coverage":
            if coverage is not None:
                args.append(
                    (
                        CoverageProvider(
                            coverage, default_chain.dev_chain.get_block_number()
                        ),
                        cov_child_conn,
                    )
                )
            else:
                args.append(None)
        else:
            raise ValueError(
                f"Unable to set value for '{arg}' argument in '{fuzz_test.__name__}' function."
            )

    fuzz_test(*args)

    err_child_conn.send(None)
    finished_event.set()


def _run(
    fuzz_test: Callable,
    index: int,
    port: int,
    random_seed: bytes,
    log_file: Path,
    tee: bool,
    finished_event: multiprocessing.synchronize.Event,
    err_child_conn: multiprocessing.connection.Connection,
    cov_child_conn: multiprocessing.connection.Connection,
    network_id: str,
    coverage: Optional[Coverage],
):
    pickling_support.install()
    random.seed(random_seed)

    chain_process = _setup(port, network_id)

    start = time.perf_counter()
    while True:
        gen = None
        try:
            gen = default_chain.connect(f"http://localhost:{port}")
            gen.__enter__()
            break
        except (ConnectionRefusedError, URLError):
            if gen is not None:
                gen.__exit__(None, None, None)
            sleep(0.1)
            if time.perf_counter() - start > 10:
                raise

    try:
        if not tee:
            logging.basicConfig(filename=log_file)

        if tee:
            with closing(Tee(log_file)):
                _run_core(
                    fuzz_test,
                    index,
                    random_seed,
                    finished_event,
                    err_child_conn,
                    cov_child_conn,
                    coverage,
                )
        else:
            with log_file.open("w") as f, redirect_stdout(f), redirect_stderr(f):
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
        err_child_conn.send(pickle.dumps(sys.exc_info()))
        finished_event.set()

        try:
            attach: bool = err_child_conn.recv()
            if attach:
                sys.stdin = os.fdopen(0)
                _attach_debugger()
        finally:
            finished_event.set()
    finally:
        gen.__exit__(None, None, None)
        with log_file.open("a") as f, redirect_stdout(f), redirect_stderr(f):
            chain_process.kill()


def fuzz(
    config: WokeConfig,
    fuzz_test: types.FunctionType,
    process_count: int,
    seeds: Iterable[bytes],
    logs_dir: Path,
    passive: bool,
    network_id: str,
    cov_proc_num: int,
):
    random_seeds = list(seeds)
    if len(random_seeds) < process_count:
        for i in range(process_count - len(random_seeds)):
            random_seeds.append(os.urandom(8))

    coverage = Coverage()
    processes = dict()
    for i, seed in zip(range(process_count), random_seeds):
        console.print(f"Using seed '{seed.hex()}' for process #{i}")
        finished_event = multiprocessing.Event()
        err_parent_conn, err_child_con = multiprocessing.Pipe()
        cov_parent_conn, cov_child_conn = multiprocessing.Pipe()

        log_path = logs_dir / sanitize_filename(
            f"{fuzz_test.__module__}.{fuzz_test.__name__}_{i}.ansi"
        )

        proc_cov = copy.deepcopy(coverage) if i < cov_proc_num else None

        p = multiprocessing.Process(
            target=_run,
            args=(
                fuzz_test,
                i,
                8545 + i,
                seed,
                log_path,
                passive and i == 0,
                finished_event,
                err_child_con,
                cov_child_conn,
                network_id,
                proc_cov,
            ),
        )
        processes[i] = (p, finished_event, err_parent_conn, cov_parent_conn)
        p.start()

    with rich.progress.Progress(
        rich.progress.SpinnerColumn(finished_text="[green]⠿"),
        "[progress.description][yellow]{task.description}, "
        "[green]{task.fields[thr_rem]}[yellow] "
        "processes remaining",
    ) as progress:
        coverages: Dict[int, Coverage] = {}

        if passive:
            progress.stop()
        task = progress.add_task("Fuzzing", thr_rem=len(processes), total=1)

        while len(processes):
            to_be_removed = []
            for i, (p, e, err_parent_conn, cov_parent_conn) in processes.items():
                finished = e.wait(0.125)
                if finished:
                    to_be_removed.append(i)

                    exception_info = err_parent_conn.recv()
                    if exception_info is not None:
                        print(exception_info)
                        exception_info = pickle.loads(exception_info)

                    if exception_info is not None:
                        if not passive or i == 0:
                            tb = Traceback.from_exception(
                                exception_info[0], exception_info[1], exception_info[2]
                            )

                            if not passive:
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
                        if not passive:
                            progress.start()

                    progress.update(task, thr_rem=len(processes) - len(to_be_removed))
                    if i == 0:
                        progress.start()
                while cov_parent_conn.poll():
                    coverage: Coverage = cov_parent_conn.recv()
                    coverages[i] = coverage
                    res = get_merged_ide_coverage(list(coverages.values()))
                    if res:
                        ide_cov, ide_cov_per_trans = res
                        with open("woke-coverage.cov", "w") as f:
                            f.write(json.dumps(ide_cov, indent=4, sort_keys=True))
                        with open("woke-coverage-per-trans.cov", "w") as f:
                            f.write(
                                json.dumps(ide_cov_per_trans, indent=4, sort_keys=True)
                            )
            for i in to_be_removed:
                processes.pop(i)
        progress.update(task, description="Finished", completed=1)
