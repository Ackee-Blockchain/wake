from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx

from woke.core import get_logger
from woke.ir import (
    Block,
    Break,
    Conditional,
    Continue,
    DoWhileStatement,
    ExpressionAbc,
    ExpressionStatement,
    ForStatement,
    FunctionCall,
    FunctionDefinition,
    IfStatement,
    InlineAssembly,
    ModifierDefinition,
    Return,
    RevertStatement,
    StatementAbc,
    TryStatement,
    UncheckedBlock,
    WhileStatement,
    YulBlock,
    YulBreak,
    YulCase,
    YulContinue,
    YulExpressionStatement,
    YulForLoop,
    YulFunctionCall,
    YulFunctionDefinition,
    YulIf,
    YulLeave,
    YulStatementAbc,
    YulSwitch,
)
from woke.ir.enums import GlobalSymbol
from woke.utils import StrEnum

logger = get_logger(__name__)

# pyright: reportGeneralTypeIssues=false
# pyright: reportOptionalSubscript=false


class TransitionCondition(StrEnum):
    IS_TRUE = "is true"
    IS_FALSE = "is false"
    ALWAYS = "always"
    NEVER = "never"
    TRY_SUCCEEDED = "try succeeded"
    TRY_REVERTED = "try reverted"
    TRY_PANICKED = "try panicked"
    TRY_FAILED = "try failed"
    SWITCH_MATCHED = "switch matched"
    SWITCH_DEFAULT = "switch default"


class ControlFlowGraph:
    __graph: nx.DiGraph
    __declaration: Union[FunctionDefinition, ModifierDefinition, YulFunctionDefinition]
    __statements_lookup: Dict[Union[StatementAbc, YulStatementAbc], CfgBlock]
    __start_block: CfgBlock
    __success_end_block: CfgBlock
    __revert_end_block: CfgBlock

    def __init__(
        self,
        declaration: Union[
            FunctionDefinition, ModifierDefinition, YulFunctionDefinition
        ],
    ):
        if declaration.body is None:
            raise ValueError("Function body is None.")
        self.__declaration = declaration

        self.__graph = nx.DiGraph()
        self.__start_block = CfgBlock()
        self.__graph.add_node(self.__start_block)
        next_block = CfgBlock()
        self.__graph.add_node(next_block)
        self.__graph.add_edge(
            self.__start_block, next_block, condition=(TransitionCondition.ALWAYS, None)
        )
        self.__success_end_block = CfgBlock()
        self.__graph.add_node(self.__success_end_block)
        self.__revert_end_block = CfgBlock()
        self.__graph.add_node(self.__revert_end_block)

        tmp = CfgBlock.from_statement(
            self.__graph,
            next_block,
            self.__success_end_block,
            self.__revert_end_block,
            None,
            None,
            declaration.body,
        )
        self.__graph.add_edge(
            tmp, self.__success_end_block, condition=(TransitionCondition.ALWAYS, None)
        )

        while _normalize(
            self.__graph,
            self.__start_block,
            self.__success_end_block,
            self.__revert_end_block,
        ):
            pass

        self.__statements_lookup = {
            stmt: block for block in self.__graph.nodes for stmt in block.statements
        }
        for node in self.__graph.nodes:
            for stmt in node.statements:
                self.__statements_lookup[stmt] = node
            if node.control_statement is not None:
                self.__statements_lookup[node.control_statement] = node

    @property
    def graph(self) -> nx.DiGraph:
        return self.__graph.copy(as_view=True)

    @property
    def declaration(
        self,
    ) -> Union[FunctionDefinition, ModifierDefinition, YulFunctionDefinition]:
        return self.__declaration

    @property
    def start_block(self) -> CfgBlock:
        """
        Start block is guaranteed to be empty, i.e. it has no statements.
        """
        return self.__start_block

    @property
    def success_end_block(self) -> CfgBlock:
        """
        End block is guaranteed to be empty, i.e. it has no statements.
        """
        return self.__success_end_block

    @property
    def revert_end_block(self) -> CfgBlock:
        """
        End block is guaranteed to be empty, i.e. it has no statements.
        """
        return self.__revert_end_block

    def get_cfg_block(
        self, statement: Union[StatementAbc, YulStatementAbc]
    ) -> CfgBlock:
        return self.__statements_lookup[statement]

    def is_reachable(
        self,
        start: Union[StatementAbc, YulStatementAbc],
        end: Union[StatementAbc, YulStatementAbc],
    ) -> bool:
        start_block = self.__statements_lookup[start]
        end_block = self.__statements_lookup[end]
        if start_block == end_block:
            if end == end_block.control_statement:
                return True
            start_index = start_block.statements.index(start)
            end_index = end_block.statements.index(end)
            if start_index <= end_index:  # also EQUAL?
                return True
            try:
                nx.find_cycle(self.__graph, start_block)
                return True
            except nx.NetworkXNoCycle:
                return False
        else:
            return nx.has_path(self.__graph, start_block, end_block)


def _normalize(
    graph: nx.DiGraph, start: CfgBlock, success_end: CfgBlock, revert_end: CfgBlock
) -> bool:
    changed = False
    to_be_removed = set()

    for node in graph.nodes:
        for out_edge in list(graph.out_edges(node, data=True)):
            if out_edge[2]["condition"][0] == TransitionCondition.NEVER:
                graph.remove_edge(out_edge[0], out_edge[1])
                changed = True

        if (
            len(node.statements) == 0
            and len(graph.out_edges(node)) == 1
            and node != start
        ):
            edge = next(iter(graph.out_edges(node, data=True)))
            if edge[2]["condition"][0] == TransitionCondition.ALWAYS:
                to = edge[1]
                in_edges = list(graph.in_edges(node, data=True))
                for from_, _, data in in_edges:
                    graph.add_edge(from_, to, condition=data["condition"])
                    graph.remove_edge(from_, node)
                to_be_removed.add(node)
                changed = True

        if (
            len(node.statements) == 0
            and len(graph.in_edges(node)) == 0
            and node not in {start, success_end, revert_end}
        ):
            to_be_removed.add(node)
            changed = True
            for edge in list(graph.out_edges(node)):
                graph.remove_edge(edge[0], edge[1])

    for node in to_be_removed:
        graph.remove_node(node)

    return changed


class CfgBlock:
    __id_counter: int = 0
    __id: int
    __statements: List[Union[StatementAbc, YulStatementAbc]]
    # control statement is always the last statement
    __control_statement: Optional[
        Union[
            DoWhileStatement,
            ForStatement,
            IfStatement,
            TryStatement,
            WhileStatement,
            YulForLoop,
            YulIf,
            YulSwitch,
        ]
    ]

    def __init__(self):
        self.__id = self.__class__.__id_counter
        self.__class__.__id_counter += 1
        self.__statements = []
        self.__control_statement = None

    def __str__(self):
        return (
            "\n".join(statement.source for statement in self.statements)
            if len(self.statements) > 0
            else ""
        )

    @property
    def id(self) -> int:
        return self.__id

    @property
    def statements(self) -> Tuple[Union[StatementAbc, YulStatementAbc], ...]:
        return tuple(self.__statements)

    @property
    def control_statement(
        self,
    ) -> Optional[
        Union[
            DoWhileStatement,
            ForStatement,
            IfStatement,
            TryStatement,
            WhileStatement,
            YulForLoop,
            YulIf,
            YulSwitch,
        ]
    ]:
        return self.__control_statement

    @classmethod
    def from_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        loop_body_post: Optional[CfgBlock],
        loop_body_next: Optional[CfgBlock],
        statement: Union[StatementAbc, YulStatementAbc],
    ) -> CfgBlock:
        if isinstance(statement, (Block, UncheckedBlock, YulBlock)):
            for body_statement in statement.statements:
                prev = cls.from_statement(
                    graph,
                    prev,
                    success_end,
                    revert_end,
                    loop_body_post,
                    loop_body_next,
                    body_statement,
                )
            return prev
        elif isinstance(statement, InlineAssembly):
            return cls.from_statement(
                graph,
                prev,
                success_end,
                revert_end,
                loop_body_post,
                loop_body_next,
                statement.yul_block,
            )
        elif (
            isinstance(statement, YulExpressionStatement)
            and isinstance(statement.expression, YulFunctionCall)
            and statement.expression.function_name.name == "revert"
        ):
            prev.__statements.append(statement)
            next = CfgBlock()
            graph.add_node(next)
            graph.add_edge(
                prev, revert_end, condition=(TransitionCondition.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
            return next
        elif isinstance(statement, (Break, YulBreak)):
            prev.__statements.append(statement)
            next = CfgBlock()
            assert loop_body_next is not None
            graph.add_node(next)
            graph.add_edge(
                prev, loop_body_next, condition=(TransitionCondition.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
            return next
        elif isinstance(statement, (Continue, YulContinue)):
            prev.__statements.append(statement)
            next = CfgBlock()
            assert loop_body_post is not None
            graph.add_node(next)
            graph.add_edge(
                prev, loop_body_post, condition=(TransitionCondition.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
            return next
        elif isinstance(statement, DoWhileStatement):
            return cls.from_do_while_statement(
                graph, prev, success_end, revert_end, statement
            )
        elif isinstance(statement, ForStatement):
            return cls.from_for_statement(
                graph, prev, success_end, revert_end, statement
            )
        elif isinstance(statement, IfStatement):
            return cls.from_if_statement(
                graph,
                prev,
                success_end,
                revert_end,
                loop_body_post,
                loop_body_next,
                statement,
            )
        elif isinstance(statement, (Return, YulLeave)):
            prev.__statements.append(statement)
            next = CfgBlock()
            graph.add_node(next)
            graph.add_edge(
                prev, success_end, condition=(TransitionCondition.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
            return next
        elif isinstance(statement, RevertStatement):
            prev.__statements.append(statement)
            next = CfgBlock()
            graph.add_node(next)
            graph.add_edge(
                prev, revert_end, condition=(TransitionCondition.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionCondition.NEVER, None))
            return next
        elif isinstance(statement, ExpressionStatement):

            def process_expression(expression: ExpressionAbc, block: CfgBlock) -> bool:
                if isinstance(expression, Conditional):
                    true_block = CfgBlock()
                    graph.add_node(true_block)
                    false_block = CfgBlock()
                    graph.add_node(false_block)

                    graph.add_edge(
                        block,
                        true_block,
                        condition=(TransitionCondition.IS_TRUE, expression.condition),
                    )
                    graph.add_edge(
                        block,
                        false_block,
                        condition=(TransitionCondition.IS_FALSE, expression.condition),
                    )

                    true_is_control = process_expression(
                        expression.true_expression, true_block
                    )
                    false_is_control = process_expression(
                        expression.false_expression, false_block
                    )

                    if not true_is_control:
                        graph.remove_node(true_block)
                        if false_is_control:
                            graph.add_edge(
                                block,
                                next,
                                condition=(
                                    TransitionCondition.IS_TRUE,
                                    expression.condition,
                                ),
                            )

                    if not false_is_control:
                        graph.remove_node(false_block)
                        if true_is_control:
                            graph.add_edge(
                                block,
                                next,
                                condition=(
                                    TransitionCondition.IS_FALSE,
                                    expression.condition,
                                ),
                            )

                    return true_is_control or false_is_control
                elif isinstance(expression, FunctionCall):
                    func_called = expression.function_called
                    if func_called == GlobalSymbol.REVERT:
                        graph.add_edge(
                            block,
                            revert_end,
                            condition=(TransitionCondition.ALWAYS, None),
                        )
                        graph.add_edge(
                            block, next, condition=(TransitionCondition.NEVER, None)
                        )
                        return True
                    elif func_called in {
                        GlobalSymbol.REQUIRE,
                        GlobalSymbol.ASSERT,
                    }:
                        graph.add_edge(
                            block,
                            next,
                            condition=(
                                TransitionCondition.IS_TRUE,
                                expression.arguments[0],
                            ),
                        )
                        graph.add_edge(
                            block,
                            revert_end,
                            condition=(
                                TransitionCondition.IS_FALSE,
                                expression.arguments[0],
                            ),
                        )
                        return True
                    else:
                        return False

            prev.__statements.append(statement)
            next = CfgBlock()
            graph.add_node(next)

            if process_expression(statement.expression, prev):
                return next
            else:
                graph.remove_node(next)
                return prev
        elif isinstance(statement, TryStatement):
            return cls.from_try_statement(
                graph,
                prev,
                success_end,
                revert_end,
                loop_body_post,
                loop_body_next,
                statement,
            )
        elif isinstance(statement, WhileStatement):
            return cls.from_while_statement(
                graph, prev, success_end, revert_end, statement
            )
        elif isinstance(statement, YulCase):
            raise NotImplementedError()  # should be handled by YulSwitch
        elif isinstance(statement, YulForLoop):
            return cls.from_yul_for_loop(
                graph, prev, success_end, revert_end, statement
            )
        elif isinstance(statement, YulIf):
            return cls.from_yul_if(
                graph,
                prev,
                success_end,
                revert_end,
                loop_body_post,
                loop_body_next,
                statement,
            )
        elif isinstance(statement, YulSwitch):
            return cls.from_yul_switch(graph, prev, success_end, revert_end, statement)
        else:
            prev.__statements.append(statement)
            return prev

    @classmethod
    def from_if_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        loop_body_post: Optional[CfgBlock],
        loop_body_next: Optional[CfgBlock],
        if_statement: IfStatement,
    ) -> CfgBlock:
        assert prev.__control_statement is None
        prev.__control_statement = if_statement
        true_block = CfgBlock()
        graph.add_node(true_block)
        true_block_end = cls.from_statement(
            graph,
            true_block,
            success_end,
            revert_end,
            loop_body_post,
            loop_body_next,
            if_statement.true_body,
        )

        false_block = CfgBlock()
        graph.add_node(false_block)

        if if_statement.false_body is None:
            false_block_end = false_block
        else:
            false_block_end = cls.from_statement(
                graph,
                false_block,
                success_end,
                revert_end,
                loop_body_post,
                loop_body_next,
                if_statement.false_body,
            )

        next = CfgBlock()
        graph.add_node(next)
        graph.add_edge(
            prev,
            true_block,
            condition=(TransitionCondition.IS_TRUE, if_statement.condition),
        )
        graph.add_edge(
            prev,
            false_block,
            condition=(TransitionCondition.IS_FALSE, if_statement.condition),
        )
        graph.add_edge(
            true_block_end, next, condition=(TransitionCondition.ALWAYS, None)
        )
        graph.add_edge(
            false_block_end, next, condition=(TransitionCondition.ALWAYS, None)
        )
        return next

    @classmethod
    def from_yul_if(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        loop_body_post: Optional[CfgBlock],
        loop_body_next: Optional[CfgBlock],
        if_statement: YulIf,
    ):
        assert prev.__control_statement is None
        prev.__control_statement = if_statement
        true_block = CfgBlock()
        graph.add_node(true_block)
        true_block_end = cls.from_statement(
            graph,
            true_block,
            success_end,
            revert_end,
            loop_body_post,
            loop_body_next,
            if_statement.body,
        )
        next = CfgBlock()
        graph.add_node(next)
        graph.add_edge(
            prev,
            true_block,
            condition=(TransitionCondition.IS_TRUE, if_statement.condition),
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionCondition.IS_FALSE, if_statement.condition),
        )
        graph.add_edge(
            true_block_end, next, condition=(TransitionCondition.ALWAYS, None)
        )
        return next

    @classmethod
    def from_do_while_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        do_while_statement: DoWhileStatement,
    ) -> CfgBlock:
        body = CfgBlock()
        graph.add_node(body)
        next = CfgBlock()
        graph.add_node(next)
        body_end = cls.from_statement(
            graph, body, success_end, revert_end, body, next, do_while_statement.body
        )
        assert body_end.__control_statement is None
        body_end.__control_statement = do_while_statement

        graph.add_edge(prev, body, condition=(TransitionCondition.ALWAYS, None))
        graph.add_edge(
            body_end,
            next,
            condition=(TransitionCondition.IS_FALSE, do_while_statement.condition),
        )
        graph.add_edge(
            body_end,
            body,
            condition=(TransitionCondition.IS_TRUE, do_while_statement.condition),
        )
        return next

    @classmethod
    def from_for_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        for_statement: ForStatement,
    ) -> CfgBlock:
        if for_statement.initialization_expression is not None:
            prev = cls.from_statement(
                graph,
                prev,
                success_end,
                revert_end,
                None,
                None,
                for_statement.initialization_expression,
            )
        assert prev.__control_statement is None
        prev.__control_statement = for_statement

        body = CfgBlock()
        graph.add_node(body)
        next = CfgBlock()
        graph.add_node(next)
        loop_post = CfgBlock()
        graph.add_node(loop_post)
        if for_statement.loop_expression is not None:
            loop_post_end = cls.from_statement(
                graph,
                loop_post,
                success_end,
                revert_end,
                loop_post,
                next,
                for_statement.loop_expression,
            )
        else:
            loop_post_end = loop_post
        body_end = cls.from_statement(
            graph, body, success_end, revert_end, loop_post, next, for_statement.body
        )

        graph.add_edge(
            body_end, loop_post, condition=(TransitionCondition.ALWAYS, None)
        )
        graph.add_edge(
            prev, body, condition=(TransitionCondition.IS_TRUE, for_statement.condition)
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionCondition.IS_FALSE, for_statement.condition),
        )
        graph.add_edge(
            loop_post_end,
            body,
            condition=(TransitionCondition.IS_TRUE, for_statement.condition),
        )
        graph.add_edge(
            loop_post_end,
            next,
            condition=(TransitionCondition.IS_FALSE, for_statement.condition),
        )
        return next

    @classmethod
    def from_yul_for_loop(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        for_loop: YulForLoop,
    ) -> CfgBlock:
        assert prev.__control_statement is None
        prev = cls.from_statement(
            graph, prev, success_end, revert_end, None, None, for_loop.pre
        )
        assert prev.__control_statement is None
        prev.__control_statement = for_loop

        body = CfgBlock()
        graph.add_node(body)
        next = CfgBlock()
        graph.add_node(next)
        loop_post = CfgBlock()
        graph.add_node(loop_post)
        body_end = cls.from_statement(
            graph, body, success_end, revert_end, loop_post, next, for_loop.body
        )
        loop_post_end = cls.from_statement(
            graph, loop_post, success_end, revert_end, loop_post, next, for_loop.post
        )

        graph.add_edge(
            body_end, loop_post, condition=(TransitionCondition.ALWAYS, None)
        )
        graph.add_edge(
            prev, body, condition=(TransitionCondition.IS_TRUE, for_loop.condition)
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionCondition.IS_FALSE, for_loop.condition),
        )
        graph.add_edge(
            loop_post_end,
            body,
            condition=(TransitionCondition.IS_TRUE, for_loop.condition),
        )
        graph.add_edge(
            loop_post_end,
            next,
            condition=(TransitionCondition.IS_FALSE, for_loop.condition),
        )
        return next

    @classmethod
    def from_try_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        loop_body_post: Optional[CfgBlock],
        loop_body_next: Optional[CfgBlock],
        try_statement: TryStatement,
    ) -> CfgBlock:
        assert prev.__control_statement is None
        prev.__control_statement = try_statement

        success_block = CfgBlock()
        graph.add_node(success_block)
        success_block_end = cls.from_statement(
            graph,
            success_block,
            success_end,
            revert_end,
            loop_body_post,
            loop_body_next,
            try_statement.clauses[0].block,
        )

        revert_block = None
        revert_block_end = None
        panic_block = None
        panic_block_end = None
        fail_block = None
        fail_block_end = None
        for clause in try_statement.clauses[1:]:
            if clause.error_name == "Error":
                revert_block = CfgBlock()
                graph.add_node(revert_block)
                revert_block_end = cls.from_statement(
                    graph,
                    revert_block,
                    success_end,
                    revert_end,
                    loop_body_post,
                    loop_body_next,
                    clause.block,
                )
            elif clause.error_name == "Panic":
                panic_block = CfgBlock()
                graph.add_node(panic_block)
                panic_block_end = cls.from_statement(
                    graph,
                    panic_block,
                    success_end,
                    revert_end,
                    loop_body_post,
                    loop_body_next,
                    clause.block,
                )
            elif clause.error_name == "":
                fail_block = CfgBlock()
                graph.add_node(fail_block)
                fail_block_end = cls.from_statement(
                    graph,
                    fail_block,
                    success_end,
                    revert_end,
                    loop_body_post,
                    loop_body_next,
                    clause.block,
                )
            else:
                raise NotImplementedError(f"Unknown error name: {clause.error_name}")

        next = CfgBlock()
        graph.add_node(next)

        graph.add_edge(
            prev,
            success_block,
            condition=(TransitionCondition.TRY_SUCCEEDED, try_statement.external_call),
        )
        graph.add_edge(
            success_block_end, next, condition=(TransitionCondition.ALWAYS, None)
        )
        if revert_block is not None:
            graph.add_edge(
                prev,
                revert_block,
                condition=(
                    TransitionCondition.TRY_REVERTED,
                    try_statement.external_call,
                ),
            )
            graph.add_edge(
                revert_block_end, next, condition=(TransitionCondition.ALWAYS, None)
            )
        if panic_block is not None:
            graph.add_edge(
                prev,
                panic_block,
                condition=(
                    TransitionCondition.TRY_PANICKED,
                    try_statement.external_call,
                ),
            )
            graph.add_edge(
                panic_block_end, next, condition=(TransitionCondition.ALWAYS, None)
            )
        if fail_block is not None:
            graph.add_edge(
                prev,
                fail_block,
                condition=(TransitionCondition.TRY_FAILED, try_statement.external_call),
            )
            graph.add_edge(
                fail_block_end, next, condition=(TransitionCondition.ALWAYS, None)
            )
        else:
            graph.add_edge(
                prev,
                revert_end,
                condition=(TransitionCondition.TRY_FAILED, try_statement.external_call),
            )
        return next

    @classmethod
    def from_yul_switch(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        switch: YulSwitch,
    ) -> CfgBlock:
        assert prev.__control_statement is None
        prev.__control_statement = switch

        next = CfgBlock()
        graph.add_node(next)

        for case_statement in switch.cases:
            case_block = CfgBlock()
            graph.add_node(case_block)
            graph.add_edge(
                prev,
                case_block,
                condition=(TransitionCondition.SWITCH_MATCHED, case_statement.value)
                if case_statement.value != "default"
                else (TransitionCondition.SWITCH_DEFAULT, None),
            )
            case_block_end = cls.from_statement(
                graph,
                case_block,
                success_end,
                revert_end,
                case_block,
                next,
                case_statement.body,
            )
            graph.add_edge(
                case_block_end, next, condition=(TransitionCondition.ALWAYS, None)
            )

        if not any(case.value == "default" for case in switch.cases):
            graph.add_edge(
                prev,
                next,
                condition=(TransitionCondition.SWITCH_DEFAULT, None),
            )

        return next

    @classmethod
    def from_while_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgBlock,
        success_end: CfgBlock,
        revert_end: CfgBlock,
        while_statement: WhileStatement,
    ) -> CfgBlock:
        assert prev.__control_statement is None
        prev.__control_statement = while_statement

        body = CfgBlock()
        graph.add_node(body)
        next = CfgBlock()
        graph.add_node(next)
        body_end = cls.from_statement(
            graph, body, success_end, revert_end, body, next, while_statement.body
        )

        graph.add_edge(
            prev,
            body,
            condition=(TransitionCondition.IS_TRUE, while_statement.condition),
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionCondition.IS_FALSE, while_statement.condition),
        )
        graph.add_edge(
            body_end,
            body,
            condition=(TransitionCondition.IS_TRUE, while_statement.condition),
        )
        graph.add_edge(
            body_end,
            next,
            condition=(TransitionCondition.IS_FALSE, while_statement.condition),
        )
        return next
