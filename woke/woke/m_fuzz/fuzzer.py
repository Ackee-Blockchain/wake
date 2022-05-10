import inspect
import logging
import multiprocessing
import multiprocessing.connection
import multiprocessing.synchronize
import os
import pickle
import random
import sys
import types
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import TracebackType
from typing import Callable, Iterable, Optional, Tuple

import brownie
from IPython.core.debugger import BdbQuit_excepthook
from brownie import rpc, web3
from brownie._config import CONFIG
from brownie.test.managers.runner import RevertContextManager
from ipdb.__main__ import _init_pdb
from pathvalidate import sanitize_filename  # type: ignore
from rich.traceback import Traceback
from tblib import pickling_support

from woke.a_config import WokeConfig
from woke.x_cli.console import console


def __setup(port: int) -> None:
    brownie.reverts = RevertContextManager
    active_network = CONFIG.set_active_network("development")

    web3.connect(f"http://localhost:{port}")
    cmd = "ganache-cli"
    cmd_settings = active_network["cmd_settings"]
    cmd_settings["port"] = port

    rpc.launch(cmd, **cmd_settings)


def __attach_debugger() -> None:
    if sys.excepthook != BdbQuit_excepthook:
        BdbQuit_excepthook.excepthook_ori = sys.excepthook
        sys.excepthook = BdbQuit_excepthook
    p = _init_pdb(commands=["from IPython import embed"])
    p.reset()
    p.interaction(None, sys.exc_info()[2])


def __run(
    fuzz_test: Callable,
    index: int,
    port: int,
    random_seed: bytes,
    log_file: Path,
    finished_event: multiprocessing.synchronize.Event,
    child_conn: multiprocessing.connection.Connection,
):
    pickling_support.install()
    random.seed(random_seed)

    logging.basicConfig(filename=log_file)

    try:
        with log_file.open("w") as f, redirect_stdout(f), redirect_stderr(f):
            print(f"Using seed '{random_seed.hex()}' for process #{index}")
            __setup(port)

            project = brownie.project.load()

            brownie.chain.reset()

            args = []
            for arg in inspect.getfullargspec(fuzz_test).args:
                if arg in {"a", "accounts"}:
                    args.append(brownie.accounts)
                elif arg == "chain":
                    args.append(brownie.chain)
                elif arg == "Contract":
                    args.append(brownie.Contract)
                elif arg == "history":
                    args.append(brownie.history)
                elif arg == "interface":
                    args.append(project.interface)
                elif arg == "rpc":
                    args.append(brownie.rpc)
                elif arg == "web3":
                    args.append(brownie.web3)
                elif arg in project.keys():
                    args.append(project[arg])
                else:
                    raise ValueError(
                        f"Unable to set value for '{arg}' argument in '{fuzz_test.__name__}' function."
                    )
            fuzz_test(*args)

            child_conn.send(None)
            finished_event.set()
    except Exception:
        child_conn.send(pickle.dumps(sys.exc_info()))
        finished_event.set()

        try:
            attach: bool = child_conn.recv()
            if attach:
                sys.stdin = os.fdopen(0)
                __attach_debugger()
        finally:
            finished_event.set()
    finally:
        with log_file.open("a") as f, redirect_stdout(f), redirect_stderr(f):
            rpc.kill()


def fuzz(
    config: WokeConfig,
    fuzz_test: types.FunctionType,
    process_count: int,
    seeds: Iterable[bytes],
    logs_dir: Path,
):
    random_seeds = list(seeds)
    if len(random_seeds) < process_count:
        for i in range(process_count - len(random_seeds)):
            random_seeds.append(os.urandom(8))

    processes = dict()
    for i, seed in zip(range(process_count), random_seeds):
        console.print(f"Using seed '{seed.hex()}' for process #{i}")
        finished_event = multiprocessing.Event()
        parent_conn, child_conn = multiprocessing.Pipe()

        log_path = logs_dir / sanitize_filename(
            f"{fuzz_test.__module__}.{fuzz_test.__name__}_{i}.ansi"
        )

        p = multiprocessing.Process(
            target=__run,
            args=(
                fuzz_test,
                i,
                8545 + i,
                seed,
                log_path,
                finished_event,
                child_conn,
            ),
        )
        processes[i] = (p, finished_event, parent_conn, child_conn)
        p.start()

    while len(processes):
        to_be_removed = []
        for i, (p, e, parent_conn, child_conn) in processes.items():
            finished = e.wait(0.125)
            if finished:
                to_be_removed.append(i)

                exception_info = parent_conn.recv()
                if exception_info is not None:
                    exception_info = pickle.loads(exception_info)

                if exception_info is not None:
                    tb = Traceback.from_exception(
                        exception_info[0], exception_info[1], exception_info[2]
                    )
                    console.print(tb)
                    console.print(f"Process #{i} failed with an exception above.")

                    attach = None
                    while attach is None:
                        response = input(
                            "Would you like to attach the debugger? [y/n] "
                        )
                        if response == "y":
                            attach = True
                        elif response == "n":
                            attach = False

                    e.clear()
                    parent_conn.send(attach)
                    e.wait()
                else:
                    console.print(f"Process #{i} finished without issues.")
        for i in to_be_removed:
            processes.pop(i)
