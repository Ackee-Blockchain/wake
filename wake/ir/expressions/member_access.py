from __future__ import annotations

import re
from functools import lru_cache, partial
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from wake.core import get_logger
from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import AstNodeId, SolcMemberAccess
from wake.ir.declarations.abc import DeclarationAbc
from wake.ir.declarations.enum_definition import EnumDefinition
from wake.ir.declarations.variable_declaration import VariableDeclaration
from wake.ir.enums import GlobalSymbol, ModifiesStateFlag
from wake.ir.expressions.abc import ExpressionAbc
from wake.ir.expressions.identifier import Identifier
from wake.ir.meta.import_directive import ImportDirective
from wake.ir.meta.source_unit import SourceUnit
from wake.ir.reference_resolver import CallbackParams
from wake.ir.types import (
    Address,
    Array,
    Bytes,
    FixedBytes,
    Function,
    Magic,
    MagicTypeKind,
    String,
    Type,
    UserDefinedValueType,
)
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..statements.abc import StatementAbc
    from ..yul.abc import YulAbc

MEMBER_RE = re.compile(r"\s*.\s*(?P<member>.+)".encode("utf-8"))


logger = get_logger(__name__)


class MemberAccess(ExpressionAbc):
    """
    Represents a member access using the dot notation.
    """

    _ast_node: SolcMemberAccess
    _parent: SolidityAbc  # TODO: make this more specific

    _expression: ExpressionAbc
    _member_name: str
    _referenced_declaration_id: Optional[AstNodeId]

    def __init__(
        self, init: IrInitTuple, member_access: SolcMemberAccess, parent: SolidityAbc
    ):
        super().__init__(init, member_access, parent)
        self._expression = ExpressionAbc.from_ast(init, member_access.expression, self)
        assert self._expression.byte_location[0] == self.byte_location[0]
        assert self._expression.byte_location[1] < self.byte_location[1]

        self._member_name = member_access.member_name
        self._referenced_declaration_id = member_access.referenced_declaration

        self._reference_resolver.register_post_process_callback(
            self._post_process, priority=-1
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._expression

    def _post_process(self, callback_params: CallbackParams):
        # workaround for enum value bug in Solidity versions prior to 0.8.2
        if self._referenced_declaration_id is None:
            if isinstance(self._expression, Identifier) or (
                isinstance(self._expression, MemberAccess)
                and self._expression._referenced_declaration_id is not None
            ):
                referenced_declaration = self._expression.referenced_declaration
                if isinstance(referenced_declaration, EnumDefinition):
                    for enum_value in referenced_declaration.values:
                        if enum_value.name == self._member_name:
                            node_path_order = (
                                self._reference_resolver.get_node_path_order(
                                    AstNodeId(enum_value.ast_node_id),
                                    enum_value.source_unit.cu_hash,
                                )
                            )
                            this_cu_id = self._reference_resolver.get_ast_id_from_cu_node_path_order(
                                node_path_order, self.source_unit.cu_hash
                            )
                            self._referenced_declaration_id = this_cu_id
                            break

        if self._referenced_declaration_id is None:
            expr_type = self.expression.type

            if isinstance(expr_type, Address):
                if self.member_name == "balance":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ADDRESS_BALANCE
                    )
                elif self.member_name == "code":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ADDRESS_CODE
                    )
                elif self.member_name == "codehash":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ADDRESS_CODEHASH
                    )
                elif self.member_name == "transfer":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ADDRESS_TRANSFER
                    )
                elif self.member_name == "send":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ADDRESS_SEND
                    )
                elif self.member_name == "call":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ADDRESS_CALL
                    )
                elif self.member_name == "delegatecall":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ADDRESS_DELEGATECALL
                    )
                elif self.member_name == "staticcall":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ADDRESS_STATICCALL
                    )
                else:
                    assert False, f"Unknown address member: {self.member_name}"
            elif isinstance(expr_type, Array):
                if self.member_name == "length":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.ARRAY_LENGTH
                    )
                elif self.member_name == "push":
                    self._referenced_declaration_id = AstNodeId(GlobalSymbol.ARRAY_PUSH)
                elif self.member_name == "pop":
                    self._referenced_declaration_id = AstNodeId(GlobalSymbol.ARRAY_POP)
                else:
                    assert False, f"Unknown array member: {self.member_name}"
            elif isinstance(expr_type, (Bytes, FixedBytes)):
                if self.member_name == "length":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.BYTES_LENGTH
                    )
                elif self.member_name == "push":
                    self._referenced_declaration_id = AstNodeId(GlobalSymbol.BYTES_PUSH)
                else:
                    assert False, f"Unknown bytes member: {self.member_name}"
            elif isinstance(expr_type, Function):
                if self.member_name == "selector":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.FUNCTION_SELECTOR
                    )
                elif self.member_name == "value":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.FUNCTION_VALUE
                    )
                elif self.member_name == "gas":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.FUNCTION_GAS
                    )
                elif self.member_name == "address":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbol.FUNCTION_ADDRESS
                    )
                else:
                    assert False, f"Unknown function member: {self.member_name}"
            elif isinstance(expr_type, Magic):
                if expr_type.kind == MagicTypeKind.BLOCK:
                    if self.member_name == "basefee":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BLOCK_BASEFEE
                        )
                    elif self.member_name == "chainid":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BLOCK_CHAINID
                        )
                    elif self.member_name == "coinbase":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BLOCK_COINBASE
                        )
                    elif self.member_name == "difficulty":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BLOCK_DIFFICULTY
                        )
                    elif self.member_name == "gaslimit":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BLOCK_GASLIMIT
                        )
                    elif self.member_name == "number":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BLOCK_NUMBER
                        )
                    elif self.member_name == "timestamp":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BLOCK_TIMESTAMP
                        )
                    elif self.member_name == "prevrandao":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BLOCK_PREVRANDAO
                        )
                    else:
                        assert False, f"Unknown block member {self.member_name}"
                elif expr_type.kind == MagicTypeKind.MESSAGE:
                    if self.member_name == "data":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.MSG_DATA
                        )
                    elif self.member_name == "sender":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.MSG_SENDER
                        )
                    elif self.member_name == "sig":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.MSG_SIG
                        )
                    elif self.member_name == "value":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.MSG_VALUE
                        )
                    else:
                        assert False, f"Unknown msg member {self.member_name}"
                elif expr_type.kind == MagicTypeKind.TRANSACTION:
                    if self.member_name == "gasprice":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.TX_GASPRICE
                        )
                    elif self.member_name == "origin":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.TX_ORIGIN
                        )
                    else:
                        assert False, f"Unknown tx member {self.member_name}"
                elif expr_type.kind == MagicTypeKind.ABI:
                    if self.member_name == "decode":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.ABI_DECODE
                        )
                    elif self.member_name == "encode":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.ABI_ENCODE
                        )
                    elif self.member_name == "encodePacked":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.ABI_ENCODE_PACKED
                        )
                    elif self.member_name == "encodeWithSelector":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.ABI_ENCODE_WITH_SELECTOR
                        )
                    elif self.member_name == "encodeWithSignature":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.ABI_ENCODE_WITH_SIGNATURE
                        )
                    elif self.member_name == "encodeCall":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.ABI_ENCODE_CALL
                        )
                    else:
                        assert False, f"Unknown abi member {self.member_name}"
                elif expr_type.kind == MagicTypeKind.META_TYPE:
                    if self.member_name == "name":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.TYPE_NAME
                        )
                    elif self.member_name == "creationCode":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.TYPE_CREATION_CODE
                        )
                    elif self.member_name == "runtimeCode":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.TYPE_RUNTIME_CODE
                        )
                    elif self.member_name == "interfaceId":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.TYPE_INTERFACE_ID
                        )
                    elif self.member_name == "min":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.TYPE_MIN
                        )
                    elif self.member_name == "max":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.TYPE_MAX
                        )
                    else:
                        assert False, f"Unknown type member {self.member_name}"
            elif isinstance(expr_type, Type):
                if isinstance(expr_type.actual_type, Bytes):
                    if self.member_name == "concat":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.BYTES_CONCAT
                        )
                    else:
                        assert False, f"Unknown bytes member {self.member_name}"
                elif isinstance(expr_type.actual_type, String):
                    if self.member_name == "concat":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.STRING_CONCAT
                        )
                    else:
                        assert False, f"Unknown string member {self.member_name}"
                elif isinstance(expr_type.actual_type, UserDefinedValueType):
                    if self.member_name == "wrap":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.USER_DEFINED_VALUE_TYPE_WRAP
                        )
                    elif self.member_name == "unwrap":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbol.USER_DEFINED_VALUE_TYPE_UNWRAP
                        )
                    else:
                        assert (
                            False
                        ), f"Unknown user defined value type member {self.member_name}"
                else:
                    assert (
                        False
                    ), f"Unknown type member {self.member_name} {expr_type.actual_type}"

        assert (
            self._referenced_declaration_id is not None
        ), f"Unknown member {self.member_name}"

        if self._referenced_declaration_id < 0:
            global_symbol = GlobalSymbol(self._referenced_declaration_id)
            self._reference_resolver.register_global_symbol_reference(
                global_symbol, self
            )
            self._reference_resolver.register_destroy_callback(
                self.source_unit.file, partial(self._destroy, global_symbol)
            )
        else:
            node = self._reference_resolver.resolve_node(
                self._referenced_declaration_id, self.source_unit.cu_hash
            )

            if isinstance(node, DeclarationAbc):
                node.register_reference(self)
                self._reference_resolver.register_destroy_callback(
                    self.source_unit.file, partial(self._destroy, node)
                )
            elif isinstance(node, ImportDirective):
                # make this node to reference the source unit directly
                assert node.unit_alias is not None
                source_unit = callback_params.source_units[node.imported_file]
                node_path_order = self._reference_resolver.get_node_path_order(
                    AstNodeId(source_unit.ast_node_id),
                    source_unit.cu_hash,
                )
                self._referenced_declaration_id = (
                    self._reference_resolver.get_ast_id_from_cu_node_path_order(
                        node_path_order, self.source_unit.cu_hash
                    )
                )
            else:
                raise TypeError(f"Unexpected type: {type(node)}")

    def _destroy(
        self, referenced_declaration: Union[GlobalSymbol, DeclarationAbc]
    ) -> None:
        if isinstance(referenced_declaration, GlobalSymbol):
            self._reference_resolver.unregister_global_symbol_reference(
                referenced_declaration, self
            )
        elif isinstance(referenced_declaration, DeclarationAbc):
            referenced_declaration.unregister_reference(self)
        else:
            raise TypeError(f"Unexpected type: {type(referenced_declaration)}")

    @property
    def parent(self) -> SolidityAbc:
        return self._parent

    @property
    def expression(self) -> ExpressionAbc:
        """
        Returns:
            Expression, whose member is accessed.
        """
        return self._expression

    @property
    def member_name(self) -> str:
        """
        Returns:
            Name of the member being accessed.
        """
        return self._member_name

    @property
    @lru_cache(maxsize=2048)
    def member_location(self) -> Tuple[int, int]:
        """
        In the case of [MemberAccess][wake.ir.expressions.member_access.MemberAccess], [byte_location][wake.ir.abc.IrAbc.byte_location] returns the byte location including the expression, whose member is accessed.
        This property returns the byte location of the member name only.

        Returns:
            Byte location of the member name.
        """
        relative_expression_end = (
            self._expression.byte_location[1] - self.byte_location[0]
        )
        match = MEMBER_RE.match(self._source[relative_expression_end:])
        assert match
        return self._expression.byte_location[1] + match.start(
            "member"
        ), self._expression.byte_location[1] + match.end("member")

    @property
    def referenced_declaration(
        self,
    ) -> Union[DeclarationAbc, GlobalSymbol, SourceUnit]:
        """
        Returns:
            Referenced declaration.
        """
        assert self._referenced_declaration_id is not None
        if self._referenced_declaration_id < 0:
            return GlobalSymbol(self._referenced_declaration_id)

        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self.source_unit.cu_hash
        )
        assert isinstance(node, (DeclarationAbc, SourceUnit))
        return node

    @property
    @lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        referenced_declaration = self.referenced_declaration
        return (
            isinstance(referenced_declaration, VariableDeclaration)
            and referenced_declaration.is_state_variable
            or self.expression.is_ref_to_state_variable
        )

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return self.expression.modifies_state
