import logging

from .context import LSPContext
from .protocol_structures import (
    NotificationMessage,
    RequestMessage,
    ResponseMessage,
    ResponseError,
    ErrorCodes,
)
from .RPC_protocol import RPCProtocol
from .methods import RequestMethodEnum
from .methods_impl import method_mapping
from .notifications_impl import notification_mapping


class Server:
    def __init__(self, protocol: RPCProtocol, threads: int = 1):
        self.protocol = protocol
        self.threads = threads
        self.client_capabilities = {}
        self.running = True
        self.init_request_received = False
        self.context = LSPContext()

    def run_server(self):
        """
        Start the server
        """
        while self.running:
            try:
                # Read the message
                message = self.protocol.recieve_message()
                if type(message) == RequestMessage:
                    # print('* REQUEST *')
                    self.handle_message(message)
                else:
                    # print('* NOTIFICATION  *')
                    self.handle_notification(message)
            except EOFError:
                break
            except Exception as e:
                logging.error("Error: %s", e)

    def stop_server(self):
        logging.shutdown()
        self.running = False

    def handle_message(self, request: RequestMessage):
        # Double initialization
        if (
            self.init_request_received
            and request.method == RequestMethodEnum.INITIALIZE
        ):
            # logging.error("Double init")
            response_message = self._serve_error(
                request, ErrorCodes.InvalidRequest.value, "Server already initialized"
            )
            self.protocol.send_rpc_response(response_message)
            return
        # Init before request needed
        if (
            request.method != RequestMethodEnum.INITIALIZE
            and not self.init_request_received
        ):
            # logging.error("Request before init")
            response_message = self._serve_error(
                request,
                ErrorCodes.ServerNotInitialized.value,
                "Server has not been initialized",
            )
            self.protocol.send_rpc_response(response_message)
            return
        # Handling request
        try:
            # logging.info(f"Handling\nRequest id: {request.id}\nRequest method: {request.method}")
            response = self._serve_response(request)
            self.protocol.send_rpc_response(response)
        except Exception as e:
            # logging.error(e)
            error = self._serve_error(
                request, ErrorCodes.RequestCancelled, "Error in handling message"
            )
            self.protocol.send_rpc_response(error)

    def handle_notification(self, notification: NotificationMessage):
        # print('handling')
        # Handling notification
        # No error response send after failed notification
        try:
            self._serve_notification(notification)
        except Exception as e:
            logging.error(e)

    def _serve_response(self, request: RequestMessage) -> ResponseMessage:
        # print('serving')
        response = method_mapping[request.method](self.context, request.params)
        if self.context.initialized:
            self.init_request_received = True
            self.client_capabilities = self.context.client_capabilities
        if self.context.shutdown_received:
            self.stop_server()
        response_message = ResponseMessage(
            json_rpc="2.0", id=request.id, result=response
        )

        return response_message

    def _serve_error(
        self, request: RequestMessage, error_code: int, msg: str
    ) -> ResponseMessage:
        response_error = ResponseError(code=error_code, message=msg)
        response_message = ResponseMessage(
            json_rpc="2.0", id=request.id, error=response_error
        )
        return response_message

    def _serve_notification(self, request: RequestMessage) -> None:
        # Server handles notification
        # Nothing to return
        notification_mapping[request.method](self.context, request.params)
        return

    def get_client_capabilities(self, ClientCapabilities):
        return self.client_capabilities
