import logging
import re
from functools import lru_cache, partial
from typing import Iterator, Optional, Set, Tuple, Union

from woke.ast.enums import GlobalSymbolsEnum, ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.declaration.abc import DeclarationAbc
from woke.ast.ir.declaration.enum_definition import EnumDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.expression.identifier import Identifier
from woke.ast.ir.reference_resolver import CallbackParams
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcMemberAccess
from woke.ast.types import (
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

MEMBER_RE = re.compile(r"\s*.\s*(?P<member>.+)".encode("utf-8"))


logger = logging.getLogger(__name__)


class MemberAccess(ExpressionAbc):
    """
    TBD
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

        self._reference_resolver.register_post_process_callback(self._post_process)

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
                                    enum_value.cu_hash,
                                )
                            )
                            this_cu_id = self._reference_resolver.get_ast_id_from_cu_node_path_order(
                                node_path_order, self.cu_hash
                            )
                            self._referenced_declaration_id = this_cu_id
                            break

        if self._referenced_declaration_id is None:
            expr_type = self.expression.type

            if isinstance(expr_type, Address):
                if self.member_name == "balance":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ADDRESS_BALANCE
                    )
                elif self.member_name == "code":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ADDRESS_CODE
                    )
                elif self.member_name == "codehash":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ADDRESS_CODEHASH
                    )
                elif self.member_name == "transfer":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ADDRESS_TRANSFER
                    )
                elif self.member_name == "send":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ADDRESS_SEND
                    )
                elif self.member_name == "call":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ADDRESS_CALL
                    )
                elif self.member_name == "delegatecall":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ADDRESS_DELEGATECALL
                    )
                elif self.member_name == "staticcall":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ADDRESS_STATICCALL
                    )
                else:
                    assert False, f"Unknown address member: {self.member_name}"
            elif isinstance(expr_type, Array):
                if self.member_name == "length":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ARRAY_LENGTH
                    )
                elif self.member_name == "push":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ARRAY_PUSH
                    )
                elif self.member_name == "pop":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.ARRAY_POP
                    )
                else:
                    assert False, f"Unknown array member: {self.member_name}"
            elif isinstance(expr_type, (Bytes, FixedBytes)):
                if self.member_name == "length":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.BYTES_LENGTH
                    )
                elif self.member_name == "push":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.BYTES_PUSH
                    )
                else:
                    assert False, f"Unknown bytes member: {self.member_name}"
            elif isinstance(expr_type, Function):
                if self.member_name == "selector":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.FUNCTION_SELECTOR
                    )
                elif self.member_name == "value":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.FUNCTION_VALUE
                    )
                elif self.member_name == "gas":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.FUNCTION_GAS
                    )
                elif self.member_name == "address":
                    self._referenced_declaration_id = AstNodeId(
                        GlobalSymbolsEnum.FUNCTION_ADDRESS
                    )
                else:
                    assert False, f"Unknown function member: {self.member_name}"
            elif isinstance(expr_type, Magic):
                if expr_type.kind == MagicTypeKind.BLOCK:
                    if self.member_name == "basefee":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.BLOCK_BASEFEE
                        )
                    elif self.member_name == "chainid":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.BLOCK_CHAINID
                        )
                    elif self.member_name == "coinbase":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.BLOCK_COINBASE
                        )
                    elif self.member_name == "difficulty":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.BLOCK_DIFFICULTY
                        )
                    elif self.member_name == "gaslimit":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.BLOCK_GASLIMIT
                        )
                    elif self.member_name == "number":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.BLOCK_NUMBER
                        )
                    elif self.member_name == "timestamp":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.BLOCK_TIMESTAMP
                        )
                    else:
                        assert False, f"Unknown block member {self.member_name}"
                elif expr_type.kind == MagicTypeKind.MESSAGE:
                    if self.member_name == "data":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.MSG_DATA
                        )
                    elif self.member_name == "sender":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.MSG_SENDER
                        )
                    elif self.member_name == "sig":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.MSG_SIG
                        )
                    elif self.member_name == "value":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.MSG_VALUE
                        )
                    else:
                        assert False, f"Unknown msg member {self.member_name}"
                elif expr_type.kind == MagicTypeKind.TRANSACTION:
                    if self.member_name == "gasprice":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.TX_GASPRICE
                        )
                    elif self.member_name == "origin":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.TX_ORIGIN
                        )
                    else:
                        assert False, f"Unknown tx member {self.member_name}"
                elif expr_type.kind == MagicTypeKind.ABI:
                    if self.member_name == "decode":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.ABI_DECODE
                        )
                    elif self.member_name == "encode":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.ABI_ENCODE
                        )
                    elif self.member_name == "encodePacked":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.ABI_ENCODE_PACKED
                        )
                    elif self.member_name == "encodeWithSelector":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.ABI_ENCODE_WITH_SELECTOR
                        )
                    elif self.member_name == "encodeWithSignature":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.ABI_ENCODE_WITH_SIGNATURE
                        )
                    elif self.member_name == "encodeCall":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.ABI_ENCODE_CALL
                        )
                    else:
                        assert False, f"Unknown abi member {self.member_name}"
                elif expr_type.kind == MagicTypeKind.META_TYPE:
                    if self.member_name == "name":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.TYPE_NAME
                        )
                    elif self.member_name == "creationCode":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.TYPE_CREATION_CODE
                        )
                    elif self.member_name == "runtimeCode":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.TYPE_RUNTIME_CODE
                        )
                    elif self.member_name == "interfaceId":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.TYPE_INTERFACE_ID
                        )
                    elif self.member_name == "min":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.TYPE_MIN
                        )
                    elif self.member_name == "max":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.TYPE_MAX
                        )
                    else:
                        assert False, f"Unknown type member {self.member_name}"
            elif isinstance(expr_type, Type):
                if isinstance(expr_type.actual_type, Bytes):
                    if self.member_name == "concat":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.BYTES_CONCAT
                        )
                    else:
                        assert False, f"Unknown bytes member {self.member_name}"
                elif isinstance(expr_type.actual_type, String):
                    if self.member_name == "concat":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.STRING_CONCAT
                        )
                    else:
                        assert False, f"Unknown string member {self.member_name}"
                elif isinstance(expr_type.actual_type, UserDefinedValueType):
                    if self.member_name == "wrap":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.USER_DEFINED_VALUE_TYPE_WRAP
                        )
                    elif self.member_name == "unwrap":
                        self._referenced_declaration_id = AstNodeId(
                            GlobalSymbolsEnum.USER_DEFINED_VALUE_TYPE_UNWRAP
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
            global_symbol = GlobalSymbolsEnum(self._referenced_declaration_id)
            self._reference_resolver.register_global_symbol_reference(
                global_symbol, self
            )
            self._reference_resolver.register_destroy_callback(
                self.file, partial(self._destroy, global_symbol)
            )
        else:
            referenced_declaration = self.referenced_declaration
            assert isinstance(referenced_declaration, DeclarationAbc)
            referenced_declaration.register_reference(self)
            self._reference_resolver.register_destroy_callback(
                self.file, partial(self._destroy, referenced_declaration)
            )

    def _destroy(
        self, referenced_declaration: Union[GlobalSymbolsEnum, DeclarationAbc]
    ) -> None:
        if isinstance(referenced_declaration, GlobalSymbolsEnum):
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
        return self._expression

    @property
    def member_name(self) -> str:
        return self._member_name

    @property
    @lru_cache(maxsize=2048)
    def member_byte_location(self) -> Tuple[int, int]:
        relative_expression_end = (
            self._expression.byte_location[1] - self.byte_location[0]
        )
        match = MEMBER_RE.match(self._source[relative_expression_end:])
        assert match
        return self._expression.byte_location[1] + match.start(
            "member"
        ), self._expression.byte_location[1] + match.end("member")

    @property
    def referenced_declaration(self) -> Union[DeclarationAbc, GlobalSymbolsEnum]:
        assert self._referenced_declaration_id is not None
        if self._referenced_declaration_id < 0:
            return GlobalSymbolsEnum(self._referenced_declaration_id)

        node = self._reference_resolver.resolve_node(
            self._referenced_declaration_id, self._cu_hash
        )
        assert isinstance(node, DeclarationAbc)
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
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return self.expression.modifies_state
