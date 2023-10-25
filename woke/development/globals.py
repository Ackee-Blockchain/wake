from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Callable, DefaultDict, List, Optional, Set, Tuple
from urllib.error import HTTPError

from ipdb.__main__ import _init_pdb

from woke.config import WokeConfig
from woke.core import get_logger
from woke.development.chain_interfaces import ChainInterfaceAbc
from woke.development.json_rpc import JsonRpcError
from woke.utils.file_utils import is_relative_to

if TYPE_CHECKING:
    from woke.testing.coverage import CoverageHandler


logger = get_logger(__name__)


# must be declared before functions that use it because of a bug in Python (https://bugs.python.org/issue34939)
_exception_handler: Optional[Callable[[Exception], None]] = None
_exception_handled = False

_coverage_handler: Optional[CoverageHandler] = None

_config: Optional[WokeConfig] = None


def attach_debugger(e: Exception):
    global _exception_handled

    if _exception_handled:
        return
    _exception_handled = True

    import sys
    import traceback

    from woke.cli.console import console

    tb: Optional[TracebackType] = sys.exc_info()[2]
    assert tb is not None
    console.print_exception()

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

    p = _init_pdb(
        commands=["up %d" % frames_up] if frames_up > 0 else [],
    )
    p.reset()
    p.interaction(None, tb)


def get_exception_handler() -> Optional[Callable[[Exception], None]]:
    return _exception_handler


def set_exception_handler(handler: Callable[[Exception], None]):
    global _exception_handler
    _exception_handler = handler


def reset_exception_handled():
    global _exception_handled
    _exception_handled = False


def get_config() -> WokeConfig:
    global _config
    if _config is None:
        _config = WokeConfig()
        _config.load_configs()
    return _config


def set_config(config: WokeConfig):
    global _config
    _config = config


def set_coverage_handler(coverage_handler: CoverageHandler):
    global _coverage_handler
    _coverage_handler = coverage_handler


def get_coverage_handler() -> Optional[CoverageHandler]:
    return _coverage_handler


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
