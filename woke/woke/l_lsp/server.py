import asyncio
import logging

from .context import LspContext
from .exceptions import LspError
from .protocol_structures import (
    NotificationMessage,
    RequestMessage,
    ResponseMessage,
    ResponseError,
    ErrorCodes,
)
from .rpc_protocol import RpcProtocol
from .methods import RequestMethodEnum
from .methods_impl import handle_client_to_server_method
from .notifications_impl import handle_client_to_server_notification
from ..a_config import WokeConfig

logger = logging.getLogger(__name__)


class LspServer:
    __protocol: RpcProtocol
    __run: bool

    def __init__(
        self,
        config: WokeConfig,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self.__protocol = RpcProtocol(reader, writer)
        self.__run = True
        self.context = LspContext(config)

    async def run(self) -> None:
        while self.__run:
            message = await self.__protocol.receive()
            if isinstance(message, RequestMessage):
                await self._handle_message(message)
            else:
                self._handle_notification(message)

    async def _handle_message(self, request: RequestMessage) -> None:
        logger.info(f"Message received: {request}")

        # Init before request needed
        if (
            request.method != RequestMethodEnum.INITIALIZE
            and not self.context.initialized
        ):
            response = self._serve_error(
                request,
                ErrorCodes.ServerNotInitialized,
                "Server has not been initialized",
            )
            await self.__protocol.send(response)
            return

        # Handling request
        try:
            response = self._serve_response(request)
        except LspError as e:
            response = self._serve_error(request, e.code, e.message)
        await self.__protocol.send(response)

    def _handle_notification(self, notification: NotificationMessage):
        logger.info(f"Notification received: {notification}")

        # Handling notification
        # No error response send after failed notification
        # Drop if not initialized
        if self.context.initialized or notification.method == "exit":
            self._serve_notification(notification)

    def _serve_response(self, request: RequestMessage) -> ResponseMessage:
        response = handle_client_to_server_method(
            self.context, request.method, request.params
        )
        if self.context.initialized:
            self.init_request_received = True
        if self.context.shutdown_received:
            self.__run = False
        response_message = ResponseMessage(
            json_rpc="2.0", id=request.id, result=response, error=None
        )
        logger.info(f"Serving response: {response_message}")
        return response_message

    @staticmethod
    def _serve_error(
        request: RequestMessage, error_code: int, msg: str
    ) -> ResponseMessage:
        response_error = ResponseError(code=error_code, message=msg, data=None)
        response_message = ResponseMessage(
            json_rpc="2.0", id=request.id, error=response_error, result=None
        )
        logger.warning(f"Serving error response: {response_message}")
        return response_message

    def _serve_notification(self, request: NotificationMessage) -> None:
        # Server handles notification
        # Nothing to return
        handle_client_to_server_notification(
            self.context, request.method, request.params
        )
