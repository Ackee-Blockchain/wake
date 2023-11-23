from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, List, Set, Tuple

import networkx as nx
import rich_click as click

import wake.ir as ir
import wake.ir.types as types
from wake.detectors import (
    Detection,
    Detector,
    DetectorConfidence,
    DetectorImpact,
    DetectorResult,
    detector,
)
from wake_detectors.utils import generate_detector_uri

if TYPE_CHECKING:
    from wake.analysis.cfg import CfgNode


def _modifies_state_after_statement(
    function_definition: ir.FunctionDefinition,
    statement: ir.StatementAbc,
) -> Set[Tuple[ir.IrAbc, ir.enums.ModifiesStateFlag]]:
    ret: Set[Tuple[ir.IrAbc, ir.enums.ModifiesStateFlag]] = set()
    cfg = function_definition.cfg
    start = cfg.get_cfg_node(statement)
    graph = cfg.graph

    if not nx.has_path(graph, start, cfg.success_end_node):
        return ret

    if statement not in start.statements:
        assert statement == start.control_statement
    else:
        index = start.statements.index(statement)
        for s in start.statements[index + 1 :]:
            ret.update(s.modifies_state)
        if start.control_statement is not None:
            ret.update(start.control_statement.modifies_state)

    queue = deque([])
    visited: Set[CfgNode] = set()

    for _, to in graph.out_edges(start):  # pyright: ignore reportGeneralTypeIssues
        if to in visited:
            continue
        if not nx.has_path(graph, to, cfg.success_end_node):
            continue
        queue.append(to)

    while len(queue):
        block = queue.popleft()
        for s in block.statements:
            ret.update(s.modifies_state)
        if block.control_statement is not None:
            ret.update(block.control_statement.modifies_state)

        to: CfgNode
        for _, to in graph.out_edges(block):  # pyright: ignore reportGeneralTypeIssues
            if to in visited:
                continue
            if not nx.has_path(graph, to, cfg.success_end_node):
                continue

            visited.add(to)
            queue.append(to)

    return ret


class ReentrancyDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def _check_reentrancy_in_function(
        self,
        function_definition: ir.FunctionDefinition,
        statement: ir.StatementAbc,
        address_source: ir.ExpressionAbc,
        child_modifies_state: Set[Tuple[ir.IrAbc, ir.enums.ModifiesStateFlag]],
        checked_statements: Set[ir.StatementAbc],
    ) -> List[Tuple[Detection, DetectorImpact, DetectorConfidence]]:
        from functools import reduce
        from operator import or_

        from wake.analysis.expressions import find_low_level_call_source_address
        from wake.analysis.ownable import (
            address_is_safe,
            statement_is_publicly_executable,
        )
        from wake.analysis.utils import (
            get_all_base_and_child_declarations,
            pair_function_call_arguments,
        )

        # TODO check non-reentrant
        if not statement_is_publicly_executable(statement, check_only_eoa=True):
            return []

        source_address_declaration = find_low_level_call_source_address(address_source)
        is_safe = None
        if source_address_declaration is None:
            pass
            # self.logger.debug(f"{address_source.source}")
        elif isinstance(source_address_declaration, ir.enums.GlobalSymbol):
            if source_address_declaration == ir.enums.GlobalSymbol.THIS:
                is_safe = True
            elif source_address_declaration in {
                ir.enums.GlobalSymbol.MSG_SENDER,
                ir.enums.GlobalSymbol.TX_ORIGIN,
            }:
                is_safe = False
            else:
                is_safe = None
                # self.logger.debug(f"{source_address_declaration}:")
        elif isinstance(source_address_declaration, ir.ContractDefinition):
            if source_address_declaration.kind == ir.enums.ContractKind.LIBRARY:
                is_safe = True
        elif isinstance(source_address_declaration, ir.Literal):
            is_safe = True
        else:
            is_safe = address_is_safe(source_address_declaration)

        if is_safe:
            return []

        checked_statements.add(statement)
        ret = []

        this_modifies_state = set(child_modifies_state)
        this_modifies_state.update(
            _modifies_state_after_statement(function_definition, statement)
        )

        if len(this_modifies_state) and function_definition.visibility in {
            ir.enums.Visibility.PUBLIC,
            ir.enums.Visibility.EXTERNAL,
        }:
            state_mods = reduce(or_, (mod[1] for mod in this_modifies_state))
            if state_mods & (
                ir.enums.ModifiesStateFlag.MODIFIES_STATE_VAR
                | ir.enums.ModifiesStateFlag.SENDS_ETHER
                | ir.enums.ModifiesStateFlag.PERFORMS_CALL
                | ir.enums.ModifiesStateFlag.CALLS_UNIMPLEMENTED_NONPAYABLE_FUNCTION
                | ir.enums.ModifiesStateFlag.CALLS_UNIMPLEMENTED_PAYABLE_FUNCTION
            ):
                impact = DetectorImpact.HIGH
            elif state_mods & (
                ir.enums.ModifiesStateFlag.EMITS
                | ir.enums.ModifiesStateFlag.DEPLOYS_CONTRACT
                | ir.enums.ModifiesStateFlag.SELFDESTRUCTS
                | ir.enums.ModifiesStateFlag.PERFORMS_DELEGATECALL
            ):
                impact = DetectorImpact.WARNING
            else:
                raise NotImplementedError()

            ret.append(
                (
                    Detection(
                        statement,
                        f"Exploitable from `{function_definition.canonical_name}`",
                    ),
                    impact,
                    DetectorConfidence.LOW
                    if is_safe is None
                    else DetectorConfidence.MEDIUM,
                )
            )

        for ref in function_definition.get_all_references(False):
            if isinstance(ref, ir.IdentifierPathPart):
                top_statement = ref.underlying_node
            elif isinstance(ref, ir.ExternalReference):
                continue  # TODO currently not supported
            else:
                top_statement = ref
            func_call = None
            while top_statement is not None:
                if (
                    func_call is None
                    and isinstance(top_statement, ir.FunctionCall)
                    and top_statement.function_called
                    in get_all_base_and_child_declarations(function_definition)
                ):
                    func_call = top_statement
                if isinstance(top_statement, ir.StatementAbc):
                    break
                top_statement = top_statement.parent

            if top_statement is None or func_call is None:
                continue
            function_def = top_statement
            while function_def is not None and not isinstance(
                function_def, ir.FunctionDefinition
            ):
                function_def = function_def.parent
            if function_def is None:
                continue
            assert isinstance(function_def, ir.FunctionDefinition)
            if top_statement in checked_statements:
                continue

            if source_address_declaration in function_definition.parameters.parameters:
                for arg_decl, arg_expr in pair_function_call_arguments(
                    function_definition, func_call
                ):
                    if arg_decl == source_address_declaration:
                        assert isinstance(
                            arg_expr.type, (types.Address, types.Contract)
                        )
                        ret.extend(
                            self._check_reentrancy_in_function(
                                function_def,
                                top_statement,
                                arg_expr,
                                this_modifies_state,
                                checked_statements,
                            )
                        )
                        break
            else:
                ret.extend(
                    self._check_reentrancy_in_function(
                        function_def,
                        top_statement,
                        address_source,
                        this_modifies_state,
                        checked_statements,
                    )
                )
        return ret

    def visit_member_access(self, node: ir.MemberAccess):
        t = node.type
        if (
            not isinstance(t, types.Function)
            or t.kind
            not in {
                ir.enums.FunctionTypeKind.BARE_CALL,
                ir.enums.FunctionTypeKind.EXTERNAL,
            }
            or t.state_mutability
            in {
                ir.enums.StateMutability.PURE,
                ir.enums.StateMutability.VIEW,
            }
        ):
            return

        # TODO: reentrancy in modifiers
        if node.statement is None or not isinstance(
            node.statement.declaration, ir.FunctionDefinition
        ):
            return

        function_call = node
        while function_call != node.statement:
            if (
                isinstance(function_call, ir.FunctionCall)
                and function_call.function_called == node.referenced_declaration
            ):
                break
            function_call = function_call.parent

        if function_call == node.statement:
            return

        ret = self._check_reentrancy_in_function(
            node.statement.declaration, node.statement, node.expression, set(), set()
        )
        if len(ret) == 0:
            return

        impact = max(impact for _, impact, _ in ret)
        confidence = max(confidence for _, _, confidence in ret)
        subdetections = tuple(
            sorted(
                (detection for detection, _, _ in ret),
                key=lambda x: x.ir_node.byte_location[0],
            )
        )

        self._detections.append(
            DetectorResult(
                Detection(
                    node,
                    f"Possible reentrancy in `{node.statement.declaration.canonical_name}`",
                    subdetections,
                ),
                impact=impact,
                confidence=confidence,
                uri=generate_detector_uri(
                    name="reentrancy",
                    version=self.extra["package_versions"]["eth-wake"],
                ),
            )
        )

    # TODO: configurable trusted address/contract variables
    @detector.command(name="reentrancy")
    def cli(self) -> None:
        """
        External call vulnerable to reentrancy
        """
