from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Tuple, Union

from ..type_name.elementary_type_name import ElementaryTypeName
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition
    from ..meta.source_unit import SourceUnit

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcUserDefinedValueTypeDefinition


class UserDefinedValueTypeDefinition(DeclarationAbc):
    """
    Definition of a user defined value type.

    !!! example
        ```solidity
        type MyInt is uint;
        ```
    """

    _ast_node: SolcUserDefinedValueTypeDefinition
    _parent: Union[ContractDefinition, SourceUnit]

    _underlying_type: ElementaryTypeName

    def __init__(
        self,
        init: IrInitTuple,
        user_defined_value_type_definition: SolcUserDefinedValueTypeDefinition,
        parent: SolidityAbc,
    ):
        super().__init__(init, user_defined_value_type_definition, parent)
        self._underlying_type = ElementaryTypeName(
            init, user_defined_value_type_definition.underlying_type, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._underlying_type

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        USER_DEF_VAL_TYPE_RE = re.compile(
            r"^\s*type\s+(?P<name>{identifier})".format(identifier=IDENTIFIER).encode(
                "utf-8"
            )
        )

        byte_start = self._ast_node.src.byte_offset
        match = USER_DEF_VAL_TYPE_RE.match(self._source)
        assert match
        return byte_start + match.start("name"), byte_start + match.end("name")

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    @lru_cache(maxsize=2048)
    def canonical_name(self) -> str:
        from .contract_definition import ContractDefinition

        if isinstance(self._parent, ContractDefinition):
            return f"{self._parent.canonical_name}.{self._name}"
        return self._name

    @property
    @lru_cache(maxsize=2048)
    def declaration_string(self) -> str:
        return f"type {self.name} is {self._underlying_type.source}"

    @property
    def underlying_type(self) -> ElementaryTypeName:
        """
        Returns:
            Underlying type of the user defined value type.
        """
        return self._underlying_type
