import json
import logging
import platform
import signal
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from wake.config import WakeConfig
from wake.core import get_logger

from .abc import ProtocolAbc
from .http import HttpProtocol
from .ipc import IpcProtocol
from .websocket import WebsocketProtocol

logger = get_logger(__name__)


@contextmanager
def delayed_keyboard_interrupt():
    signal_received = []

    def signal_handler(signum, frame):
        signal_received.append((signum, frame))

    original_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal_handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, original_handler)
        if signal_received:
            original_handler(*signal_received[0])


class JsonRpcError(Exception):
    def __init__(self, data: Dict):
        self.data = data


class JsonRpcCommunicator:
    _protocol: ProtocolAbc
    _request_id: int
    _connected: bool
    uri: str

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
        self.uri = uri

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
        with delayed_keyboard_interrupt():
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
