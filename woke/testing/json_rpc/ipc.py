import json
import platform

from woke.testing.json_rpc.abc import ProtocolAbc

if platform.system() == "Windows":
    import win32file  # pyright: reportMissingImports=false

    class IpcProtocol(ProtocolAbc):  # pyright: reportGeneralTypeIssues=false
        _uri: str

        def __init__(self, uri: str):
            self._uri = uri

        def __enter__(self):
            self._handle = win32file.CreateFile(
                self._uri,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._handle.close()

        def send_recv(self, data: str):
            win32file.WriteFile(self._handle, data.encode("utf-8"))
            received = b""

            while True:
                res, data = win32file.ReadFile(self._handle, 4096)
                received += data  # pyright: reportGeneralTypeIssues=false
                if not received.rstrip().endswith((b"}", b"]")):
                    continue
                try:
                    return json.loads(received.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

else:
    import socket

    class IpcProtocol(ProtocolAbc):
        _uri: str
        _socket: socket.socket

        def __init__(self, uri: str):
            self._uri = uri

        def __enter__(self):
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.connect(self._uri)

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._socket.close()

        def send_recv(self, data: str):
            self._socket.setblocking(True)
            self._socket.sendall(data.encode("utf-8"))
            self._socket.setblocking(False)
            received = b""

            while True:
                try:
                    received += self._socket.recv(4096)
                except BlockingIOError:
                    if not received.rstrip().endswith((b"}", b"]")):
                        continue
                    try:
                        return json.loads(received.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
