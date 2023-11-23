import os
import sys
from inspect import cleandoc
from pathlib import Path
from typing import Dict, List, Tuple

from rich_click import Command
from sarif_om import (
    ArtifactLocation,
    Invocation,
    Location,
    PhysicalLocation,
    Region,
    ReportingDescriptor,
    ReportingDescriptorReference,
    Result,
    Run,
    SarifLog,
    Tool,
    ToolComponent,
    ToolComponentReference,
)

from wake.utils import get_package_version
from wake.utils.keyed_default_dict import KeyedDefaultDict

from ..ir import DeclarationAbc
from .api import DetectorImpact, DetectorResult

# pyright: reportGeneralTypeIssues=false


def create_sarif_log(
    detectors: List[Command], detections: List[Tuple[str, DetectorResult]]
) -> SarifLog:
    from wake.cli.detect import run_detect

    if sys.version_info < (3, 10):
        from importlib_metadata import packages_distributions
    else:
        from importlib.metadata import packages_distributions

    distributions = packages_distributions()

    driver = ToolComponent(
        name="wake",
        semantic_version=get_package_version("eth-wake"),
        rules=[],
    )
    extensions = KeyedDefaultDict(
        lambda n: ToolComponent(
            name=n, semantic_version=get_package_version(n), rules=[]
        )
    )

    detector_index_mapping: Dict[str, int] = {}
    for command in detectors:
        descriptor = ReportingDescriptor(
            id=command.name,
            short_description={"text": cleandoc(command.help or "")},
        )

        source = run_detect.loaded_from_plugins[command.name]
        # try to infer package name from entry point module name
        if (
            isinstance(source, str)
            and source in source in distributions
            and len(distributions[source]) == 1
        ):
            # loaded from plugin
            package_name = distributions[source][0]
            detector_index_mapping[command.name] = len(extensions[package_name].rules)
            extensions[package_name].rules.append(descriptor)
        else:
            # loaded from local path
            detector_index_mapping[command.name] = len(driver.rules)
            driver.rules.append(descriptor)

    extensions_list = list(extensions.values())
    extensions_index_mapping = {e.name: i for i, e in enumerate(extensions_list)}

    impact_to_level = {
        DetectorImpact.HIGH: "error",
        DetectorImpact.MEDIUM: "error",
        DetectorImpact.LOW: "error",
        DetectorImpact.WARNING: "warning",
        DetectorImpact.INFO: "note",
    }

    workspace_root = os.getenv("GITHUB_WORKSPACE")
    if workspace_root is not None:
        workspace_root = Path(workspace_root).resolve()

    results = []
    for detector_name, result in detections:
        (
            start_line,
            start_col,
        ) = result.detection.ir_node.source_unit.get_line_col_from_byte_offset(
            result.detection.lsp_range
            if result.detection.lsp_range is not None
            else result.detection.ir_node.name_location[0]
            if isinstance(result.detection.ir_node, DeclarationAbc)
            else result.detection.ir_node.byte_location[0]
        )
        (
            end_line,
            end_col,
        ) = result.detection.ir_node.source_unit.get_line_col_from_byte_offset(
            result.detection.lsp_range
            if result.detection.lsp_range is not None
            else result.detection.ir_node.name_location[1]
            if isinstance(result.detection.ir_node, DeclarationAbc)
            else result.detection.ir_node.byte_location[1]
        )
        rule = ReportingDescriptorReference(
            id=detector_name,
            index=detector_index_mapping[detector_name],
        )

        source = run_detect.loaded_from_plugins[detector_name]
        if (
            isinstance(source, str)
            and source in distributions
            and len(distributions[source]) == 1
        ):
            package_name = distributions[source][0]
            rule.tool_component = ToolComponentReference(
                name=package_name,
                index=extensions_index_mapping[package_name],
            )

        related_locations = []
        for i, subdetection in enumerate(result.detection.subdetections):
            (
                sub_start_line,
                sub_start_col,
            ) = subdetection.ir_node.source_unit.get_line_col_from_byte_offset(
                subdetection.lsp_range
                if subdetection.lsp_range is not None
                else subdetection.ir_node.name_location[0]
                if isinstance(subdetection.ir_node, DeclarationAbc)
                else subdetection.ir_node.byte_location[0]
            )
            (
                sub_end_line,
                sub_end_col,
            ) = subdetection.ir_node.source_unit.get_line_col_from_byte_offset(
                subdetection.lsp_range
                if subdetection.lsp_range is not None
                else subdetection.ir_node.name_location[1]
                if isinstance(subdetection.ir_node, DeclarationAbc)
                else subdetection.ir_node.byte_location[1]
            )
            related_locations.append(
                Location(
                    id=i,
                    physical_location=PhysicalLocation(
                        artifact_location=ArtifactLocation(
                            uri=f"{subdetection.ir_node.source_unit.file if workspace_root is None else subdetection.ir_node.source_unit.file.relative_to(workspace_root)}",
                        ),
                        region=Region(
                            start_line=sub_start_line,
                            start_column=sub_start_col,
                            end_line=sub_end_line,
                            end_column=sub_end_col,
                        ),
                    ),
                    message={"text": subdetection.message},
                )
            )

        results.append(
            Result(
                rule=rule,
                level=impact_to_level[result.impact],
                message={
                    "text": result.detection.message
                    + "\n"
                    + "".join(
                        f"[{related_locations[i].message['text']}]({i})"
                        for i in range(len(related_locations))
                    )
                },
                locations=[
                    Location(
                        physical_location=PhysicalLocation(
                            artifact_location=ArtifactLocation(
                                uri=f"{result.detection.ir_node.source_unit.file if workspace_root is None else result.detection.ir_node.source_unit.file.relative_to(workspace_root)}",
                            ),
                            region=Region(
                                start_line=start_line,
                                start_column=start_col,
                                end_line=end_line,
                                end_column=end_col,
                            ),
                        )
                    )
                ],
                related_locations=related_locations,
            )
        )

    return SarifLog(
        schema_uri="https://json.schemastore.org/sarif-2.1.0.json",
        version="2.1.0",
        runs=[
            Run(
                tool=Tool(
                    driver=driver,
                    extensions=extensions_list,
                ),
                invocations=[
                    Invocation(
                        execution_successful=True,
                    ),
                ],
                results=results,
            ),
        ],
    )
