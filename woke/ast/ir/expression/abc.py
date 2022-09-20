import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Optional, Set, Tuple

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
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
    TypeDescriptionsModel,
)
from woke.ast.types import TypeAbc
from woke.utils.string import StringReader

logger = logging.getLogger(__name__)


class ExpressionAbc(SolidityAbc, ABC):
    """
    Abstract base class for all IR expression nodes.
    > Something that has a value.
    """

    _type_descriptions: TypeDescriptionsModel

    def __init__(
        self, init: IrInitTuple, expression: SolcExpressionUnion, parent: SolidityAbc
    ):
        super().__init__(init, expression, parent)
        self._type_descriptions = expression.type_descriptions

    @staticmethod
    def from_ast(
        init: IrInitTuple, expression: SolcExpressionUnion, parent: SolidityAbc
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

    @property
    @lru_cache(maxsize=2048)
    def type(self) -> Optional[TypeAbc]:
        """
        Can be `None` in case of an [Identifier][woke.ast.ir.expression.identifier.Identifier] in an [ImportDirective][woke.ast.ir.meta.import_directive.ImportDirective].
        !!! example
            `Ownable` in the following example has no type information:
            ```solidity
            import { Ownable } from './Ownable.sol';
            ```
        Returns:
            Type of the expression.
        """
        if self._type_descriptions.type_identifier is None:
            return None

        type_identifier = StringReader(self._type_descriptions.type_identifier)
        ret = TypeAbc.from_type_identifier(
            type_identifier, self._reference_resolver, self.cu_hash
        )
        assert (
            len(type_identifier) == 0
        ), f"Failed to parse type_identifier: {self._type_descriptions.type_identifier}"
        return ret

    @property
    def type_string(self) -> Optional[str]:
        """
        !!! example
            `:::solidity function (uint256,uint256) returns (uint256)` in the case of the `foo` [Identifier][woke.ast.ir.expression.identifier.Identifier] in the `:::solidity foo(1, 2)` expression for the following function:
            ```solidity
            function foo(uint a, uint b) public onlyOwner payable virtual onlyOwner returns(uint) {
                return a + b;
            }
            ```

        Can be `None` in case of an [Identifier][woke.ast.ir.expression.identifier.Identifier] in an [ImportDirective][woke.ast.ir.meta.import_directive.ImportDirective].
        !!! example
            `Ownable` in the following example has no type information:
            ```solidity
            import { Ownable } from './Ownable.sol';
            ```
        Returns:
            User-friendly string describing the expression type.
        """
        return self._type_descriptions.type_string

    @property
    @abstractmethod
    def is_ref_to_state_variable(self) -> bool:
        """
        In many cases it may be useful to know if an [Assignment][woke.ast.ir.expression.assignment.Assignment] to an expression modifies a state variable or not.
        This may not be straightforward to determine, e.g. if the expression is a [MemberAccess][woke.ast.ir.expression.member_access.MemberAccess] or [IndexAccess][woke.ast.ir.expression.index_access.IndexAccess] to a state variable.
        Returns:
            `True` if the expression (possibly) is a reference to a state variable.
        """
        ...

    @property
    @abstractmethod
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        """
        Returns:
            Set of child IR nodes (including `self`) that modify the blockchain state and flags describing how the state is modified.
        """
        ...
