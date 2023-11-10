from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ..declarations.variable_declaration import VariableDeclaration
    from ..declarations.user_defined_value_type_definition import (
        UserDefinedValueTypeDefinition,
    )
    from ..expressions.elementary_type_name_expression import (
        ElementaryTypeNameExpression,
    )
    from ..expressions.new_expression import NewExpression
    from ..meta.using_for_directive import UsingForDirective
    from .array_type_name import ArrayTypeName

from wake.core import get_logger
from wake.ir.abc import SolidityAbc
from wake.ir.ast import (
    SolcArrayTypeName,
    SolcElementaryTypeName,
    SolcFunctionTypeName,
    SolcMapping,
    SolcTypeNameUnion,
    SolcUserDefinedTypeName,
    TypeDescriptionsModel,
)
from wake.ir.types import (
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
    UserDefinedValueType,
)
from wake.ir.utils import IrInitTuple
from wake.utils.string import StringReader

logger = get_logger(__name__)


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
        UserDefinedValueType,
    ]:
        """
        Returns:
            Type of the type name.
        """
        assert self._type_descriptions.type_identifier is not None

        type_identifier = StringReader(self._type_descriptions.type_identifier)
        ret = TypeAbc.from_type_identifier(
            type_identifier, self._reference_resolver, self.source_unit.cu_hash
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
                UserDefinedValueType,
            ),
        )
        return ret

    @property
    def type_identifier(self) -> str:
        assert self._type_descriptions.type_identifier is not None
        return self._type_descriptions.type_identifier

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
