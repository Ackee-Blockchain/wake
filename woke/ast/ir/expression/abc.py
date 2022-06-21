from woke.ast.ir.abc import IrAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    SolcAssignment,
    SolcBinaryOperation,
    SolcConditional,
    SolcElementaryTypeNameExpression,
    SolcExpressionUnion,
    SolcFunctionCall,
    SolcFunctionCallOptions,
    SolcIdentifier,
    SolcIndexAccess,
    SolcIndexRangeAccess,
    SolcLiteral,
    SolcMemberAccess,
    SolcNewExpression,
    SolcTupleExpression,
    SolcUnaryOperation,
)


class ExpressionAbc(IrAbc):
    """
    Something that has a value.
    """

    def __init__(
        self, init: IrInitTuple, expression: SolcExpressionUnion, parent: IrAbc
    ):
        super().__init__(init, expression, parent)

    @staticmethod
    def from_ast(
        init: IrInitTuple, expression: SolcExpressionUnion, parent: IrAbc
    ) -> "ExpressionAbc":
        from .assignment import Assignment
        from .binary_operation import BinaryOperation
        from .conditional import Conditional
        from .elementary_type_name_expression import ElementaryTypeNameExpression
        from .function_call import FunctionCall
        from .function_call_options import FunctionCallOptions
        from .identifier import Identifier
        from .index_access import IndexAccess
        from .index_range_access import IndexRangeAccess
        from .literal import Literal
        from .member_access import MemberAccess
        from .new_expression import NewExpression
        from .tuple_expression import TupleExpression
        from .unary_operation import UnaryOperation

        if isinstance(expression, SolcAssignment):
            return Assignment(init, expression, parent)
        elif isinstance(expression, SolcBinaryOperation):
            return BinaryOperation(init, expression, parent)
        elif isinstance(expression, SolcConditional):
            return Conditional(init, expression, parent)
        elif isinstance(expression, SolcElementaryTypeNameExpression):
            return ElementaryTypeNameExpression(init, expression, parent)
        elif isinstance(expression, SolcFunctionCall):
            return FunctionCall(init, expression, parent)
        elif isinstance(expression, SolcFunctionCallOptions):
            return FunctionCallOptions(init, expression, parent)
        elif isinstance(expression, SolcIdentifier):
            return Identifier(init, expression, parent)
        elif isinstance(expression, SolcIndexAccess):
            return IndexAccess(init, expression, parent)
        elif isinstance(expression, SolcIndexRangeAccess):
            return IndexRangeAccess(init, expression, parent)
        elif isinstance(expression, SolcLiteral):
            return Literal(init, expression, parent)
        elif isinstance(expression, SolcMemberAccess):
            return MemberAccess(init, expression, parent)
        elif isinstance(expression, SolcNewExpression):
            return NewExpression(init, expression, parent)
        elif isinstance(expression, SolcTupleExpression):
            return TupleExpression(init, expression, parent)
        elif isinstance(expression, SolcUnaryOperation):
            return UnaryOperation(init, expression, parent)
