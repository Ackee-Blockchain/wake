from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Union

import typing_extensions

from woke.ir.ast import SolcYulCase

from ..utils import IrInitTuple
from .abc import YulAbc
from .block import YulBlock
from .literal import YulLiteral

if TYPE_CHECKING:
    from .switch import YulSwitch


class YulCase(YulAbc):
    """
    TBD
    """

    _parent: YulSwitch
    _body: YulBlock
    _value: Union[typing_extensions.Literal["default"], YulLiteral]

    def __init__(self, init: IrInitTuple, case_: SolcYulCase, parent: YulAbc):
        super().__init__(init, case_, parent)
        self._body = YulBlock(init, case_.body, self)
        if case_.value == "default":
            self._value = "default"
        else:
            self._value = YulLiteral(init, case_.value, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._body
        if self._value != "default":
            yield from self._value

    @property
    def parent(self) -> YulSwitch:
        return self._parent

    @property
    def body(self) -> YulBlock:
        return self._body

    @property
    def value(self) -> Union[typing_extensions.Literal["default"], YulLiteral]:
        return self._value
