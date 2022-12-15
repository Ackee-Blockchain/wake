import json

from websocket import WebSocket, create_connection

from .abc import ProtocolAbc


class WebsocketProtocol(ProtocolAbc):
    _uri: str
    _ws: WebSocket

    def __init__(self, uri: str):
        self._uri = uri

    def __enter__(self):
        self._ws = create_connection(self._uri, skip_utf8_validation=True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ws.close()

    def send_recv(self, data: str):
        self._ws.send(data)
        return json.loads(self._ws.recv())
