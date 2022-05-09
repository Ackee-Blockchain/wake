import inspect
import logging
import multiprocessing
import multiprocessing.connection
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__parent_conn, self.__self_conn = multiprocessing.Pipe()
        self.__exception = None

    def run(self):
        try:
            multiprocessing.Process.run(self)
            self.__self_conn.send(None)
        except Exception:
            self.__self_conn.send(pickle.dumps(sys.exc_info()))

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

    processes = []
    for i, seed in zip(range(process_count), random_seeds):
        console.print(f"Using seed '{seed.hex()}' for process #{i}")
        p = Process(
            target=__run,
            args=(fuzz_test, i, 8545 + i, seed, logs_dir / f"fuzz{i}.ansi"),
        )
        processes.append(p)
        p.start()

    for i, p in enumerate(processes):
        p.join()
        if p.exception is not None:
            tb = Traceback.from_exception(
                p.exception[0], p.exception[1], p.exception[2]
            )
            console.print(tb)
            console.print(f"Process #{i} failed with an exception above.")
