from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING, DefaultDict, List, Set

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


class MissingReturnDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_function_definition(self, node: ir.FunctionDefinition):
        if not node.implemented or len(node.return_parameters.parameters) == 0:
            return

        cfg = node.cfg
        cfg_node_assignments: DefaultDict[
            CfgNode, Set[ir.VariableDeclaration]
        ] = defaultdict(set)

        for param in node.return_parameters.parameters:
            for ref in param.references:
                if isinstance(ref, ir.ExternalReference):
                    yul_identifier = ref.yul_identifier
                    parent = yul_identifier.parent

                    if (
                        isinstance(parent, ir.YulAssignment)
                        and len(parent.variable_names) == 1
                        and parent.variable_names[0] == yul_identifier
                    ):
                        cfg_node_assignments[cfg.get_cfg_node(parent)].add(param)
                    continue
                elif isinstance(
                    ref, (ir.IdentifierPathPart, ir.BinaryOperation, ir.UnaryOperation)
                ):
                    # should not happen
                    continue

                assignment = ref.parent
                while not isinstance(assignment, (ir.Assignment, ir.StatementAbc)):
                    if assignment is None:
                        break
                    assignment = assignment.parent
                if isinstance(assignment, ir.Assignment):
                    assert assignment.statement is not None
                    for path in assignment.assigned_variables:
                        if path is None:
                            continue
                        for option in path:
                            if param in option:
                                cfg_node_assignments[
                                    cfg.get_cfg_node(assignment.statement)
                                ].add(param)
                                break

        unassigned_path = False
        queue = deque([(cfg.start_node, set(node.return_parameters.parameters))])
        visited = {(cfg.start_node, frozenset(node.return_parameters.parameters))}

        while len(queue) > 0:
            cfg_node, unassigned_vars = queue.pop()

            if any(isinstance(stmt, ir.Return) for stmt in cfg_node.statements):
                continue

            unassigned_vars.difference_update(cfg_node_assignments[cfg_node])
            if len(unassigned_vars) == 0:
                continue

            if cfg_node == cfg.success_end_node:
                unassigned_path = True
                break

            for succ in cfg.graph.successors(cfg_node):
                if (succ, frozenset(unassigned_vars)) not in visited:
                    visited.add((succ, frozenset(unassigned_vars)))
                    queue.append((succ, unassigned_vars.copy()))

        if unassigned_path:
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "Not all execution paths have assigned return values",
                    ),
                    impact=DetectorImpact.WARNING,
                    confidence=DetectorConfidence.MEDIUM,
                    uri=generate_detector_uri(
                        name="missing-return",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="missing-return")
    def cli(self) -> None:
        """
        Function return parameters may not always be set
        """
