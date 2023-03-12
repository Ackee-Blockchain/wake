import json
from urllib.request import Request, urlopen

from woke.utils import get_package_version

from .abc import ProtocolAbc


class HttpProtocol(ProtocolAbc):
    _uri: str
    _timeout: float

    def __init__(self, uri: str, timeout: float):
        self._uri = uri
        self._timeout = timeout

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def send_recv(self, data: str):
        req = Request(
            self._uri,
            data.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"woke/{get_package_version('woke')}",
            },
        )

        with urlopen(req, timeout=self._timeout) as response:
            return json.loads(response.read().decode("utf-8"))
