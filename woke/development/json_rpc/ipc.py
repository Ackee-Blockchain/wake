import json
import platform
import time

from .abc import ProtocolAbc

if platform.system() == "Windows":
    import win32file  # pyright: ignore reportMissingModuleSource

    class IpcProtocol(ProtocolAbc):  # pyright: ignore reportGeneralTypeIssues
        _uri: str
        _timeout: float

        def __init__(self, uri: str, timeout: float):
            self._uri = uri
            self._timeout = timeout

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
            win32file.WriteFile(
                self._handle,  # pyright: ignore reportGeneralTypeIssues
                data.encode("utf-8"),
            )
            received = bytearray()
            start = time.perf_counter()

            while time.perf_counter() - start < self._timeout:
                res, data = win32file.ReadFile(
                    self._handle, 4096  # pyright: ignore reportGeneralTypeIssues
                )
                received += data  # pyright: ignore reportGeneralTypeIssues
                if not received.rstrip().endswith((b"}", b"]")):
                    continue
                try:
                    return json.loads(received.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
            raise TimeoutError("IPC communication timeout")

else:
    import socket

    class IpcProtocol(ProtocolAbc):
        _uri: str
        _timeout: float
        _socket: socket.socket

        def __init__(self, uri: str, timeout: float):
            self._uri = uri
            self._timeout = timeout

        def __enter__(self):
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.connect(self._uri)
            self._socket.settimeout(0.0005)

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._socket.close()

        def send_recv(self, data: str):
            self._socket.sendall(data.encode("utf-8"))
            received = bytearray()
            start = time.perf_counter()

            while time.perf_counter() - start < self._timeout:
                try:
                    received += self._socket.recv(4096)
                except socket.timeout:
                    if not received.rstrip().endswith((b"}", b"]")):
                        continue
                    try:
                        return json.loads(received.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
            raise TimeoutError("IPC communication timeout")
