import json
from urllib.request import Request, urlopen

from woke.testing.json_rpc.abc import ProtocolAbc


class HttpProtocol(ProtocolAbc):
    _uri: str

    def __init__(self, uri: str):
        self._uri = uri

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def send_recv(self, data: str):
        req = Request(
            self._uri,
            data.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
