"""
PROTOCOL/SERVER Tesing client
Manual
- run server from separate procce $python __main__.py
- connect client
- use test_data messages and functions from test_data file to send requests and notifications

import test_client as ts
client = ts.Client()
client.connect()
init = ts.make_message(ts.TestClass.init_msg)
did_change = ts.make_message(ts.TestClass.did_change_msg)
did_open = ts.make_message(ts.TestClass.did_open_msg)
ex = ts.make_message(ts.TestClass.exit_msg)
client.send_request(msg)

Automat
- use test_run() function with given set of messages

* Notifications sdould be dropped if server was not initialized (except exit)
* Notifications handled after successful init 
    (Print for did_change and did_open notificaions to check whether the right model was returned or not)
"""
import json
from base64 import decode
import socket

from .test_data import *
from woke.l_lsp.basic_structures import *

HOST = "127.0.0.1"  # The server's hostname or IP address
PORT = 65432  # The port used by the server


class Client:
    def __init__(self, sock=None):
        if sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.sock = sock

    def _create_packet(self, data):
        return f"Content-Length: {len(data)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n{data}"

    def connect(self):
        self.sock.connect((HOST, PORT))

    def send_request(self, msg):
        sent = self.sock.send(str.encode(msg))
        chunk = self.sock.recv(2048)
        if sent == 0:
            raise RuntimeError("socket connection broken")
        return chunk.decode()

    def send_notification(self, msg):
        sent = self.sock.send(str.encode(msg))
        if sent == 0:
            raise RuntimeError("socket connection broken")


"""
def test_run():
    client = Client()
    client.connect()
    response = client.send_request(make_message(TestClass.init_msg))
    #response_object = InitializeResult.parse_obj(t_dict(response))
    print(response)
        
#test_run()
"""
