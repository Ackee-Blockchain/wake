from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ..declaration.variable_declaration import VariableDeclaration
    from ..declaration.user_defined_value_type_definition import (
        UserDefinedValueTypeDefinition,
    )
    from ..expression.elementary_type_name_expression import (
        ElementaryTypeNameExpression,
    )
    from ..expression.new_expression import NewExpression
    from ..meta.using_for_directive import UsingForDirective
    from .array_type_name import ArrayTypeName

from woke.ast.ir.abc import SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    SolcArrayTypeName,
    SolcElementaryTypeName,
    SolcFunctionTypeName,
    SolcMapping,
    SolcTypeNameUnion,
    SolcUserDefinedTypeName,
    TypeDescriptionsModel,
)
from woke.ast.types import (
    Address,
    Array,
    Bool,
    Bytes,
    Contract,
    Enum,
    Fixed,
    FixedBytes,
    Function,
    Int,
    Mapping,
    String,
    Struct,
    Type,
    TypeAbc,
    UFixed,
    UInt,
)
from woke.utils.string import StringReader

logger = logging.getLogger(__name__)


class TypeNameAbc(SolidityAbc, ABC):
    """
    Abstract base class for all IR type name nodes.
    """

    _type_descriptions: TypeDescriptionsModel

    def __init__(
        self, init: IrInitTuple, type_name: SolcTypeNameUnion, parent: SolidityAbc
    ):
        super().__init__(init, type_name, parent)
        self._type_descriptions = type_name.type_descriptions

    @staticmethod
    def from_ast(
        init: IrInitTuple, type_name: SolcTypeNameUnion, parent: SolidityAbc
    ) -> TypeNameAbc:
        from .array_type_name import ArrayTypeName
        from .elementary_type_name import ElementaryTypeName
        from .function_type_name import FunctionTypeName
        from .mapping import Mapping
        from .user_defined_type_name import UserDefinedTypeName

        if isinstance(type_name, SolcArrayTypeName):
            return ArrayTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcElementaryTypeName):
            return ElementaryTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcFunctionTypeName):
            return FunctionTypeName(init, type_name, parent)
        elif isinstance(type_name, SolcMapping):
            return Mapping(init, type_name, parent)
        elif isinstance(type_name, SolcUserDefinedTypeName):
            return UserDefinedTypeName(init, type_name, parent)

    @property
    @abstractmethod
    def parent(
        self,
    ) -> Union[
        VariableDeclaration,
        UserDefinedValueTypeDefinition,
        ElementaryTypeNameExpression,
        NewExpression,
        UsingForDirective,
        ArrayTypeName,
        Mapping,
    ]:
        """
        Returns:
            Parent node of the type name.
        """
        ...

    @property
    @lru_cache(maxsize=2048)
    def type(
        self,
    ) -> Union[
        Array,
        Address,
        Bool,
        Int,
        UInt,
        Fixed,
        UFixed,
        String,
        Bytes,
        FixedBytes,
        Type,
        Function,
        Mapping,
        Struct,
        Enum,
        Contract,
    ]:
        """
        Returns:
            Type of the type name.
        """
        assert self._type_descriptions.type_identifier is not None

        type_identifier = StringReader(self._type_descriptions.type_identifier)
        ret = TypeAbc.from_type_identifier(
            type_identifier, self._reference_resolver, self.cu_hash
        )
        assert (
            len(type_identifier) == 0 and ret is not None
        ), f"Failed to parse type identifier: {self._type_descriptions.type_identifier}"
        assert isinstance(
            ret,
            (
                Array,
                Address,
                Bool,
                Int,
                UInt,
                Fixed,
                UFixed,
                String,
                Bytes,
                FixedBytes,
                Type,
                Function,
                Mapping,
                Struct,
                Enum,
                Contract,
            ),
        )
        return ret

    @property
    def type_string(self) -> str:
        """
        !!! example
            `:::solidity mapping(uint256 => int24[])` in the case of the `:::solidity mapping(uint => int24[])` type name in the following declaration:
            ```solidity
            mapping(uint => int24[]) map;
            ```

        Returns:
            User-friendly string describing the type name type.
        """
        assert self._type_descriptions.type_string is not None
        return self._type_descriptions.type_string
