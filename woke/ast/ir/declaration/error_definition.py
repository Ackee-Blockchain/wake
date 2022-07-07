from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Optional, Tuple, Union

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcErrorDefinition

from ..meta.parameter_list import ParameterList
from ..meta.structured_documentation import StructuredDocumentation
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from ..meta.source_unit import SourceUnit
    from .contract_definition import ContractDefinition


class ErrorDefinition(DeclarationAbc):
    _ast_node: SolcErrorDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    __parameters: ParameterList
    __documentation: Optional[StructuredDocumentation]

    def __init__(self, init: IrInitTuple, error: SolcErrorDefinition, parent: IrAbc):
        super().__init__(init, error, parent)
        self.__parameters = ParameterList(init, error.parameters, self)
        self.__documentation = (
            StructuredDocumentation(init, error.documentation, self)
            if error.documentation
            else None
        )

    def _parse_name_location(self) -> Tuple[int, int]:
        # SolcErrorDefinition node always contains name_location attribute
        # this method is implemented here just for completeness and to satisfy the linter
        byte_start = self._ast_node.name_location.byte_offset
        byte_length = self._ast_node.name_location.byte_length
        return byte_start, byte_start + byte_length

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        return self._parent

    @property
    @lru_cache(maxsize=None)
    def canonical_name(self) -> str:
        from .contract_definition import ContractDefinition

        if isinstance(self._parent, ContractDefinition):
            return f"{self._parent.canonical_name}.{self._name}"
        return self._name

    @property
    def parameters(self) -> ParameterList:
        return self.__parameters

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation
