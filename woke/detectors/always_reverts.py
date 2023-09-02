from __future__ import annotations

from typing import List

import networkx as nx
import rich_click as click

import woke.ir as ir
from woke.detectors import (
    Detection,
    DetectionConfidence,
    DetectionImpact,
    Detector,
    DetectorResult,
    detector,
)


class AlwaysRevertsDetector(Detector):
    mod: bool
    pure: bool
    view: bool
    func: bool
    results = []

    def detect(self) -> List[DetectorResult]:
        return self.results

    def visit_modifier_definition(self, node: ir.ModifierDefinition):
        if not self.mod or not node.implemented:
            return

        cfg = node.cfg
        assert cfg is not None
        if not nx.has_path(cfg.graph, cfg.start_block, cfg.success_end_block):
            self.results.append(
                DetectorResult(
                    Detection(
                        node,
                        "Modifier always reverts",
                    ),
                    impact=DetectionImpact.HIGH,
                    confidence=DetectionConfidence.HIGH,
                )
            )

    def visit_function_definition(self, node: ir.FunctionDefinition):
        if (
            not self.func
            or not node.implemented
            or node.state_mutability == ir.enums.StateMutability.PURE
            and not self.pure
            or node.state_mutability == ir.enums.StateMutability.VIEW
            and not self.view
        ):
            return

        cfg = node.cfg
        assert cfg is not None
        if not nx.has_path(cfg.graph, cfg.start_block, cfg.success_end_block):
            self.results.append(
                DetectorResult(
                    Detection(
                        node,
                        "Function always reverts",
                    ),
                    impact=DetectionImpact.HIGH,
                    confidence=DetectionConfidence.HIGH,
                )
            )

    @detector.command(name="always-reverts")
    @click.option(
        "--mod/--no-mod",
        "--modifier/--no-modifier",
        default=True,
        is_flag=True,
        help="Check modifiers",
    )
    @click.option(
        "--pure/--no-pure", default=False, is_flag=True, help="Check pure functions"
    )
    @click.option(
        "--view/--no-view", default=False, is_flag=True, help="Check view functions"
    )
    @click.option(
        "--func/--no-func",
        "--function/--no-function",
        default=True,
        is_flag=True,
        help="Check functions",
    )
    def cli(self, mod: bool, pure: bool, view: bool, func: bool) -> None:
        self.mod = mod
        self.pure = pure
        self.view = view
        self.func = func
