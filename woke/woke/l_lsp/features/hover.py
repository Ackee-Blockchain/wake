from typing import List, Optional, Union

from ..common_structures import (
    MarkupContent,
    MarkupKind,
    Range,
    TextDocumentPositionParams,
    WorkDoneProgressOptions,
    WorkDoneProgressParams,
)


class HoverClientCapabilities:
    dynamic_registration: Optional[bool]
    content_format: Optional[List[MarkupKind]]


class HoverOptions(WorkDoneProgressOptions):
    pass


class HoverParams(TextDocumentPositionParams, WorkDoneProgressParams):
    pass


class MarkedString:
    language: str
    value: str


MarkedStringType = Union[str, MarkedString]


class Hover:
    contents: Union[MarkedStringType, List[MarkedStringType], MarkupContent]
    range: Optional[Range]
