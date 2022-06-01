import logging
from typing import List, Iterable

from .context import LspContext
from .exceptions import LspError
from .protocol_structures import (
    NotificationMessage,
    RequestMessage,
    ResponseMessage,
    ResponseError,
    ErrorCodes,
)
from .RPC_protocol import RPCProtocol
from .methods import RequestMethodEnum
from .methods_impl import handle_client_to_server_method
from .notifications_impl import handle_client_to_server_notification
from ..a_config import WokeConfig

logger = logging.getLogger(__name__)


class Server:
    def __init__(
        self,
        config: WokeConfig,
        protocol: RPCProtocol,
        threads: int = 1,
    ):
        self.protocol = protocol
        self.threads = threads
        self.running = True
        self.context = LspContext(config)

    def run_server(self):
        """
        Start the server
        """
        while self.running:
            # Read the message
            message = self.protocol.receive_message()
            if isinstance(message, RequestMessage):
                self.handle_message(message)
            else:
                self.handle_notification(message)

    def stop_server(self):
        logging.shutdown()
        self.running = False

    def handle_message(self, request: RequestMessage):
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
            self.protocol.send_rpc_response(response)
            return

        # Handling request
        try:
            response = self._serve_response(request)
        except LspError as e:
            response = self._serve_error(request, e.code, e.message)
        self.protocol.send_rpc_response(response)

    def handle_notification(self, notification: NotificationMessage):
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
            self.stop_server()
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
