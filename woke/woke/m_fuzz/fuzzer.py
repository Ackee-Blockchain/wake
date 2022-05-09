import inspect
import logging
import multiprocessing
import multiprocessing.connection
import multiprocessing.synchronize
import os
import pickle
import platform
import random
import sys
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import TracebackType
from typing import Callable, Iterable, Optional, Tuple

import brownie
import ipdb
from brownie import rpc, web3
from brownie._config import CONFIG
from brownie.test.managers.runner import RevertContextManager
from rich.traceback import Traceback
from tblib import pickling_support

from woke.a_config import WokeConfig
from woke.x_cli.console import console


class Process(multiprocessing.Process):
    __parent_conn: multiprocessing.connection.Connection
    __self_conn: multiprocessing.connection.Connection
    __exception: Optional[Tuple[type, BaseException, TracebackType]]
    __finished_event: multiprocessing.synchronize.Event

    def __init__(
        self, finished_event: multiprocessing.synchronize.Event, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.__parent_conn, self.__self_conn = multiprocessing.Pipe()
        self.__exception = None
        self.__finished_event = finished_event

    def run(self):
        try:
            multiprocessing.Process.run(self)
            self.__self_conn.send(None)
            self.__finished_event.set()
        except Exception:
            self.__self_conn.send(pickle.dumps(sys.exc_info()))
            self.__finished_event.set()

            try:
                attach: bool = self.__self_conn.recv()
                if attach:
                    sys.stdin = os.fdopen(0)
                    ipdb.post_mortem()
            finally:
                self.__finished_event.set()

    def set_attach_debugger(self, attach: bool) -> None:
        self.__parent_conn.send(attach)

    @property
    def exception(self) -> Optional[Tuple[type, BaseException, TracebackType]]:
        if self.__parent_conn.poll():
            info = self.__parent_conn.recv()
            if info is None:
                self.__exception = None
            else:
                self.__exception = pickle.loads(info)
        return self.__exception


def __setup(port: int) -> None:
    brownie.reverts = RevertContextManager
    active_network = CONFIG.set_active_network("development")

    web3.connect(f"http://localhost:{port}")
    cmd = "ganache-cli"
    cmd_settings = active_network["cmd_settings"]
    cmd_settings["port"] = port

    rpc.launch(cmd, **cmd_settings)


def __run(
    fuzz_test: Callable, index: int, port: int, random_seed: bytes, log_file: Path
):
    pickling_support.install()
    random.seed(random_seed)

    logging.basicConfig(filename=log_file)

    with log_file.open("w") as f, redirect_stdout(f), redirect_stderr(f):
        try:
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
        finally:
            rpc.kill()


def fuzz(
    config: WokeConfig, fuzz_test: Callable, process_count: int, seeds: Iterable[bytes]
):
    logs_dir = config.project_root_path / ".woke-logs" / "fuzz" / str(int(time.time()))
    logs_dir.mkdir(parents=True, exist_ok=False)
    latest_dir = logs_dir.parent / "latest"

    # create `latest` symlink
    if platform.system() != "Windows":
        if latest_dir.is_symlink():
            latest_dir.unlink()
        latest_dir.symlink_to(logs_dir, target_is_directory=True)

    random_seeds = list(seeds)
    if len(random_seeds) < process_count:
        for i in range(process_count - len(random_seeds)):
            random_seeds.append(os.urandom(8))

    processes = dict()
    for i, seed in zip(range(process_count), random_seeds):
        console.print(f"Using seed '{seed.hex()}' for process #{i}")
        finished_event = multiprocessing.Event()
        p = Process(
            finished_event,
            target=__run,
            args=(fuzz_test, i, 8545 + i, seed, logs_dir / f"fuzz{i}.ansi"),
        )
        processes[i] = (p, finished_event)
        p.start()

    while len(processes):
        to_be_removed = []
        for i, (p, e) in processes.items():
            finished = e.wait(0.125)
            if finished:
                to_be_removed.append(i)
                if p.exception is not None:
                    tb = Traceback.from_exception(
                        p.exception[0], p.exception[1], p.exception[2]
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
                    p.set_attach_debugger(attach)
                    e.wait()
                else:
                    console.print(f"Process #{i} finished without issues.")
        for i in to_be_removed:
            processes.pop(i)
