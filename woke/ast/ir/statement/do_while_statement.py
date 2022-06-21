from typing import Optional

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcDoWhileStatement


class DoWhileStatement(StatementAbc):
    _ast_node: SolcDoWhileStatement
    _parent: IrAbc  # TODO: make this more specific

    __body: StatementAbc
    __condition: ExpressionAbc
    __documentation: Optional[str]

    def __init__(
        self, init: IrInitTuple, do_while: SolcDoWhileStatement, parent: IrAbc
    ):
        super().__init__(init, do_while, parent)
        self.__body = StatementAbc.from_ast(init, do_while.body, self)
        self.__condition = ExpressionAbc.from_ast(init, do_while.condition, self)
        self.__documentation = do_while.documentation

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def body(self) -> StatementAbc:
        return self.__body

    @property
    def condition(self) -> ExpressionAbc:
        return self.__condition

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation
