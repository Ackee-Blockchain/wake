from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union

import networkx as nx

from wake.core import get_logger
from wake.ir import (
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
from wake.ir.enums import GlobalSymbol
from wake.utils import StrEnum

logger = get_logger(__name__)

# pyright: reportGeneralTypeIssues=false
# pyright: reportOptionalSubscript=false


class TransitionConditionKind(StrEnum):
    IS_TRUE = "is true"
    """
    Associated expression evaluates to true.
    """
    IS_FALSE = "is false"
    """
    Associated expression evaluates to false.
    """
    ALWAYS = "always"
    """
    Transition is always taken.
    """
    NEVER = "never"
    """
    Transition is never taken.
    """
    TRY_SUCCEEDED = "try succeeded"
    """
    Try call succeeded.
    """
    TRY_REVERTED = "try reverted"
    """
    Try call reverted with a string reason.
    """
    TRY_PANICKED = "try panicked"
    """
    Try call panicked with an uint256 error code.
    """
    TRY_FAILED = "try failed"
    """
    Try call failed with a bytes memory reason.
    """
    SWITCH_MATCHED = "switch matched"
    """
    Yul switch case value matched the switch expression.
    """
    SWITCH_DEFAULT = "switch default"
    """
    None of the Yul switch case values matched the switch expression.
    """


class ControlFlowGraph:
    """
    Control flow graph for a function or a modifier. Uses NetworkX [DiGraph](https://networkx.org/documentation/stable/reference/classes/digraph.html) as the underlying data structure.

    Holds the following invariants:

    - all nodes are of [CfgNode][wake.analysis.cfg.CfgNode] type,
    - [start_node][wake.analysis.cfg.ControlFlowGraph.start_node], [success_end_node][wake.analysis.cfg.ControlFlowGraph.success_end_node] and [revert_end_node][wake.analysis.cfg.ControlFlowGraph.revert_end_node] are always present and empty (i.e. they contain no statements),
    - all edges have a `condition` attribute holding a 2-item tuple:
        - the first item is a [TransitionConditionKind][wake.analysis.cfg.TransitionConditionKind] enum value,
        - the second item is an optional [ExpressionAbc][wake.ir.expressions.abc.ExpressionAbc] instance.

    !!! tip
        The [Tools for Solidity](https://marketplace.visualstudio.com/items?itemName=AckeeBlockchain.tools-for-solidity) VS Code extension provides a visualizer for CFGs.
        The visualized CFGs are stripped of empty nodes, so they may slightly differ from the CFGs constructed by this class.
    """

    _graph: nx.DiGraph
    _declaration: Union[FunctionDefinition, ModifierDefinition, YulFunctionDefinition]
    _statements_lookup: Dict[Union[StatementAbc, YulStatementAbc], CfgNode]
    _start_node: CfgNode
    _success_end_node: CfgNode
    _revert_end_node: CfgNode

    def __init__(
        self,
        declaration: Union[
            FunctionDefinition, ModifierDefinition, YulFunctionDefinition
        ],
    ):
        if declaration.body is None:
            raise ValueError("Function body is None.")
        self._declaration = declaration

        self._graph = nx.DiGraph()
        self._start_node = CfgNode()
        self._graph.add_node(self._start_node)
        next_node = CfgNode()
        self._graph.add_node(next_node)
        self._graph.add_edge(
            self._start_node,
            next_node,
            condition=(TransitionConditionKind.ALWAYS, None),
        )
        self._success_end_node = CfgNode()
        self._graph.add_node(self._success_end_node)
        self._revert_end_node = CfgNode()
        self._graph.add_node(self._revert_end_node)

        tmp = CfgNode.from_statement(
            self._graph,
            next_node,
            self._success_end_node,
            self._revert_end_node,
            None,
            None,
            declaration.body,
        )
        self._graph.add_edge(
            tmp,
            self._success_end_node,
            condition=(TransitionConditionKind.ALWAYS, None),
        )

        while _normalize(
            self._graph,
            self._start_node,
            self._success_end_node,
            self._revert_end_node,
        ):
            pass

        self._statements_lookup = {
            stmt: node for node in self._graph.nodes for stmt in node.statements
        }
        for node in self._graph.nodes:
            for stmt in node.statements:
                self._statements_lookup[stmt] = node
            if node.control_statement is not None:
                self._statements_lookup[node.control_statement] = node

    @property
    def graph(self) -> nx.DiGraph:
        """
        Returns:
            Read-only view of the underlying NetworkX DiGraph.
        """
        return self._graph.copy(as_view=True)

    @property
    def declaration(
        self,
    ) -> Union[FunctionDefinition, ModifierDefinition, YulFunctionDefinition]:
        """
        Returns:
            Function or modifier definition for which this CFG was constructed.
        """
        return self._declaration

    @property
    def start_node(self) -> CfgNode:
        """
        Start node is guaranteed to be empty, i.e. it has no statements.

        Returns:
            Start node of this CFG, i.e. the node that is always executed first.
        """
        return self._start_node

    @property
    def success_end_node(self) -> CfgNode:
        """
        Success end node is guaranteed to be empty, i.e. it has no statements.

        Returns:
            Success end node of this CFG, i.e. the node that is always executed last if the function or modifier does not revert.
        """
        return self._success_end_node

    @property
    def revert_end_node(self) -> CfgNode:
        """
        Revert end node is guaranteed to be empty, i.e. it has no statements.

        Returns:
            Revert end node of this CFG, signaling that the function or modifier reverted under some condition.
        """
        return self._revert_end_node

    def get_cfg_node(self, statement: Union[StatementAbc, YulStatementAbc]) -> CfgNode:
        """
        Raises:
            KeyError: If the given statement is not contained in this CFG or if the statement is of the
                [Block][wake.ir.statements.block.Block], [UncheckedBlock][wake.ir.statements.unchecked_block.UncheckedBlock],
                [YulBlock][wake.ir.yul.block.YulBlock] or [InlineAssembly][wake.ir.statements.inline_assembly.InlineAssembly] type.


        [Block][wake.ir.statements.block.Block], [UncheckedBlock][wake.ir.statements.block.UncheckedBlock], [YulBlock][wake.ir.yul.block.YulBlock] and [InlineAssembly][wake.ir.statements.inline_assembly.InlineAssembly] statements
        serve as containers for other statements and so may be contained in multiple CFG nodes. For this reason, a single [CfgNode][wake.analysis.cfg.CfgNode] cannot be returned for these statements.

        Args:
            statement: Statement for which to get the CFG node.

        Returns:
            CFG node that contains the given statement.
        """
        return self._statements_lookup[statement]

    def is_reachable(
        self,
        start: Union[StatementAbc, YulStatementAbc],
        end: Union[StatementAbc, YulStatementAbc],
    ) -> bool:
        """
        Args:
            start: Statement that is expected to be executed before `end`.
            end: Statement that is expected to be executed after `start`.

        Returns:
            True if there is an execution path from `start` to `end` in this CFG, False otherwise.
        """
        start_node = self._statements_lookup[start]
        end_node = self._statements_lookup[end]
        if start_node == end_node:
            if end == end_node.control_statement:
                return True
            start_index = start_node.statements.index(start)
            end_index = end_node.statements.index(end)
            if start_index <= end_index:  # also EQUAL?
                return True
            try:
                nx.find_cycle(self._graph, start_node)
                return True
            except nx.NetworkXNoCycle:
                return False
        else:
            return nx.has_path(self._graph, start_node, end_node)


def _normalize(
    graph: nx.DiGraph, start: CfgNode, success_end: CfgNode, revert_end: CfgNode
) -> bool:
    changed = False
    to_be_removed = set()

    for node in graph.nodes:
        for out_edge in list(graph.out_edges(node, data=True)):
            if out_edge[2]["condition"][0] == TransitionConditionKind.NEVER:
                graph.remove_edge(out_edge[0], out_edge[1])
                changed = True

        if (
            len(node.statements) == 0
            and len(graph.out_edges(node)) == 1
            and node != start
        ):
            edge = next(iter(graph.out_edges(node, data=True)))
            if edge[2]["condition"][0] == TransitionConditionKind.ALWAYS:
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


class CfgNode:
    """
    Basic building block of a control flow graph. Holds a list of statements and an optional control statement that is always
    executed last (if set). Solidity and Yul statements may be mixed in the same CFG node.
    """

    _id_counter: int = 0
    _id: int
    _statements: List[Union[StatementAbc, YulStatementAbc]]
    # control statement is always the last statement
    _control_statement: Optional[
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
        self._id = self.__class__._id_counter
        self.__class__._id_counter += 1
        self._statements = []
        self._control_statement = None

    def __str__(self):
        return (
            "\n".join(statement.source for statement in self.statements)
            if len(self.statements) > 0
            else ""
        )

    @property
    def id(self) -> int:
        """
        The concrete value should not be relied upon, it is only guaranteed to be unique within a single CFG.

        Returns:
            Unique ID of this CFG node.
        """
        return self._id

    @property
    def statements(self) -> Tuple[Union[StatementAbc, YulStatementAbc], ...]:
        """
        Returns:
            Statements contained in this CFG node.
        """
        return tuple(self._statements)

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
        """
        Control statements are handled specially in CFG construction, because they contain sub-statements that are not
        part of the current CFG node. At the same time, control statements are always nearest parent statements for
        some expressions and so must be indexed.

        !!! example
            For example, [IfStatement][wake.ir.statements.if_statement.IfStatement] is the nearest parent statement
            of the [IfStatement.condition][wake.ir.statements.if_statement.IfStatement.condition] expression.

        A control statement is always the last statement in a CFG node.

        Returns:
            Control statement of this CFG node, if any.
        """
        return self._control_statement

    @classmethod
    def from_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        loop_body_post: Optional[CfgNode],
        loop_body_next: Optional[CfgNode],
        statement: Union[StatementAbc, YulStatementAbc],
    ) -> CfgNode:
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
            prev._statements.append(statement)
            next = CfgNode()
            graph.add_node(next)
            graph.add_edge(
                prev, revert_end, condition=(TransitionConditionKind.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionConditionKind.NEVER, None))
            return next
        elif (
            isinstance(statement, YulExpressionStatement)
            and isinstance(statement.expression, YulFunctionCall)
            and statement.expression.function_name.name == "return"
        ):
            prev._statements.append(statement)
            next = CfgNode()
            graph.add_node(next)
            graph.add_edge(
                prev, success_end, condition=(TransitionConditionKind.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionConditionKind.NEVER, None))
            return next
        elif isinstance(statement, (Break, YulBreak)):
            prev._statements.append(statement)
            next = CfgNode()
            assert loop_body_next is not None
            graph.add_node(next)
            graph.add_edge(
                prev, loop_body_next, condition=(TransitionConditionKind.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionConditionKind.NEVER, None))
            return next
        elif isinstance(statement, (Continue, YulContinue)):
            prev._statements.append(statement)
            next = CfgNode()
            assert loop_body_post is not None
            graph.add_node(next)
            graph.add_edge(
                prev, loop_body_post, condition=(TransitionConditionKind.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionConditionKind.NEVER, None))
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
            prev._statements.append(statement)
            next = CfgNode()
            graph.add_node(next)
            graph.add_edge(
                prev, success_end, condition=(TransitionConditionKind.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionConditionKind.NEVER, None))
            return next
        elif isinstance(statement, RevertStatement):
            prev._statements.append(statement)
            next = CfgNode()
            graph.add_node(next)
            graph.add_edge(
                prev, revert_end, condition=(TransitionConditionKind.ALWAYS, None)
            )
            graph.add_edge(prev, next, condition=(TransitionConditionKind.NEVER, None))
            return next
        elif isinstance(statement, ExpressionStatement):

            def process_expression(expression: ExpressionAbc, node: CfgNode) -> bool:
                if isinstance(expression, Conditional):
                    true_node = CfgNode()
                    graph.add_node(true_node)
                    false_node = CfgNode()
                    graph.add_node(false_node)

                    graph.add_edge(
                        node,
                        true_node,
                        condition=(
                            TransitionConditionKind.IS_TRUE,
                            expression.condition,
                        ),
                    )
                    graph.add_edge(
                        node,
                        false_node,
                        condition=(
                            TransitionConditionKind.IS_FALSE,
                            expression.condition,
                        ),
                    )

                    true_is_control = process_expression(
                        expression.true_expression, true_node
                    )
                    false_is_control = process_expression(
                        expression.false_expression, false_node
                    )

                    if not true_is_control:
                        graph.remove_node(true_node)
                        if false_is_control:
                            graph.add_edge(
                                node,
                                next,
                                condition=(
                                    TransitionConditionKind.IS_TRUE,
                                    expression.condition,
                                ),
                            )

                    if not false_is_control:
                        graph.remove_node(false_node)
                        if true_is_control:
                            graph.add_edge(
                                node,
                                next,
                                condition=(
                                    TransitionConditionKind.IS_FALSE,
                                    expression.condition,
                                ),
                            )

                    return true_is_control or false_is_control
                elif isinstance(expression, FunctionCall):
                    func_called = expression.function_called
                    if func_called == GlobalSymbol.REVERT:
                        graph.add_edge(
                            node,
                            revert_end,
                            condition=(TransitionConditionKind.ALWAYS, None),
                        )
                        graph.add_edge(
                            node, next, condition=(TransitionConditionKind.NEVER, None)
                        )
                        return True
                    elif func_called in {
                        GlobalSymbol.REQUIRE,
                        GlobalSymbol.ASSERT,
                    }:
                        graph.add_edge(
                            node,
                            next,
                            condition=(
                                TransitionConditionKind.IS_TRUE,
                                expression.arguments[0],
                            ),
                        )
                        graph.add_edge(
                            node,
                            revert_end,
                            condition=(
                                TransitionConditionKind.IS_FALSE,
                                expression.arguments[0],
                            ),
                        )
                        return True
                    else:
                        return False

            prev._statements.append(statement)
            next = CfgNode()
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
            prev._statements.append(statement)
            return prev

    @classmethod
    def from_if_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        loop_body_post: Optional[CfgNode],
        loop_body_next: Optional[CfgNode],
        if_statement: IfStatement,
    ) -> CfgNode:
        assert prev._control_statement is None
        prev._control_statement = if_statement
        true_node = CfgNode()
        graph.add_node(true_node)
        true_node_end = cls.from_statement(
            graph,
            true_node,
            success_end,
            revert_end,
            loop_body_post,
            loop_body_next,
            if_statement.true_body,
        )

        false_node = CfgNode()
        graph.add_node(false_node)

        if if_statement.false_body is None:
            false_node_end = false_node
        else:
            false_node_end = cls.from_statement(
                graph,
                false_node,
                success_end,
                revert_end,
                loop_body_post,
                loop_body_next,
                if_statement.false_body,
            )

        next = CfgNode()
        graph.add_node(next)
        graph.add_edge(
            prev,
            true_node,
            condition=(TransitionConditionKind.IS_TRUE, if_statement.condition),
        )
        graph.add_edge(
            prev,
            false_node,
            condition=(TransitionConditionKind.IS_FALSE, if_statement.condition),
        )
        graph.add_edge(
            true_node_end, next, condition=(TransitionConditionKind.ALWAYS, None)
        )
        graph.add_edge(
            false_node_end, next, condition=(TransitionConditionKind.ALWAYS, None)
        )
        return next

    @classmethod
    def from_yul_if(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        loop_body_post: Optional[CfgNode],
        loop_body_next: Optional[CfgNode],
        if_statement: YulIf,
    ):
        assert prev._control_statement is None
        prev._control_statement = if_statement
        true_node = CfgNode()
        graph.add_node(true_node)
        true_node_end = cls.from_statement(
            graph,
            true_node,
            success_end,
            revert_end,
            loop_body_post,
            loop_body_next,
            if_statement.body,
        )
        next = CfgNode()
        graph.add_node(next)
        graph.add_edge(
            prev,
            true_node,
            condition=(TransitionConditionKind.IS_TRUE, if_statement.condition),
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionConditionKind.IS_FALSE, if_statement.condition),
        )
        graph.add_edge(
            true_node_end, next, condition=(TransitionConditionKind.ALWAYS, None)
        )
        return next

    @classmethod
    def from_do_while_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        do_while_statement: DoWhileStatement,
    ) -> CfgNode:
        body = CfgNode()
        graph.add_node(body)
        next = CfgNode()
        graph.add_node(next)
        body_end = cls.from_statement(
            graph, body, success_end, revert_end, body, next, do_while_statement.body
        )
        assert body_end._control_statement is None
        body_end._control_statement = do_while_statement

        graph.add_edge(prev, body, condition=(TransitionConditionKind.ALWAYS, None))
        graph.add_edge(
            body_end,
            next,
            condition=(TransitionConditionKind.IS_FALSE, do_while_statement.condition),
        )
        graph.add_edge(
            body_end,
            body,
            condition=(TransitionConditionKind.IS_TRUE, do_while_statement.condition),
        )
        return next

    @classmethod
    def from_for_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        for_statement: ForStatement,
    ) -> CfgNode:
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
        assert prev._control_statement is None
        prev._control_statement = for_statement

        body = CfgNode()
        graph.add_node(body)
        next = CfgNode()
        graph.add_node(next)
        loop_post = CfgNode()
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
            body_end, loop_post, condition=(TransitionConditionKind.ALWAYS, None)
        )
        graph.add_edge(
            prev,
            body,
            condition=(TransitionConditionKind.IS_TRUE, for_statement.condition),
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionConditionKind.IS_FALSE, for_statement.condition),
        )
        graph.add_edge(
            loop_post_end,
            body,
            condition=(TransitionConditionKind.IS_TRUE, for_statement.condition),
        )
        graph.add_edge(
            loop_post_end,
            next,
            condition=(TransitionConditionKind.IS_FALSE, for_statement.condition),
        )
        return next

    @classmethod
    def from_yul_for_loop(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        for_loop: YulForLoop,
    ) -> CfgNode:
        assert prev._control_statement is None
        prev = cls.from_statement(
            graph, prev, success_end, revert_end, None, None, for_loop.pre
        )
        assert prev._control_statement is None
        prev._control_statement = for_loop

        body = CfgNode()
        graph.add_node(body)
        next = CfgNode()
        graph.add_node(next)
        loop_post = CfgNode()
        graph.add_node(loop_post)
        body_end = cls.from_statement(
            graph, body, success_end, revert_end, loop_post, next, for_loop.body
        )
        loop_post_end = cls.from_statement(
            graph, loop_post, success_end, revert_end, loop_post, next, for_loop.post
        )

        graph.add_edge(
            body_end, loop_post, condition=(TransitionConditionKind.ALWAYS, None)
        )
        graph.add_edge(
            prev, body, condition=(TransitionConditionKind.IS_TRUE, for_loop.condition)
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionConditionKind.IS_FALSE, for_loop.condition),
        )
        graph.add_edge(
            loop_post_end,
            body,
            condition=(TransitionConditionKind.IS_TRUE, for_loop.condition),
        )
        graph.add_edge(
            loop_post_end,
            next,
            condition=(TransitionConditionKind.IS_FALSE, for_loop.condition),
        )
        return next

    @classmethod
    def from_try_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        loop_body_post: Optional[CfgNode],
        loop_body_next: Optional[CfgNode],
        try_statement: TryStatement,
    ) -> CfgNode:
        assert prev._control_statement is None
        prev._control_statement = try_statement

        success_node = CfgNode()
        graph.add_node(success_node)
        success_node_end = cls.from_statement(
            graph,
            success_node,
            success_end,
            revert_end,
            loop_body_post,
            loop_body_next,
            try_statement.clauses[0].block,
        )

        revert_node = None
        revert_node_end = None
        panic_node = None
        panic_node_end = None
        fail_node = None
        fail_node_end = None
        for clause in try_statement.clauses[1:]:
            if clause.error_name == "Error":
                revert_node = CfgNode()
                graph.add_node(revert_node)
                revert_node_end = cls.from_statement(
                    graph,
                    revert_node,
                    success_end,
                    revert_end,
                    loop_body_post,
                    loop_body_next,
                    clause.block,
                )
            elif clause.error_name == "Panic":
                panic_node = CfgNode()
                graph.add_node(panic_node)
                panic_node_end = cls.from_statement(
                    graph,
                    panic_node,
                    success_end,
                    revert_end,
                    loop_body_post,
                    loop_body_next,
                    clause.block,
                )
            elif clause.error_name == "":
                fail_node = CfgNode()
                graph.add_node(fail_node)
                fail_node_end = cls.from_statement(
                    graph,
                    fail_node,
                    success_end,
                    revert_end,
                    loop_body_post,
                    loop_body_next,
                    clause.block,
                )
            else:
                raise NotImplementedError(f"Unknown error name: {clause.error_name}")

        next = CfgNode()
        graph.add_node(next)

        graph.add_edge(
            prev,
            success_node,
            condition=(
                TransitionConditionKind.TRY_SUCCEEDED,
                try_statement.external_call,
            ),
        )
        graph.add_edge(
            success_node_end, next, condition=(TransitionConditionKind.ALWAYS, None)
        )
        if revert_node is not None:
            graph.add_edge(
                prev,
                revert_node,
                condition=(
                    TransitionConditionKind.TRY_REVERTED,
                    try_statement.external_call,
                ),
            )
            graph.add_edge(
                revert_node_end, next, condition=(TransitionConditionKind.ALWAYS, None)
            )
        if panic_node is not None:
            graph.add_edge(
                prev,
                panic_node,
                condition=(
                    TransitionConditionKind.TRY_PANICKED,
                    try_statement.external_call,
                ),
            )
            graph.add_edge(
                panic_node_end, next, condition=(TransitionConditionKind.ALWAYS, None)
            )
        if fail_node is not None:
            graph.add_edge(
                prev,
                fail_node,
                condition=(
                    TransitionConditionKind.TRY_FAILED,
                    try_statement.external_call,
                ),
            )
            graph.add_edge(
                fail_node_end, next, condition=(TransitionConditionKind.ALWAYS, None)
            )
        else:
            graph.add_edge(
                prev,
                revert_end,
                condition=(
                    TransitionConditionKind.TRY_FAILED,
                    try_statement.external_call,
                ),
            )
        return next

    @classmethod
    def from_yul_switch(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        switch: YulSwitch,
    ) -> CfgNode:
        assert prev._control_statement is None
        prev._control_statement = switch

        next = CfgNode()
        graph.add_node(next)

        for case_statement in switch.cases:
            case_node = CfgNode()
            graph.add_node(case_node)
            graph.add_edge(
                prev,
                case_node,
                condition=(TransitionConditionKind.SWITCH_MATCHED, case_statement.value)
                if case_statement.value != "default"
                else (TransitionConditionKind.SWITCH_DEFAULT, None),
            )
            case_node_end = cls.from_statement(
                graph,
                case_node,
                success_end,
                revert_end,
                case_node,
                next,
                case_statement.body,
            )
            graph.add_edge(
                case_node_end, next, condition=(TransitionConditionKind.ALWAYS, None)
            )

        if not any(case.value == "default" for case in switch.cases):
            graph.add_edge(
                prev,
                next,
                condition=(TransitionConditionKind.SWITCH_DEFAULT, None),
            )

        return next

    @classmethod
    def from_while_statement(
        cls,
        graph: nx.DiGraph,
        prev: CfgNode,
        success_end: CfgNode,
        revert_end: CfgNode,
        while_statement: WhileStatement,
    ) -> CfgNode:
        assert prev._control_statement is None
        prev._control_statement = while_statement

        body = CfgNode()
        graph.add_node(body)
        next = CfgNode()
        graph.add_node(next)
        body_end = cls.from_statement(
            graph, body, success_end, revert_end, body, next, while_statement.body
        )

        graph.add_edge(
            prev,
            body,
            condition=(TransitionConditionKind.IS_TRUE, while_statement.condition),
        )
        graph.add_edge(
            prev,
            next,
            condition=(TransitionConditionKind.IS_FALSE, while_statement.condition),
        )
        graph.add_edge(
            body_end,
            body,
            condition=(TransitionConditionKind.IS_TRUE, while_statement.condition),
        )
        graph.add_edge(
            body_end,
            next,
            condition=(TransitionConditionKind.IS_FALSE, while_statement.condition),
        )
        return next
