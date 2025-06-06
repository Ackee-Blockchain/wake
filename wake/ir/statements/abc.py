from __future__ import annotations

import weakref
from abc import ABC
from typing import TYPE_CHECKING, Iterator, Optional, Union

from wake.ir.abc import SolidityAbc, is_not_none
from wake.ir.ast import (
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
from wake.ir.utils import IrInitTuple

if TYPE_CHECKING:
    from ..declarations.function_definition import FunctionDefinition
    from ..declarations.modifier_definition import ModifierDefinition
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
    _declaration_cache: weakref.ReferenceType[
        Union[FunctionDefinition, ModifierDefinition]
    ]

    def __init__(
        self, init: IrInitTuple, statement: SolcStatementUnion, parent: SolidityAbc
    ):
        super().__init__(init, statement, parent)
        self._documentation = statement.documentation

    @classmethod
    def _strip_weakrefs(cls, state: dict):
        super()._strip_weakrefs(state)
        state.pop("_declaration_cache", None)

    @staticmethod
    def from_ast(
        init: IrInitTuple, statement: SolcStatementUnion, parent: SolidityAbc
    ) -> StatementAbc:
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
        return super().parent

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

    @property
    def declaration(self) -> Union[FunctionDefinition, ModifierDefinition]:
        """
        Returns:
            [FunctionDefinition][wake.ir.declarations.function_definition.FunctionDefinition] or [ModifierDefinition][wake.ir.declarations.modifier_definition.ModifierDefinition] that contains the statement.
        """
        if not hasattr(self, "_declaration_cache"):
            from ..declarations.function_definition import FunctionDefinition
            from ..declarations.modifier_definition import ModifierDefinition

            node = self
            while node is not None:
                if isinstance(node, (FunctionDefinition, ModifierDefinition)):
                    self._declaration_cache = weakref.ref(node)
                    return node
                node = node.parent
            assert (
                False
            ), f"Statement {self.source} is not part of a function or modifier"
        else:
            return is_not_none(self._declaration_cache())
