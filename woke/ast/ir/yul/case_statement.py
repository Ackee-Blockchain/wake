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
    __body: Block
    __value: Union[typing_extensions.Literal["default"], Literal]

    def __init__(self, init: IrInitTuple, case_: YulCase, parent: YulAbc):
        super().__init__(init, case_, parent)
        self.__body = Block(init, case_.body, self)
        if case_.value == "default":
            self.__value = "default"
        else:
            self.__value = Literal(init, case_.value, self)

    def __iter__(self) -> Iterator[YulAbc]:
        yield self
        yield from self.__body
        if self.__value != "default":
            yield from self.__value

    @property
    def parent(self) -> Switch:
        return self._parent

    @property
    def body(self) -> Block:
        return self.__body

    @property
    def value(self) -> Union[typing_extensions.Literal["default"], Literal]:
        return self.__value
