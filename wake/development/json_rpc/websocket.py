import json

from websocket import WebSocket, create_connection

from .abc import ProtocolAbc


class WebsocketProtocol(ProtocolAbc):
    _uri: str
    _timeout: float
    _ws: WebSocket

    def __init__(self, uri: str, timeout: float):
        self._uri = uri
        self._timeout = timeout

    def __enter__(self):
        self._ws = create_connection(
            self._uri, skip_utf8_validation=True, timeout=self._timeout
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ws.close()

    def send_recv(self, data: str):
        self._ws.send(data)  # pyright: ignore reportGeneralTypeIssues
        return json.loads(self._ws.recv())
