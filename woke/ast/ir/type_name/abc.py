from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    SolcArrayTypeName,
    SolcElementaryTypeName,
    SolcFunctionTypeName,
    SolcMapping,
    SolcTypeNameUnion,
    SolcUserDefinedTypeName,
)


class TypeNameAbc(IrAbc):
    _type_identifier: Optional[str]
    _type_string: Optional[str]

    def __init__(self, init: IrInitTuple, type_name: SolcTypeNameUnion, parent: IrAbc):
        super().__init__(init, type_name, parent)
        self._type_identifier = type_name.type_descriptions.type_identifier
        self._type_string = type_name.type_descriptions.type_string

    @staticmethod
    def from_ast(
        init: IrInitTuple, type_name: SolcTypeNameUnion, parent: IrAbc
    ) -> "TypeNameAbc":
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
    def type_identifier(self) -> Optional[str]:
        return self._type_identifier

    @property
    def type_string(self) -> Optional[str]:
        return self._type_string
