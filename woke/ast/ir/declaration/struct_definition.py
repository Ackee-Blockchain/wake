from __future__ import annotations

import re
from typing import TYPE_CHECKING, List, Tuple, Union

from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition
    from ..meta.source_unit import SourceUnit

from woke.ast.enums import Visibility
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcStructDefinition


class StructDefinition(DeclarationAbc):
    _ast_node: SolcStructDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    __canonical_name: str
    __members: List[VariableDeclaration]
    __visibility: Visibility

    def __init__(
        self, init: IrInitTuple, struct_definition: SolcStructDefinition, parent: IrAbc
    ):
        super().__init__(init, struct_definition, parent)
        self.__canonical_name = struct_definition.canonical_name
        # TODO scope
        self.__visibility = struct_definition.visibility

        self.__members = []
        for member in struct_definition.members:
            self.__members.append(VariableDeclaration(init, member, self))

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        STRUCT_RE = re.compile(
            r"^\s*struct\s+(?P<name>{identifier})".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )

        byte_start = self._ast_node.src.byte_offset
        match = STRUCT_RE.match(self._source)
        assert match
        return byte_start + match.start("name"), byte_start + match.end("name")

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        return self._parent

    @property
    def canonical_name(self) -> str:
        return self.__canonical_name

    @property
    def members(self) -> Tuple[VariableDeclaration]:
        return tuple(self.__members)

    @property
    def visibility(self) -> Visibility:
        return self.__visibility
