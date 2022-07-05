import asyncio
import logging
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Type

from ..config import WokeConfig
from .common_structures import (
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
    __config: WokeConfig
    __context: LspContext
    __protocol: RpcProtocol
    __run: bool
    __compilation_task: Optional[asyncio.Task]

    __method_mapping: Dict[str, Tuple[Callable, Optional[Type[LspModel]]]]
    __notification_mapping: Dict[str, Tuple[Callable, Optional[Type[LspModel]]]]

    def __init__(
        self,
        config: WokeConfig,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self.__initialized = False
        self.__config = config
        self.__context = LspContext(config)
        self.__protocol = RpcProtocol(reader, writer)
        self.__run = True
        self.__compilation_task = None

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
        }

    async def run(self) -> None:
        while self.__run:
            message = await self.__protocol.receive()
            if isinstance(message, RequestMessage):
                await self._handle_message(message)
            else:
                await self._handle_notification(message)
        if self.__compilation_task is not None:
            self.__compilation_task.cancel()

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
        self.__context.config.project_root_path = path
        self.__context.config.load_configs()
        self.__compilation_task = asyncio.create_task(self.__context.compiler.run())

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

    async def _initialized(self, params: InitializedParams) -> None:
        pass

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
