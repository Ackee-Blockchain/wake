from woke.testing.json_rpc.abc import ProtocolAbc


class IpcProtocol(ProtocolAbc):
    def __init__(self, uri: str):
        raise NotImplementedError("IPC communication is not supported yet")

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def send_recv(self, data: str) -> str:
        raise NotImplementedError("IPC communication is not supported yet")
