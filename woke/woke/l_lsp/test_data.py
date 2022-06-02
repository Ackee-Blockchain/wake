import json
from woke.l_lsp.basic_structures import *

"""
Class for providing test messages
One request, two notifications
For each some broken variants


Functions for creating correct header
5 functions for creating broken heades
They can be applied to any message

"""


class TestClass:
    """
    Message 'inialize' must be received as the first on
    """

    init_params = (
        InitializeParams(
            process_id=1,
            client_info=None,
            locale=None,
            root_path=None,
            root_uri=DocumentUri("foo://uri/here/folder/"),
            initialization_options=None,
            capabilities=ClientCapabilities(
                workspace=None,
                text_document=None,
                notebook_document=None,
                window=None,
                general=None,
                experimental="test_capability",
            ),
            trace=None,
            workspace_folders=None,
        )
    ).dict()
    """
    Notification for passing text of opened doc (notification do not have ID)
    """
    did_open_params = (
        DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri=DocumentUri("foo://uri/here/folder/contract.sol"),
                language_id="sol",
                version=1,
                text="text of the document source code",
            )
        )
    ).dict()
    """
    Notification for changig text of opened doc (notification do not have ID)
    """
    did_change_params = (
        DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                version=1, uri=DocumentUri("foo://uri/here/folder/contract.sol")
            ),
            content_changes=[
                TextDocumentContentChangeEvent(
                    range=Range(
                        start=Position(line=1, character=10),
                        end=Position(line=1, character=25),
                    ),
                    range_length=None,
                    text="changed text of length 25",
                )
            ],
        )
    ).dict()
    # init messages
    init_msg = f'{{"jsonrpc": "2.0","id": 1,"method": "initialize","params": {json.dumps(init_params)}}}'
    init_msg_no_id_data = f'{{"jsonrpc": "2.0","id":,"method": "initialize","params": {json.dumps(init_params)}}}'
    init_msg_no_id = f'{{"jsonrpc": "2.0","method": "initialize","params": {json.dumps(init_params)}}}'
    init_msg_typos_method_data = f'{{"jsonrpc": "2.0","id": 1,"method": "initlize","params": {json.dumps(init_params)}}}'
    init_msg_typos_method = f'{{"jsonrpc": "2.0","id": 1,"mhod": "initlize","params": {json.dumps(init_params)}}}'
    init_msg_no_params = (
        f'{{"jsonrpc": "2.0","id": 1,"method": "initialize","params":}}'
    )
    # did open
    did_open_msg = f'{{"jsonrpc": "2.0","method": "textDocument/didOpen","params": {json.dumps(did_open_params)}}}'
    did_open_msg_id_data = f'{{"jsonrpc": "2.0","id": 2,"method": "textDocument/didOpen","params": {json.dumps(did_open_params)}}}'
    did_open_msg_typos_method_data = f'{{"jsonrpc": "2.0","method": "textcument/didOpen","params": {json.dumps(did_open_params)}}}'
    did_open_msg_typos_method = f'{{"jsonrpc": "2.0","ethod": "textDocument/didOpen","params": {json.dumps(did_open_params)}}}'
    did_open_msg_no_params = f'{{"jsonrpc": "2.0","method": "textDocument/didOpen"}}'
    # did change
    did_change_msg = f'{{"jsonrpc": "2.0","method": "textDocument/didChange","params": {json.dumps(did_change_params)}}}'
    did_change_msg_id_data = f'{{"jsonrpc": "2.0","id": 2,"method": "textDocument/didChange","params": {json.dumps(did_change_params)}}}'
    did_change_msg_typos_method_data = f'{{"jsonrpc": "2.0","method": "textcument/didCange","params": {json.dumps(did_change_params)}}}'
    did_change_msg_typos_method = f'{{"jsonrpc": "2.0","ethod": "textDocument/didChange","params": {json.dumps(did_change_params)}}}'
    did_change_msg_no_params = (
        f'{{"jsonrpc": "2.0","method": "textDocument/didChange"}}'
    )
    # exit
    exit_msg = '{"jsonrpc": "2.0","method": "exit","params": "Null"}'
    exit_msg_with_id = '{"jsonrpc": "2.0","id": 1,"method": "exit"}'
    exit_msg_typos_method_data = '{"jsonrpc": "2.0","method": "exlt","params": "Null"}'
    # No method
    no_method_mg = '{"jsonrpc": "2.0","id": 1,"params": "url"}'


# create right message
def make_message(msg: str) -> str:
    return f"Content-Length: {len(msg)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n{msg}"


# Create broken messages
def make_wrong_message_1(msg: str) -> str:
    return f"Contenngth: {len(msg)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n{msg}"


def make_wrong_message_2(msg: str) -> str:
    return f"Content-Length: \r\nContent-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n{msg}"


def make_wrong_message_3(msg: str) -> str:
    return f"application/vscode-jsonrpc; charset=utf8\r\n\r\n{msg}"


def make_wrong_message_4(msg: str) -> str:
    return f"r\n\r\n{msg}"


def make_wrong_message_5(msg: str) -> str:
    return f"{msg}"
