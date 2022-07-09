from typing import Optional, Union

from woke.ast.ir.abc import IrAbc
from woke.ast.ir.expression.abc import ExpressionAbc
from woke.ast.ir.statement.abc import StatementAbc
from woke.ast.ir.statement.expression_statement import ExpressionStatement
from woke.ast.ir.statement.variable_declaration_statement import (
    VariableDeclarationStatement,
)
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    SolcExpressionStatement,
    SolcForStatement,
    SolcVariableDeclarationStatement,
)


class ForStatement(StatementAbc):
    _ast_node: SolcForStatement
    _parent: IrAbc  # TODO: make this more specific

    __body: StatementAbc
    __documentation: Optional[str]
    __condition: Optional[ExpressionAbc]
    __initialization_expression: Optional[
        Union[ExpressionStatement, VariableDeclarationStatement]
    ]
    __loop_expression: Optional[ExpressionStatement]

    def __init__(self, init: IrInitTuple, for_: SolcForStatement, parent: IrAbc):
        super().__init__(init, for_, parent)
        self.__body = StatementAbc.from_ast(init, for_.body, self)
        self.__documentation = for_.documentation

        self.__condition = (
            ExpressionAbc.from_ast(init, for_.condition, self)
            if for_.condition
            else None
        )

        if for_.initialization_expression is None:
            self.__initialization_expression = None
        else:
            if isinstance(for_.initialization_expression, SolcExpressionStatement):
                self.__initialization_expression = ExpressionStatement(
                    init, for_.initialization_expression, self
                )
            elif isinstance(
                for_.initialization_expression, SolcVariableDeclarationStatement
            ):
                self.__initialization_expression = VariableDeclarationStatement(
                    init, for_.initialization_expression, self
                )

        self.__loop_expression = (
            ExpressionStatement(init, for_.loop_expression, self)
            if for_.loop_expression
            else None
        )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def body(self) -> StatementAbc:
        return self.__body

    @property
    def documentation(self) -> Optional[str]:
        return self.__documentation

    @property
    def condition(self) -> Optional[ExpressionAbc]:
        return self.__condition

    @property
    def initialization_expression(
        self,
    ) -> Optional[Union[ExpressionStatement, VariableDeclarationStatement]]:
        return self.__initialization_expression

    @property
    def loop_expression(self) -> Optional[ExpressionStatement]:
        return self.__loop_expression
