from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Tuple, Union

from ..nodes import SolcEnumDefinition
from .abc import IrAbc
from .enum_value import EnumValue
from .utils import IrInitTuple

# if TYPE_CHECKING:
# from .contract_definition import ContractDefinition
# from .source_unit import SourceUnit


logger = logging.getLogger(__name__)


class EnumDefinition(IrAbc):
    _ast_node: SolcEnumDefinition
    # _parent: Union[ContractDefinition, SourceUnit]

    __name: str
    __canonical_name: str
    __values: List[EnumValue]

    def __init__(self, init: IrInitTuple, enum: SolcEnumDefinition, parent: IrAbc):
        super().__init__(init, enum, parent)
        self.__name = enum.name
        self.__canonical_name = enum.canonical_name

        self.__values = []
        for value in enum.members:
            self.__values.append(EnumValue(init, value, self))

    # @property
    # def parent(self) -> Union[SourceUnit, ContractDefinition]:
    # return self._parent

    @property
    def name(self) -> str:
        return self.__name

    @property
    def canonical_name(self) -> str:
        return self.__canonical_name

    @property
    def values(self) -> Tuple[EnumValue]:
        return tuple(self.__values)
