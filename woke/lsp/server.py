import asyncio
import logging
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, NoReturn, Optional, Tuple, Type, Union

from pydantic.error_wrappers import ValidationError

from ..config import WokeConfig
from .common_structures import (
    ConfigurationItem,
    ConfigurationParams,
    DidChangeConfigurationParams,
    DocumentFilter,
    InitializedParams,
    InitializeError,
    InitializeParams,
    LogMessageParams,
    LogTraceParams,
    MessageType,
    ProgressParams,
    SetTraceParams,
)
from .context import LspContext
from .document_sync import (
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    TextDocumentSyncKind,
    TextDocumentSyncOptions,
    WillSaveTextDocumentParams,
)
from .exceptions import LspError
from .features.diagnostic import diagnostics_loop
from .features.document_link import (
    DocumentLinkOptions,
    DocumentLinkParams,
    document_link,
)
from .features.document_symbol import DocumentSymbolParams, document_symbol
from .features.references import ReferenceParams, references
from .features.type_hierarchy import (
    TypeHierarchyPrepareParams,
    TypeHierarchySubtypesParams,
    TypeHierarchySupertypesParams,
    prepare_type_hierarchy,
    subtypes,
    supertypes,
)
from .lsp_data_model import LspModel
from .methods import RequestMethodEnum
from .protocol_structures import (
    CancelParams,
    ErrorCodes,
    NotificationMessage,
    RequestMessage,
    ResponseError,
    ResponseMessage,
)
from .rpc_protocol import RpcProtocol
from .server_capabilities import (
    InitializeResult,
    PositionEncodingKind,
    ServerCapabilities,
)
from .utils.uri import uri_to_path

logger = logging.getLogger(__name__)


class LspServer:
    __initialized: bool
    __cli_config: WokeConfig
    __workspace_config: Optional[WokeConfig]
    __workspace_path: Optional[Path]
    __context: LspContext
    __protocol: RpcProtocol
    __run: bool
    __request_id_counter: int
    __sent_requests: Dict[Union[int, str], asyncio.Event]
    __message_responses: Dict[Union[int, str], ResponseMessage]
    __compilation_task: Optional[asyncio.Task]
    __diagnostics_task: Optional[asyncio.Task]
    __diagnostics_queue: asyncio.Queue

    __method_mapping: Dict[str, Tuple[Callable, Optional[Type[LspModel]]]]
    __notification_mapping: Dict[str, Tuple[Callable, Optional[Type[LspModel]]]]

    def __init__(
        self,
        config: WokeConfig,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self.__diagnostics_queue = asyncio.Queue()
        self.__initialized = False
        self.__cli_config = config
        self.__workspace_config = None
        self.__workspace_path = None
        self.__context = LspContext(self, self.__diagnostics_queue)
        self.__protocol = RpcProtocol(reader, writer)
        self.__run = True
        self.__request_id_counter = 0
        self.__sent_requests = {}
        self.__message_responses = {}
        self.__compilation_task = None
        self.__diagnostics_task = None

        self.__method_mapping = {
            RequestMethodEnum.INITIALIZE: (self._initialize, InitializeParams),
            RequestMethodEnum.SHUTDOWN: (self._shutdown, None),
            RequestMethodEnum.DOCUMENT_LINK: (
                partial(document_link, self.__context),
                DocumentLinkParams,
            ),
            RequestMethodEnum.PREPARE_TYPE_HIERARCHY: (
                partial(prepare_type_hierarchy, self.__context),
                TypeHierarchyPrepareParams,
            ),
            RequestMethodEnum.TYPE_HIERARCHY_SUPERTYPES: (
                partial(supertypes, self.__context),
                TypeHierarchySupertypesParams,
            ),
            RequestMethodEnum.TYPE_HIERARCHY_SUBTYPES: (
                partial(subtypes, self.__context),
                TypeHierarchySubtypesParams,
            ),
            RequestMethodEnum.REFERENCES: (
                partial(references, self.__context),
                ReferenceParams,
            ),
            RequestMethodEnum.DOCUMENT_SYMBOL: (
                partial(document_symbol, self.__context),
                DocumentSymbolParams,
            ),
        }

        self.__notification_mapping = {
            RequestMethodEnum.INITIALIZED: (self._initialized, InitializedParams),
            RequestMethodEnum.CANCEL_REQUEST: (self._cancel_request, CancelParams),
            RequestMethodEnum.PROGRESS: (self._progress, ProgressParams),
            RequestMethodEnum.LOG_TRACE: (self._log_trace, LogTraceParams),
            RequestMethodEnum.SET_TRACE: (self._set_trace, SetTraceParams),
            RequestMethodEnum.TEXT_DOCUMENT_DID_OPEN: (
                self._text_document_did_open,
                DidOpenTextDocumentParams,
            ),
            RequestMethodEnum.TEXT_DOCUMENT_DID_CHANGE: (
                self._text_document_did_change,
                DidChangeTextDocumentParams,
            ),
            RequestMethodEnum.TEXT_DOCUMENT_WILL_SAVE: (
                self._text_document_will_save,
                WillSaveTextDocumentParams,
            ),
            RequestMethodEnum.TEXT_DOCUMENT_DID_SAVE: (
                self._text_document_did_save,
                DidSaveTextDocumentParams,
            ),
            RequestMethodEnum.TEXT_DOCUMENT_DID_CLOSE: (
                self._text_document_did_close,
                DidCloseTextDocumentParams,
            ),
            RequestMethodEnum.WORKSPACE_DID_CHANGE_CONFIGURATION: (
                self._workspace_did_change_configuration,
                DidChangeConfigurationParams,
            ),
        }

    async def run(self) -> None:
        messages_queue = asyncio.Queue()
        messages_task = asyncio.create_task(self._messages_loop(messages_queue))

        while self.__run:
            message = await self.__protocol.receive()
            if isinstance(message, ResponseMessage):
                await self._handle_response(message)
            else:
                await messages_queue.put(message)

        messages_task.cancel()
        if self.__compilation_task is not None:
            self.__compilation_task.cancel()
        if self.__diagnostics_task is not None:
            self.__diagnostics_task.cancel()

    async def _messages_loop(self, queue: asyncio.Queue) -> NoReturn:
        while True:
            message = await queue.get()
            if isinstance(message, RequestMessage):
                await self._handle_message(message)
            elif isinstance(message, NotificationMessage):
                await self._handle_notification(message)
            else:
                raise Exception("Unknown message type")

    async def send_request(self, method: RequestMethodEnum, params: Any = None) -> Any:
        request = RequestMessage(
            jsonrpc="2.0", id=self.__request_id_counter, method=method, params=params
        )
        self.__sent_requests[request.id] = asyncio.Event()
        self.__request_id_counter += 1

        logger.debug(f"Sending request:\n{request}")
        await self.__protocol.send(request)
        await self.__sent_requests[request.id].wait()
        self.__sent_requests.pop(request.id)
        response = self.__message_responses.pop(request.id)

        if response.error is not None:
            raise LspError(
                response.error.code, response.error.message, response.error.data
            )
        return response.result

    async def send_notification(
        self, method: str, params: Optional[Any] = None
    ) -> None:
        notification = NotificationMessage(
            jsonrpc="2.0",
            method=method,
            params=params,
        )
        logger.debug(f"Sending notification:\n{notification}")
        await self.__protocol.send(notification)

    async def log_message(self, message: str, type: MessageType) -> None:
        params = LogMessageParams(
            type=type,
            message=message,
        )
        await self.send_notification(RequestMethodEnum.WINDOW_LOG_MESSAGE, params)

    async def _handle_message(self, request: RequestMessage) -> None:
        logger.info(f"Message received: {request}")

        # Init before request needed
        if request.method != RequestMethodEnum.INITIALIZE and not self.__initialized:
            response = self._serve_error(
                request,
                ErrorCodes.ServerNotInitialized,
                "Server has not been initialized",
            )
            await self.__protocol.send(response)
            return

        # Handling request
        try:
            response = await self._serve_response(request)
        except LspError as e:
            response = self._serve_error(request, e.code, e.message)
        await self.__protocol.send(response)

    async def _handle_notification(self, notification: NotificationMessage) -> None:
        logger.info(f"Notification received: {notification}")

        if not self.__initialized and notification.method != RequestMethodEnum.EXIT:
            return

        try:
            n, params_type = self.__notification_mapping[notification.method]
        except KeyError:
            logger.error(
                f"Incoming notification type '{notification.method}' not implemented."
            )
            raise NotImplementedError()

        if params_type is not None:
            await n(params_type.parse_obj(notification.params))
        else:
            await n(None)

    async def _handle_response(self, response: ResponseMessage) -> None:
        logger.info(f"Response received: {response}")

        if response.id is None:
            logger.error(f"Response without id: {response}")
            return

        try:
            self.__message_responses[response.id] = response
            self.__sent_requests[response.id].set()
        except KeyError:
            logger.error(
                f"Received response with id {response.id} but no such request was sent."
            )

    async def _serve_response(self, request: RequestMessage) -> ResponseMessage:
        try:
            m, params_type = self.__method_mapping[request.method]
        except KeyError:
            logger.error(f"Incoming method type '{request.method}' not implemented.")
            raise NotImplementedError()

        if params_type is not None:
            response = await m(params_type.parse_obj(request.params))
        else:
            response = await m(None)

        response_message = ResponseMessage(
            jsonrpc="2.0", id=request.id, result=response, error=None
        )
        logger.info(f"Serving response: {response_message}")
        return response_message

    @staticmethod
    def _serve_error(
        request: RequestMessage, error_code: int, msg: str
    ) -> ResponseMessage:
        response_error = ResponseError(code=error_code, message=msg, data=None)
        response_message = ResponseMessage(
            jsonrpc="2.0", id=request.id, error=response_error, result=None
        )
        logger.warning(f"Serving error response: {response_message}")
        return response_message

    async def _initialize(self, params: InitializeParams) -> InitializeResult:
        if self.__initialized:
            raise LspError(ErrorCodes.InvalidRequest, "Server already initialized")

        if params.workspace_folders is not None:
            if len(params.workspace_folders) != 1:
                raise LspError(
                    ErrorCodes.RequestFailed,
                    "Exactly one workspace directory must be provided.",
                    InitializeError(retry=False),
                )
            path = uri_to_path(params.workspace_folders[0].uri).resolve(strict=True)
        elif params.root_uri is not None:
            path = uri_to_path(params.root_uri).resolve(strict=True)
        elif params.root_path is not None:
            path = Path(params.root_path).resolve(strict=True)
        else:
            raise LspError(
                ErrorCodes.RequestFailed,
                "Exactly one workspace directory must be provided.",
                InitializeError(retry=False),
            )

        self.__initialized = True
        self.__workspace_path = path

        server_capabilities = ServerCapabilities(
            position_encoding=PositionEncodingKind.UTF16,
            text_document_sync=TextDocumentSyncOptions(
                open_close=True, change=TextDocumentSyncKind.INCREMENTAL
            ),
            document_link_provider=DocumentLinkOptions(
                resolve_provider=False,
            ),
            type_hierarchy_provider=True,
            references_provider=True,
            document_symbol_provider=True,
        )
        return InitializeResult(capabilities=server_capabilities, server_info=None)

    async def _cancel_request(self, params: CancelParams) -> None:
        pass

    async def _progress(self, params: ProgressParams) -> None:
        pass

    async def _log_trace(self, params: LogTraceParams) -> None:
        pass

    async def _set_trace(self, params: SetTraceParams) -> None:
        pass

    async def _shutdown(self, params: Any) -> None:
        self.__run = False

    async def _handle_config_change(self, raw_config: dict) -> bool:
        assert self.__workspace_path is not None

        run = True
        invalid_options = []
        while run:
            try:
                WokeConfig.fromdict(
                    raw_config,
                    project_root_path=self.__workspace_path,
                    woke_root_path=self.__cli_config.woke_root_path,
                )
                run = False
            except ValidationError as e:
                for error in e.errors():
                    invalid_options.append(error["loc"])
                    invalid_option = raw_config
                    for segment in error["loc"][:-1]:
                        invalid_option = invalid_option[segment]

                    if isinstance(invalid_option, list):
                        invalid_option.remove(error["loc"][-1])
                    elif isinstance(invalid_option, dict):
                        del invalid_option[error["loc"][-1]]
                    else:
                        raise NotImplementedError()
        if len(invalid_options) > 0:
            message = "Failed to parse the following config options:\n" + "\n".join(
                f"    woke -> {' -> '.join(option)}" for option in invalid_options
            )
            await self.log_message(message, MessageType.WARNING)

        if self.__workspace_config is None:
            self.__workspace_config = WokeConfig.fromdict(
                raw_config,
                project_root_path=self.__workspace_path,
                woke_root_path=self.__cli_config.woke_root_path,
            )
            return False
        else:
            return self.__workspace_config.update(raw_config)

    async def _initialized(self, params: InitializedParams) -> None:
        async def _post_initialized():
            code_config = await self.get_configuration()
            assert isinstance(code_config, list)
            assert len(code_config) == 1
            assert isinstance(code_config[0], dict)

            await self._handle_config_change(code_config[0])
            assert self.__workspace_config is not None

            self.__compilation_task = asyncio.create_task(
                self.__context.compiler.run(self.__workspace_config)
            )
            self.__diagnostics_task = asyncio.create_task(
                diagnostics_loop(self, self.__context, self.__diagnostics_queue)
            )

        asyncio.create_task(_post_initialized())

    async def _workspace_did_change_configuration(
        self, params: DidChangeConfigurationParams
    ) -> None:
        logger.debug(f"Received configuration change: {params}")
        if "woke" in params.settings:
            changed = await self._handle_config_change(params.settings["woke"])
            if changed:
                await self.__context.compiler.force_recompile()

    async def _text_document_did_open(self, params: DidOpenTextDocumentParams) -> None:
        await self.__context.compiler.add_change(params)

    async def _text_document_did_change(
        self, params: DidChangeTextDocumentParams
    ) -> None:
        await self.__context.compiler.add_change(params)

    async def _text_document_will_save(
        self, params: WillSaveTextDocumentParams
    ) -> None:
        pass

    async def _text_document_did_save(self, params: DidSaveTextDocumentParams) -> None:
        pass

    async def _text_document_did_close(
        self, params: DidCloseTextDocumentParams
    ) -> None:
        await self.__context.compiler.add_change(params)

    async def get_configuration(self) -> None:
        params = ConfigurationParams(
            items=[
                ConfigurationItem(
                    section="woke",
                )
            ]
        )
        return await self.send_request(
            RequestMethodEnum.WORKSPACE_CONFIGURATION, params
        )
