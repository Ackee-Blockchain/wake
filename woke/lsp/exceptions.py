from typing import Any


class LspError(Exception):
    __code: int
    __message: str
    __data: Any

    def __init__(self, code: int, message: str, data: Any = None):
        self.__code = code
        self.__message = message
        self.__data = data

    @property
    def code(self) -> int:
        return self.__code

    @property
    def message(self) -> str:
        return self.__message

    @property
    def data(self) -> Any:
        return self.__data
