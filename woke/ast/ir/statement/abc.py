from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterator, Set, Tuple, Union, Optional

from woke.ast.enums import ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import (
    SolcBlock,
    SolcBreak,
    SolcContinue,
    SolcDoWhileStatement,
    SolcEmitStatement,
    SolcExpressionStatement,
    SolcForStatement,
    SolcIfStatement,
    SolcInlineAssembly,
    SolcPlaceholderStatement,
    SolcReturn,
    SolcRevertStatement,
    SolcStatementUnion,
    SolcTryStatement,
    SolcUncheckedBlock,
    SolcVariableDeclarationStatement,
    SolcWhileStatement,
)

if TYPE_CHECKING:
    from ..declaration.function_definition import FunctionDefinition
    from ..declaration.modifier_definition import ModifierDefinition
    from ..meta.try_catch_clause import TryCatchClause
    from .block import Block
    from .do_while_statement import DoWhileStatement
    from .for_statement import ForStatement
    from .if_statement import IfStatement
    from .unchecked_block import UncheckedBlock
    from .while_statement import WhileStatement


class StatementAbc(SolidityAbc, ABC):
    """
    Abstract base class for all Solidity statements.
    """
    _documentation: Optional[str]

    def __init__(
        self, init: IrInitTuple, statement: SolcStatementUnion, parent: SolidityAbc
    ):
        super().__init__(init, statement, parent)
        self._documentation = statement.documentation

    @staticmethod
    def from_ast(
        init: IrInitTuple, statement: SolcStatementUnion, parent: SolidityAbc
    ) -> "StatementAbc":
        from .block import Block
        from .break_statement import Break
        from .continue_statement import Continue
        from .do_while_statement import DoWhileStatement
        from .emit_statement import EmitStatement
        from .expression_statement import ExpressionStatement
        from .for_statement import ForStatement
        from .if_statement import IfStatement
        from .inline_assembly import InlineAssembly
        from .placeholder_statement import PlaceholderStatement
        from .return_statement import Return
        from .revert_statement import RevertStatement
        from .try_statement import TryStatement
        from .unchecked_block import UncheckedBlock
        from .variable_declaration_statement import VariableDeclarationStatement
        from .while_statement import WhileStatement

        if isinstance(statement, SolcBlock):
            return Block(init, statement, parent)
        elif isinstance(statement, SolcBreak):
            return Break(init, statement, parent)
        elif isinstance(statement, SolcContinue):
            return Continue(init, statement, parent)
        elif isinstance(statement, SolcDoWhileStatement):
            return DoWhileStatement(init, statement, parent)
        elif isinstance(statement, SolcEmitStatement):
            return EmitStatement(init, statement, parent)
        elif isinstance(statement, SolcExpressionStatement):
            return ExpressionStatement(init, statement, parent)
        elif isinstance(statement, SolcForStatement):
            return ForStatement(init, statement, parent)
        elif isinstance(statement, SolcIfStatement):
            return IfStatement(init, statement, parent)
        elif isinstance(statement, SolcInlineAssembly):
            return InlineAssembly(init, statement, parent)
        elif isinstance(statement, SolcPlaceholderStatement):
            return PlaceholderStatement(init, statement, parent)
        elif isinstance(statement, SolcReturn):
            return Return(init, statement, parent)
        elif isinstance(statement, SolcRevertStatement):
            return RevertStatement(init, statement, parent)
        elif isinstance(statement, SolcTryStatement):
            return TryStatement(init, statement, parent)
        elif isinstance(statement, SolcUncheckedBlock):
            return UncheckedBlock(init, statement, parent)
        elif isinstance(statement, SolcVariableDeclarationStatement):
            return VariableDeclarationStatement(init, statement, parent)
        elif isinstance(statement, SolcWhileStatement):
            return WhileStatement(init, statement, parent)
        assert False, f"Unknown statement type: {type(statement)}"

    @property
    @abstractmethod
    def parent(
        self,
    ) -> Union[
        Block,
        DoWhileStatement,
        ForStatement,
        IfStatement,
        UncheckedBlock,
        WhileStatement,
        FunctionDefinition,
        ModifierDefinition,
        TryCatchClause,
    ]:
        """
        Returns:
            Parent node of the statement.
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

    def statements_iter(self) -> Iterator[StatementAbc]:
        """
        Yields:
            Child statements of the statement (recursively) including `self`.
        """
        yield self

    @property
    def documentation(self) -> Optional[str]:
        """
        Statement documentation strings should be placed above the statement.
        Returns:
            [NatSpec](https://docs.soliditylang.org/en/latest/natspec-format.html) documentation string, if any.
        """
        return self._documentation
