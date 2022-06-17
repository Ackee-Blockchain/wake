import asyncio
import collections
import json
from typing import Optional, Union

from .protocol_structures import (
    NotificationMessage,
    RequestMessage,
    ResponseError,
    ResponseMessage,
)

# TODO Buffering messages


ENCODING = "utf-8"


class RpcProtocolError(Exception):
    pass


class RpcProtocol:
    """
    Json rpc comunication
    """

    __port: int
    __reader: asyncio.StreamReader
    __writer: asyncio.StreamWriter

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.__reader = reader
        self.__writer = writer

    async def _read_message(self) -> dict:
        line = (await self.__reader.readline()).decode(ENCODING)
        # It is, read header then
        if line.startswith("Content-Length: ") and line.endswith("\r\n"):
            content_length = int(line.split(":")[-1])
        else:
            raise RpcProtocolError(f"Invalid HTTP header: {line}")
        # Skip unnecessary header part
        while line != b"\r\n":
            line = await self.__reader.readline()

        return json.loads(await self.__reader.read(content_length))

    async def receive(self) -> Union[RequestMessage, NotificationMessage]:
        raw_message = await self._read_message()

        if "id" in raw_message:
            return RequestMessage.parse_obj(raw_message)
        return NotificationMessage.parse_obj(raw_message)

    async def _send(self, message: str) -> None:
        content_length = len(message)
        response = f"Content-Length: {content_length}\r\nContent-Type: application/vscode-jsonrpc; charset={ENCODING}\r\n\r\n{message}"
        self.__writer.write(response.encode(ENCODING))
        await self.__writer.drain()

    async def send(
        self,
        message: Union[
            ResponseMessage, RequestMessage, ResponseError, NotificationMessage
        ],
    ) -> None:
        await self._send(message.json(exclude_none=True, by_alias=True))
