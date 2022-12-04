import platform

from woke.testing.json_rpc.abc import ProtocolAbc

if platform.system() == "Windows":
    raise NotImplementedError("IPC communication is not supported yet on Windows")


else:
    import socket

    class IpcProtocol(ProtocolAbc):
        _uri: str
        _socket: socket.socket

        def __init__(self, uri: str):
            self._uri = uri

        def __enter__(self):
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.setblocking(False)
            self._socket.connect(self._uri)

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._socket.close()

        def send_recv(self, data: str) -> str:
            self._socket.sendall(data.encode("utf-8"))
            received = b""

            while True:
                try:
                    received += self._socket.recv(4096)
                except BlockingIOError:
                    if not received.endswith((b"}", b"}\n", b"]", b"]\n")):
                        continue
                    break

            return received.decode("utf-8")
