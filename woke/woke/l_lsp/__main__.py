import socketserver
import logging
import argparse

from .server import Server
from .RPC_protocol import TCPReader, RPCProtocol


class TCPHandler(socketserver.StreamRequestHandler):
    """
    The request handler class using our server with RPC protocol  for message handling

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    (https://docs.python.org/3/library/socketserver.html#socketserver.StreamRequestHandler)
    """

    def handle(self):
        rpc_protocol = RPCProtocol(TCPReader(self.rfile, self.wfile))
        s = Server(protocol=rpc_protocol, client_capabilities=["test", "completion"])
        s.run_server()


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


def main():
    parser = argparse.ArgumentParser(description="Server arguments")
    parser.add_argument("--port", default=65432, help="TCP port", type=int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    # static ip adress | argument port
    host = "127.0.0.1"
    logging.info(f"Woke server listening on address: {host}/{args.port}")
    ThreadingTCPServer.allow_reuse_address = True
    ThreadingTCPServer.daemon_threads = True
    # TCPHandler.config = config
    s = ThreadingTCPServer((host, args.port), TCPHandler)
    try:
        s.serve_forever()
    finally:
        s.shutdown()


if __name__ == "__main__":
    main()
