from __future__ import annotations

from typing import List, Set

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


class StructMappingDeletionDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def _check_struct_mapping(self, t: types.TypeAbc) -> Set[ir.VariableDeclaration]:
        if isinstance(t, types.Array):
            return self._check_struct_mapping(t.base_type)
        elif isinstance(t, types.Struct):
            ret = set()
            for m in t.ir_node.members:
                if isinstance(m.type, types.Mapping):
                    ret.add(m)
                else:
                    ret.update(self._check_struct_mapping(m.type))
            return ret
        else:
            return set()

    def visit_unary_operation(self, node: ir.UnaryOperation):
        if node.operator != ir.enums.UnaryOpOperator.DELETE:
            return

        t = node.sub_expression.type
        assert t is not None
        members = self._check_struct_mapping(t)
        if len(members) > 0:
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "Deleting a struct with a mapping member does not delete the mapping",
                        subdetections=tuple(
                            Detection(m, "Mapping member is not deleted")
                            for m in members
                        ),
                    ),
                    impact=DetectorImpact.MEDIUM,
                    confidence=DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="struct-mapping-deletion",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="struct-mapping-deletion")
    def cli(self) -> None:
        """
        Mapping struct member not deleted
        """
