from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstNodeId, SolcMemberAccess


class MemberAccess(ExpressionAbc):
    _ast_node: SolcMemberAccess
    _parent: IrAbc  # TODO: make this more specific

    __expression: ExpressionAbc
    __member_name: str
    __referenced_declaration_id: Optional[AstNodeId]

    def __init__(
        self, init: IrInitTuple, member_access: SolcMemberAccess, parent: IrAbc
    ):
        super().__init__(init, member_access, parent)
        self.__expression = ExpressionAbc.from_ast(init, member_access.expression, self)
        self.__member_name = member_access.member_name
        self.__referenced_declaration_id = member_access.referenced_declaration

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def expression(self) -> ExpressionAbc:
        return self.__expression

    @property
    def member_name(self) -> str:
        return self.__member_name

    @property
    def referenced_declaration(self) -> Optional[AstNodeId]:
        return self.__referenced_declaration_id
