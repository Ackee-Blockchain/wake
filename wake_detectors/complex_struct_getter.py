from __future__ import annotations

from typing import List, Set, Tuple

import networkx as nx
import rich_click as click

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.detectors import (
    Detection,
    Detector,
    DetectorConfidence,
    DetectorImpact,
    DetectorResult,
    detector,
)
from wake_detectors.utils import generate_detector_uri


class ComplexStructGetterDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def _check_complex_struct(self, t: types.TypeAbc) -> Set[ir.VariableDeclaration]:
        if isinstance(t, types.Array):
            return self._check_complex_struct(t.base_type)
        elif isinstance(t, types.Mapping):
            return self._check_complex_struct(t.value_type)
        elif isinstance(t, types.Struct):
            ret = set()
            for m in t.ir_node.members:
                if isinstance(m.type, types.Array):
                    ret.add(m)
                elif isinstance(m.type, types.Mapping):
                    ret.add(m)
                else:
                    ret.update(self._check_complex_struct(m.type))
            return ret
        else:
            return set()

    def visit_variable_declaration(self, node: ir.VariableDeclaration):
        if not node.is_state_variable or node.visibility != ir.enums.Visibility.PUBLIC:
            return

        omitted_members = self._check_complex_struct(node.type)
        if len(omitted_members) > 0:
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "State variable getter does not return all members of a complex struct",
                        subdetections=tuple(
                            Detection(m, "Omitted member") for m in omitted_members
                        ),
                    ),
                    impact=DetectorImpact.WARNING,
                    confidence=DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="complex-struct-getter",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                ),
            )

    def detect(self) -> List[DetectorResult]:
        return self._detections

    @detector.command(name="complex-struct-getter")
    def cli(self) -> None:
        """
        Struct getter does not return all members
        """
