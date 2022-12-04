from abc import ABC, abstractmethod


class ProtocolAbc(ABC):
    @abstractmethod
    def __enter__(self):
        ...

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        ...

    @abstractmethod
    def send_recv(self, data: str) -> str:
        ...
