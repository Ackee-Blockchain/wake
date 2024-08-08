from typing import List

from typing_extensions import Literal

from .common_structures import DocumentUri, Location, Position
from .lsp_data_model import LspModel


class CommandAbc(LspModel):
    command: str


class GoToLocationsCommand(CommandAbc):
    uri: DocumentUri  # pyright: ignore reportInvalidTypeForm
    position: Position
    locations: List[Location]
    multiple: Literal["peek", "gotoAndPeek", "goto"]
    no_results_message: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="goToLocations")


class PeekLocationsCommand(CommandAbc):
    uri: DocumentUri  # pyright: ignore reportInvalidTypeForm
    position: Position
    locations: List[Location]
    multiple: Literal["peek", "gotoAndPeek", "goto"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="peekLocations")


class OpenCommand(CommandAbc):
    uri: DocumentUri  # pyright: ignore reportInvalidTypeForm

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="open")


class CopyToClipboardCommand(CommandAbc):
    text: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="copyToClipboard")


class ShowMessageCommand(CommandAbc):
    message: str
    kind: Literal["info", "warning", "error"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="showMessage")


class ShowDotCommand(CommandAbc):
    title: str
    dot: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, command="showDot")
