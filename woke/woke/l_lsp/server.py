import logging
from context import LSPContext
from protocol_structures import NotificationMessage, RequestMessage, ResponseMessage, ResponseError, ErrorCodes
from RPC_protocol import RPCProtocol
from methods import RequestMethodEnum
#from methods_impl import method_mapping
#from notifications_impl import notification_mapping
from typing import Union



class Server:
    def __init__(self, protocol: RPCProtocol, client_capabilities: list, threads: int = 1):
        self.protocol = protocol
        self.threads = threads 
        self.client_capabilities = client_capabilities
        self.running = True
        self.workspace = None
        self.init_request_received = False
        self.context = LSPContext()
        
    def run_server(self):
        '''
        Start the server
        '''
        while self.running:
            try:
                # Read it
                message = self.protocol.recieve_message()
                # Handle it
                self.handle_message(message)
            # Proper error handling
            except EOFError:
                break
            except Exception as e:
                logging.error("Error: %s", e)

    def stop_server(self):
        logging.shutdown()
        self.running = False

    def handle_message(self, request: Union[RequestMessage, NotificationMessage]):
        # Double initialization
        if self.init_request_received and request.method == RequestMethodEnum.INITIALIZE:
            logging.error("Double init")
            response_message = self._serve_error(request, ErrorCodes.InvalidRequest, "Server already initialized")
            self.protocol.send_rpc_response(response_message)
            return
        # Init before request needed    
        if request.id and not self.init_request_received:
            logging.error("Request before init")
            response_message = self._serve_error(request, ErrorCodes.ServerNotInitialized, "Server has not been initialized")                                
            self.protocol.send_rpc_response(response_message)
            return           
        # Handle here
        try:
            if request.id:
                # If id --> request handling and send
                logging.info(f"Handling\nRequest id: {request.id}\nRequest method: {request.method}")
                response =  self._serve_response(request)
                self.protocol.send_rpc_response(response)
            else:
                # Notification is without response
                self._serve_notification(request)
        except Exception as e:
            logging.error(e)
            error = self._serve_error(request, ErrorCodes.RequestCancelled, "Error in handling message")
            self.protocol.send_rpc_response(error)


    def _serve_response(self, request: RequestMessage) ->  ResponseMessage:
        response = method_mapping[request.method](self.context, request.params)
        if self.context.initialized:
            self.init_request_received = True
        if self.context.shutdown_received:
            self.stop_server()
        response_message = ResponseMessage(
                                json_rpc = "2.0",
                                id = request.id,
                                result= response)

        return response_message


    def _serve_error(self, request: RequestMessage, error_code: ErrorCodes, msg: str) -> ResponseMessage:
        response_error = ResponseError(
                                code = error_code,
                                message = msg)
        response_message = ResponseMessage(
                                json_rpc = "2.0",
                                id = request.id,
                                error = response_error)
        return response_message

    def _serve_notification(self, request: RequestMessage) -> None:
        # Methods do their job
        notification_mapping[request.method](self.context, request.params)
        return


    def get_client_capabilities(self, ClientCapabilities):
        return self.client_capabilities



