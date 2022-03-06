import json
import collections
from pydantic import BaseModel
from protocol_structures import (
                                RequestMessage,
                                ResponseMessage,
                                ResponseError,
                                NotificationMessage,
                                )
# TODO Buffering messages

class RPCProtocolError(Exception):
    pass

class TCPReader():
    '''
    Also a writer
    '''
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer

    def read(self, input):
        return self.reader.read(input).decode("utf-8")

    def write(self, output):
        self.writer.write(output.encode("utf-8"))
        self.writer.flush()

    def read_line(self, input):
        return self.reader.readline(input).decode("utf-8")


class RPCProtocol():
    '''
    Json rpc comunication
    '''
    def __init__(self, reader):
        self.reader = reader
        # For buffering messages
        self.msg_buffer = collections.deque()
    

    def _read_header(self):
        '''
        Reads message header (Content length only)
        '''
        # Is there anything to read ?
        line = self.reader.read_line()
        if not line:
            raise RPCProtocolError(f"No message to read")
                            
        # It is, read header then
        if line.startswith("Content-Length: ") and line.endswith("\r\n"):
            content_length = line.split(':').strip()
        else:
            raise RPCProtocolError(f"Invalid HTTP header")
        # Skip unnecessary header part
        while line != "\r\n":
            line = self.reader.read_line()
        # Return content length
        return content_length


    def _read_content(self) -> RequestMessage:
        '''
        Reads message content and creates object
        '''
        body = self.reader.read()
        content = json.loads(body)
        request_object = RequestMessage(
                            json_rpc=content['json_rpc'],
                            id=content['id'],
                            method=content['method'],
                            params=content['params'])
        return request_object

    def recieve_message(self) -> RequestMessage:
        '''
        Get content length parameters from http header
        (Is useless variable at this point, but function
            make steps over the header and stop before content)
        Get RPC message body content
        '''
        #if self.msg_buffer:
        #    return self.msg_buffer.popleft()
        _ = self._read_header()
        request_object = self._read_content()
        #self.buffer.append(request_content)
        return request_object


    def send_rpc_response(self, response: ResponseMessage):
        '''
        Response object to be send
        '''
        return self._send(response.__dict__)


    def send_rpc_request(self, request: RequestMessage):
        '''
        Request object to be send
        '''
        return self._send(request.__dict__)


    def send_rpc_error(self, error: ResponseError):
        '''
        Error object to be send
        '''
        return self._send(error.__dict__)


    def send_rpc_notification(self, notification: NotificationMessage):
        '''
        Notification object to be send
        '''
        return self._send(notification.__dict__)


    def _send(self, message: dict):
        '''
        Formats object to message and sends it 
        '''
        message = json.dumps(message, separators=(",", ":"))
        content_length = len(message)
        response = f"Content-Length: {content_length}\r\nContent-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n{message}"
        self.stdout.write(response)
        # Flush if something collected in buffer
        self.stdout.flush()

