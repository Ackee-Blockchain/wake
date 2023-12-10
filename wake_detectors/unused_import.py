from __future__ import annotations

from typing import List

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


class UnusedImportDetector(Detector):
    def __init__(self):
        self.detections = []

    def detect(self) -> List[DetectorResult]:
        return self.detections

    @detector.command(name="unused-import")
    def cli(self) -> None:
        """
        Unused import
        """

    def visit_source_unit(self, node: ir.SourceUnit):
        from wake.analysis.graph import graph_iter

        for import_directive in node.imports:
            imported_source_unit_name = import_directive.imported_source_unit_name
            found_imported_symbol = False

            for predecessor in graph_iter(
                self.imports_graph, imported_source_unit_name, "in"
            ):
                predecessor_path = (
                    self.imports_graph.nodes[  # pyright: ignore reportGeneralTypeIssues
                        predecessor
                    ]["path"]
                )
                source_unit = self.build.source_units[predecessor_path]

                # should not be needed to check for aliases, as there still should be original global declarations referenced

                for declaration in source_unit.declarations_iter():
                    for ref in declaration.references:
                        if isinstance(ref, ir.IdentifierPathPart):
                            ref = ref.underlying_node
                        elif isinstance(ref, ir.ExternalReference):
                            ref = ref.inline_assembly

                        if ref.source_unit.source_unit_name == node.source_unit_name:
                            found_imported_symbol = True
                            break

                    if found_imported_symbol:
                        break

                if found_imported_symbol:
                    break

            if not found_imported_symbol:
                self.detections.append(
                    DetectorResult(
                        Detection(
                            import_directive,
                            "Unused import",
                        ),
                        impact=DetectorImpact.INFO,
                        confidence=DetectorConfidence.HIGH,
                        uri=generate_detector_uri(
                            name="unused-import",
                            version=self.extra["package_versions"]["eth-wake"],
                        ),
                    )
                )
