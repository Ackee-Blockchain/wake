from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Union

import typing_extensions

from ...nodes import YulCase
from ..utils import IrInitTuple
from .abc import YulAbc
from .block import Block
from .literal import Literal

if TYPE_CHECKING:
    from .switch import Switch


class Case(YulAbc):
    """
    TBD
    """
    _parent: Switch
    _body: Block
    _value: Union[typing_extensions.Literal["default"], Literal]

    def __init__(self, init: IrInitTuple, case_: YulCase, parent: YulAbc):
        super().__init__(init, case_, parent)
        self._body = Block(init, case_.body, self)
        if case_.value == "default":
            self._value = "default"
        else:
            self._value = Literal(init, case_.value, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self._body
        if self._value != "default":
            yield from self._value

    @property
    def parent(self) -> Switch:
        return self._parent

    @property
    def body(self) -> Block:
        return self._body

    @property
    def value(self) -> Union[typing_extensions.Literal["default"], Literal]:
        return self._value
