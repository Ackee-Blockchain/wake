from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from random import Random
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Callable,
    DefaultDict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
)
from urllib.error import HTTPError

import rich.traceback
import rich_click
from ipdb.__main__ import _init_pdb

from wake.config import WakeConfig
from wake.core import get_logger
from wake.development.chain_interfaces import ChainInterfaceAbc
from wake.development.json_rpc import JsonRpcError
from wake.utils.file_utils import is_relative_to

if TYPE_CHECKING:
    from wake.testing.coverage import CoverageHandler


logger = get_logger(__name__)


random = Random()


# must be declared before functions that use it because of a bug in Python (https://bugs.python.org/issue34939)
_exception_handler: Optional[
    Callable[
        [
            Optional[Type[BaseException]],
            Optional[BaseException],
            Optional[TracebackType],
        ],
        None,
    ]
] = None
_exception_handled = False

_initial_internal_state: dict = {}

_coverage_handler: Optional[CoverageHandler] = None

_config: Optional[WakeConfig] = None
_verbosity: int = 0

_fuzz_mode: int = 0

_current_test_id: Optional[str] = None

_executing_sequence_num: int = 0
_executing_flow_num: int = 0

_shrank_path: Optional[Path] = None

_shrink_exact_flow: bool = False
_shrink_exact_exception: bool = False
_shrink_target_invariants_only: bool = False
_is_fuzzing: bool = False

def set_is_fuzzing(is_fuzzing: bool):
    global _is_fuzzing
    _is_fuzzing = is_fuzzing

def get_is_fuzzing() -> bool:
    return _is_fuzzing

def set_shrank_path(path: Path):
    global _shrank_path
    _shrank_path = path

def get_shrank_path() -> Optional[Path]:
    return _shrank_path

def set_current_test_id(test_id: str):
    global _current_test_id
    _current_test_id = test_id

def get_current_test_id() -> Optional[str]:
    return _current_test_id

def attach_debugger(
    e_type: Optional[Type[BaseException]],
    e: Optional[BaseException],
    tb: Optional[TracebackType],
    seed: Optional[bytes] = None,
):
    global _exception_handled

    if _exception_handled:
        return
    _exception_handled = True

    import traceback

    from wake.cli.console import console

    assert e_type is not None
    assert e is not None
    assert tb is not None

    rich_tb = rich.traceback.Traceback.from_exception(e_type, e, tb)
    console.print(rich_tb)

    frames = []

    for frame, lineno in traceback.walk_tb(tb):
        frames.append((frame, lineno))

    frames_up = 0
    for frame, lineno in reversed(frames):
        if is_relative_to(
            Path(frame.f_code.co_filename), Path.cwd()
        ) and not is_relative_to(
            Path(frame.f_code.co_filename), Path().cwd() / "pytypes"
        ):
            break
        frames_up += 1

    commands = []
    if frames_up > 0:
        commands.append("up %d" % frames_up)
    if seed is not None:
        commands.append(f"wake_random_seed = bytes.fromhex('{seed.hex()}')")

    p = _init_pdb(commands=commands)
    p.reset()
    p.interaction(None, tb)

def get_fuzz_mode() -> int:
    return _fuzz_mode

def set_fuzz_mode(fuzz_mode: int):
    global _fuzz_mode
    _fuzz_mode = fuzz_mode

def get_executing_sequence_num() -> int:
    return _executing_sequence_num

def set_executing_sequence_num(sequence_num: int):
    global _executing_sequence_num
    _executing_sequence_num = sequence_num

def get_executing_flow_num() -> int:
    return _executing_flow_num

def set_executing_flow_num(error_flow_num: int):
    global _executing_flow_num
    _executing_flow_num = error_flow_num


def get_exception_handler() -> Optional[
    Callable[
        [
            Optional[Type[BaseException]],
            Optional[BaseException],
            Optional[TracebackType],
        ],
        None,
    ]
]:
    return _exception_handler


def set_exception_handler(
    handler: Callable[
        [
            Optional[Type[BaseException]],
            Optional[BaseException],
            Optional[TracebackType],
        ],
        None,
    ]
):
    global _exception_handler
    _exception_handler = handler

def set_sequence_initial_internal_state(intenral_state: dict):
    global _initial_internal_state
    _initial_internal_state = intenral_state

def get_sequence_initial_internal_state() -> dict:
    return _initial_internal_state

def reset_exception_handled():
    global _exception_handled
    _exception_handled = False


def get_config() -> WakeConfig:
    global _config
    if _config is None:
        local_config_path = None
        ctx = rich_click.get_current_context(silent=True)
        if ctx is not None and isinstance(ctx.obj, dict):
            local_config_path = ctx.obj.get("local_config_path", None)

        _config = WakeConfig(local_config_path=local_config_path)
        _config.load_configs()
    return _config


def set_config(config: WakeConfig):
    global _config
    _config = config


def set_shrink_exact_flow(exact_flow: bool):
    global _shrink_exact_flow
    _shrink_exact_flow = exact_flow

def get_shrink_exact_flow() -> bool:
    return _shrink_exact_flow


def set_shrink_exact_exception(exact_exception: bool):
    global _shrink_exact_exception
    _shrink_exact_exception = exact_exception

def get_shrink_exact_exception() -> bool:
    return _shrink_exact_exception


def set_shrink_target_invariants_only(target_invariants_only: bool):
    global _shrink_target_invariants_only
    _shrink_target_invariants_only = target_invariants_only

def get_shrink_target_invariants_only() -> bool:
    return _shrink_target_invariants_only


def set_coverage_handler(coverage_handler: CoverageHandler):
    global _coverage_handler
    _coverage_handler = coverage_handler


def get_coverage_handler() -> Optional[CoverageHandler]:
    return _coverage_handler


def set_verbosity(verbosity: int):
    global _verbosity
    _verbosity = verbosity


def get_verbosity() -> int:
    return _verbosity


class ChainInterfaceManager:
    _chain_interfaces: DefaultDict[Tuple, List[Tuple[ChainInterfaceAbc, Optional[str]]]]
    _free_chain_interfaces: DefaultDict[Tuple, Set[ChainInterfaceAbc]]

    def __init__(self):
        self._chain_interfaces = defaultdict(list)
        self._free_chain_interfaces = defaultdict(set)

    def get_or_create(
        self,
        uri: Optional[str],
        *,
        accounts: Optional[int],
        chain_id: Optional[int],
        fork: Optional[str],
        hardfork: Optional[str],
    ) -> ChainInterfaceAbc:
        params = (uri, accounts, chain_id, fork, hardfork)

        if len(self._free_chain_interfaces[params]) == 0:
            if uri is None:
                logger.debug(
                    "Launching chain with accounts=%s, chain_id=%s, fork=%s, hardfork=%s",
                    accounts,
                    chain_id,
                    fork,
                    hardfork,
                )
                chain_interface = ChainInterfaceAbc.launch(
                    get_config(),
                    accounts=accounts,
                    chain_id=chain_id,
                    fork=fork,
                    hardfork=hardfork,
                )
            else:
                if (
                    accounts is not None
                    or chain_id is not None
                    or fork is not None
                    or hardfork is not None
                ):
                    raise ValueError(
                        "Cannot specify accounts, chain_id, fork or hardfork when connecting to a running chain"
                    )
                logger.debug("Connecting to chain at %s", uri)
                chain_interface = ChainInterfaceAbc.connect(get_config(), uri)
        else:
            logger.debug(
                "Reusing chain with accounts=%s, chain_id=%s, fork=%s, hardfork=%s",
                accounts,
                chain_id,
                fork,
                hardfork,
            )
            chain_interface = self._free_chain_interfaces[params].pop()

        try:
            snapshot = chain_interface.snapshot()
        except (JsonRpcError, HTTPError):
            snapshot = None

        self._chain_interfaces[params].append((chain_interface, snapshot))
        return chain_interface

    def free(self, chain_interface: ChainInterfaceAbc) -> None:
        snapshot_reverted = False
        params = None

        for chain_params, chain_interfaces in self._chain_interfaces.items():
            for i, (c, snapshot) in enumerate(chain_interfaces):
                if c == chain_interface:
                    params = chain_params
                    self._chain_interfaces[chain_params].pop(i)
                    try:
                        if snapshot is not None and chain_interface.revert(snapshot):
                            snapshot_reverted = True
                    except JsonRpcError:
                        pass
                    break

        if snapshot_reverted and params is not None:
            logger.debug(
                "Freeing chain with uri=%s, accounts=%s, chain_id=%s, fork=%s, hardfork=%s",
                *params,
            )
            self._free_chain_interfaces[params].add(chain_interface)
        else:
            if params is None:
                logger.debug("Unable to revert snapshot, closing chain")
            else:
                logger.debug(
                    "Unable to revert snapshot, closing chain with uri=%s, accounts=%s, chain_id=%s, fork=%s, hardfork=%s",
                    *params,
                )
            chain_interface.close()

    def close(self, chain_interface: ChainInterfaceAbc) -> None:
        chain_interface.close()

        for chain_params, chain_interfaces in self._chain_interfaces.items():
            for i, (c, _) in enumerate(chain_interfaces):
                if c == chain_interface:
                    chain_interfaces.pop(i)
                    logger.debug(
                        "Closed chain with uri=%s, accounts=%s, chain_id=%s, fork=%s, hardfork=%s",
                        *chain_params,
                    )
                    return
        logger.debug("Closed chain")

    def close_all(self) -> None:
        for _, chain_interfaces in self._chain_interfaces.items():
            for chain_interface, _ in chain_interfaces:
                chain_interface.close()
        for _, chain_interfaces in self._free_chain_interfaces.items():
            for chain_interface in chain_interfaces:
                chain_interface.close()
        self._chain_interfaces.clear()
        self._free_chain_interfaces.clear()


chain_interfaces_manager = ChainInterfaceManager()
