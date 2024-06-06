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
    Json rpc communication
    """

    __port: int
    __reader: asyncio.StreamReader
    __writer: asyncio.StreamWriter
    __lock: asyncio.Lock

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.__reader = reader
        self.__writer = writer
        self.__lock = asyncio.Lock()

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

        return json.loads(await self.__reader.readexactly(content_length))

    async def receive(
        self,
    ) -> Union[RequestMessage, NotificationMessage, ResponseMessage]:
        raw_message = await self._read_message()

        if "id" in raw_message:
            if "method" in raw_message:
                return RequestMessage.model_validate(raw_message)
            else:
                return ResponseMessage.model_validate(raw_message)
        return NotificationMessage.model_validate(raw_message)

    async def _send(self, message: str) -> None:
        encoded_message = message.encode(ENCODING)
        content_length = len(encoded_message)
        response = (
            f"Content-Length: {content_length}\r\nContent-Type: application/vscode-jsonrpc; charset={ENCODING}\r\n\r\n".encode(
                ENCODING
            )
            + encoded_message
        )
        async with self.__lock:
            self.__writer.write(response)
            await self.__writer.drain()

    async def send(
        self,
        message: Union[
            ResponseMessage, RequestMessage, ResponseError, NotificationMessage
        ],
    ) -> None:
        await self._send(message.model_dump_json(exclude_unset=True, by_alias=True))
