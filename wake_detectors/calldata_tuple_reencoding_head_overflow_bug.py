from __future__ import annotations

from typing import List, Sequence

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


def type_contains_dynamic_component(t: types.TypeAbc) -> bool:
    if isinstance(t, types.Array):
        if t.length is None:
            return True
        return type_contains_dynamic_component(t.base_type)
    elif isinstance(t, (types.Bytes, types.String)):
        return True
    elif isinstance(t, types.Tuple):
        return any(
            type_contains_dynamic_component(component)
            for component in t.components
            if component is not None
        )
    elif isinstance(t, types.Struct):
        return any(type_contains_dynamic_component(m.type) for m in t.ir_node.members)
    else:
        return False


def types_meet_requirements(
    t: Sequence[types.TypeAbc], data_location_is_calldata: bool = False
) -> bool:
    for component in t:
        if isinstance(component, types.Struct):
            bug = types_meet_requirements(
                list(m.type for m in component.ir_node.members),
                data_location_is_calldata
                or component.data_location == ir.enums.DataLocation.CALLDATA,
            )
            if bug:
                return True

    if len(t) < 2:
        return False
    last = t[-1]
    if not (
        isinstance(last, types.Array)
        and last.length is not None
        and (
            last.data_location == ir.enums.DataLocation.CALLDATA
            or data_location_is_calldata
        )
    ):
        return False

    base_type = last.base_type
    while isinstance(base_type, types.Array):
        if base_type.length is None:
            return False
        base_type = base_type.base_type
    if isinstance(base_type, types.UInt) and base_type.bits_count == 256:
        pass
    elif isinstance(base_type, types.FixedBytes) and base_type.bytes_count == 32:
        pass
    else:
        return False

    if not any(type_contains_dynamic_component(x) for x in t[:-1]):
        return False

    return True


def abi_encoder_v2_enabled(source_unit: ir.SourceUnit) -> bool:
    from wake.core.solidity_version import SolidityVersionRange, SolidityVersionRanges

    if any(
        directive.literals == ("abicoder", "v1") for directive in source_unit.pragmas
    ):
        return False
    elif any(
        directive.literals == ("abicoder", "v2") for directive in source_unit.pragmas
    ):
        return True
    elif any(
        directive.literals == ("experimental", "ABIEncoderV2")
        for directive in source_unit.pragmas
    ):
        return True
    else:
        default_v2_versions = SolidityVersionRanges(
            [SolidityVersionRange("0.8.0", True, None, None)]
        )
        if len(default_v2_versions & source_unit.version_ranges) == 0:
            return False
        return True


class CalldataTupleReencodingHeadOverflowBugDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_function_definition(self, node: ir.FunctionDefinition):
        from wake.core.solidity_version import (
            SolidityVersionRange,
            SolidityVersionRanges,
        )

        if node.visibility not in {
            ir.enums.Visibility.PUBLIC,
            ir.enums.Visibility.EXTERNAL,
        }:
            return

        input_encoded_types = [param.type for param in node.parameters.parameters]
        if types_meet_requirements(input_encoded_types, True):
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "External calls to this function may send malformed data because of compiler bug in Solidity < 0.8.16",
                    ),
                    impact=DetectorImpact.HIGH,
                    confidence=DetectorConfidence.LOW,
                    uri=generate_detector_uri(
                        name="calldata-tuple-reencoding-head-overflow-bug",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

        versions = node.source_unit.version_ranges
        affected_versions = SolidityVersionRanges(
            [SolidityVersionRange("0.5.8", True, "0.8.16", False)]
        )
        if len(versions & affected_versions) == 0:
            return

        # ABI encoder v2 must be enabled
        if not abi_encoder_v2_enabled(node.source_unit):
            return

        output_encoded_types = [
            param.type for param in node.return_parameters.parameters
        ]
        if types_meet_requirements(output_encoded_types):
            self._detections.append(
                DetectorResult(
                    Detection(
                        node.return_parameters,
                        "ABI-encoded return data from this function may be malformed because of compiler bug",
                    ),
                    impact=DetectorImpact.HIGH,
                    confidence=DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="calldata-tuple-reencoding-head-overflow-bug",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    def visit_function_call(self, node: ir.FunctionCall):
        from wake.core.solidity_version import (
            SolidityVersionRange,
            SolidityVersionRanges,
        )

        if node.kind == ir.enums.FunctionCallKind.TYPE_CONVERSION:
            return

        versions = node.source_unit.version_ranges
        affected_versions = SolidityVersionRanges(
            [SolidityVersionRange("0.5.8", True, "0.8.16", False)]
        )
        if len(versions & affected_versions) == 0:
            return

        func_identifier = node.expression
        while True:
            if isinstance(func_identifier, (ir.Identifier, ir.MemberAccess)):
                break
            elif isinstance(func_identifier, ir.FunctionCallOptions):
                func_identifier = func_identifier.expression
            elif isinstance(func_identifier, ir.NewExpression):
                return
            elif (
                isinstance(func_identifier, ir.TupleExpression)
                and len(func_identifier.components) == 1
            ):
                func_identifier = func_identifier.components[0]
            elif isinstance(func_identifier, ir.FunctionCall):
                t = func_identifier.type
                if isinstance(t, types.Function) and (t.value_set or t.gas_set):
                    func_identifier = func_identifier.expression
                else:
                    # function returning a function
                    break
            else:
                return

        t = func_identifier.type

        if not isinstance(t, types.Function):
            return

        if t.kind == ir.enums.FunctionTypeKind.EXTERNAL:
            assert t.attached_to is None
            encoded_types = [arg.type for arg in node.arguments]
        elif t.kind in {
            ir.enums.FunctionTypeKind.ERROR,
            ir.enums.FunctionTypeKind.EVENT,
        }:
            encoded_types = [arg.type for arg in node.arguments]
        elif t.kind in {
            ir.enums.FunctionTypeKind.ABI_ENCODE,
            ir.enums.FunctionTypeKind.ABI_ENCODE_PACKED,
        }:
            encoded_types = [arg.type for arg in node.arguments]
        elif t.kind in {
            ir.enums.FunctionTypeKind.ABI_ENCODE_WITH_SELECTOR,
            ir.enums.FunctionTypeKind.ABI_ENCODE_WITH_SIGNATURE,
        }:
            assert len(node.arguments) >= 1
            encoded_types = [arg.type for arg in node.arguments[1:]]
        elif t.kind == ir.enums.FunctionTypeKind.ABI_ENCODE_CALL:
            assert len(node.arguments) == 2
            if isinstance(node.arguments[1], ir.TupleExpression):
                encoded_types = [
                    arg.type if arg is not None else None
                    for arg in node.arguments[
                        1
                    ].components  # pyright: ignore reportGeneralTypeIssues
                ]
            elif (
                isinstance(node.arguments[1], ir.FunctionCall)
                and node.arguments[1].kind
                == ir.enums.FunctionCallKind.STRUCT_CONSTRUCTOR_CALL
            ):
                # probably always created in memory, not calldata
                return
            else:
                return
        else:
            return

        # ABI encoder v2 must be enabled
        if not abi_encoder_v2_enabled(node.source_unit):
            return

        if types_meet_requirements(
            encoded_types  # pyright: ignore reportGeneralTypeIssues
        ):
            self._detections.append(
                DetectorResult(
                    Detection(
                        node,
                        "ABI-encoded data in this call may be malformed because of compiler bug",
                    ),
                    impact=DetectorImpact.HIGH,
                    confidence=DetectorConfidence.HIGH,
                    uri=generate_detector_uri(
                        name="calldata-tuple-reencoding-head-overflow-bug",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="calldata-tuple-reencoding-head-overflow-bug")
    def cli(self) -> None:
        """
        Head overflow calldata tuple reencoding compiler bug in Solidity < 0.8.16
        """
