import json
import logging
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

from wake.config import WakeConfig
from wake.core import get_logger

from .abc import ProtocolAbc
from .http import HttpProtocol
from .ipc import IpcProtocol
from .websocket import WebsocketProtocol
import signal
from contextlib import contextmanager

logger = get_logger(__name__)


_no_interrupt = False
_keyboard_interrupt_in_no_interrupt = False

def signal_handler(signum, frame):
    if _no_interrupt:
        global _keyboard_interrupt_in_no_interrupt
        _keyboard_interrupt_in_no_interrupt = True
    else:
        raise KeyboardInterrupt


@contextmanager
def set_no_interrupt():
    global _no_interrupt
    global _keyboard_interrupt_in_no_interrupt
    assert _keyboard_interrupt_in_no_interrupt == False # for checking'
    _no_interrupt = True

    yield

    _no_interrupt = False
    if _keyboard_interrupt_in_no_interrupt:
        _keyboard_interrupt_in_no_interrupt = False
        raise KeyboardInterrupt

signal.signal(signal.SIGINT, signal_handler)

class JsonRpcError(Exception):
    def __init__(self, data: Dict):
        self.data = data


class JsonRpcCommunicator:
    _protocol: ProtocolAbc
    _request_id: int
    _connected: bool

    def __init__(self, config: WakeConfig, uri: str):
        if uri.startswith(("http://", "https://")):
            self._protocol = HttpProtocol(uri, config.general.json_rpc_timeout)
        elif uri.startswith(("ws://", "wss://")):
            self._protocol = WebsocketProtocol(uri, config.general.json_rpc_timeout)
        elif Path(uri).is_socket() or platform.system() == "Windows":
            self._protocol = IpcProtocol(uri, config.general.json_rpc_timeout)
        else:
            raise ValueError(f"Invalid URI: {uri}")

        self._request_id = 0
        self._connected = False

    def __enter__(self):
        self._protocol.__enter__()
        self._connected = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._protocol.__exit__(exc_type, exc_value, traceback)
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def send_request(self, method_name: str, params: Optional[List] = None) -> Any:
        with set_no_interrupt():
            post_data = {
                "jsonrpc": "2.0",
                "method": method_name,
                "params": params if params is not None else [],
                "id": self._request_id,
            }
            logger.info(f"Sending request:\n{post_data}")
            self._request_id += 1

            response = self._protocol.send_recv(json.dumps(post_data))
            logger.info(f"Received response:\n{json.dumps(response)}")
            if "error" in response:
                raise JsonRpcError(response["error"])
            return response["result"]
