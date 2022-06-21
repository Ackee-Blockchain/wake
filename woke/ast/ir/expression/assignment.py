from woke.ast.enums import AssignmentOperator
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcAssignment

from .abc import ExpressionAbc


class Assignment(ExpressionAbc):
    _ast_node: SolcAssignment
    _parent: IrAbc  # TODO: make this more specific

    __left_expression: ExpressionAbc
    __right_expression: ExpressionAbc
    __operator: AssignmentOperator

    def __init__(self, init: IrInitTuple, assignment: SolcAssignment, parent: IrAbc):
        super().__init__(init, assignment, parent)
        self.__operator = assignment.operator
        self.__left_expression = ExpressionAbc.from_ast(
            init, assignment.left_hand_side, self
        )
        self.__right_expression = ExpressionAbc.from_ast(
            init, assignment.right_hand_side, self
        )

    @property
    def parent(self) -> IrAbc:
        return self._parent

    @property
    def left_expression(self) -> ExpressionAbc:
        return self.__left_expression

    @property
    def right_expression(self) -> ExpressionAbc:
        return self.__right_expression

    @property
    def operator(self) -> AssignmentOperator:
        return self.__operator
