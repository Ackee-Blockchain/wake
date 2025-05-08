from __future__ import annotations

from collections import namedtuple
from typing import List, Optional

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
from wake.ir.enums import ContractKind, StateMutability
from wake_detectors.utils import generate_detector_uri

FunctionInfo = namedtuple(
    "FunctionInfo", ["name", "state_mutability", "return_parameters"]
)


def return_parameters_string(function: ir.FunctionDefinition) -> List[str]:
    return list(
        map(
            lambda param: param.type_name.type.abi_type,
            function.return_parameters._parameters,
        )
    )


class ChainlinkDeprecatedFunctionDetector(Detector):

    chainlink_deprecated_functions = {
        b"\x50\xd2\x5b\xcd": FunctionInfo(
            "latestAnswer()", StateMutability.VIEW, ["int256"]
        ),
        b"\x82\x05\xbf\x6a": FunctionInfo(
            "latestTimestamp()", StateMutability.VIEW, ["uint256"]
        ),
        b"\x66\x8a\x0f\x02": FunctionInfo(
            "latestRound()", StateMutability.VIEW, ["uint256"]
        ),
        b"\xb5\xab\x58\xdc": FunctionInfo(
            "getAnswer(uint256)", StateMutability.VIEW, ["int256"]
        ),
        b"\xb6\x33\x62\x0c": FunctionInfo(
            "getTimestamp(uint256)", StateMutability.VIEW, ["uint256"]
        ),
    }

    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_function_call(self, node: ir.FunctionCall) -> None:
        if not isinstance(node.function_called, ir.FunctionDefinition):
            return
        if not isinstance(node.function_called.function_selector, bytes):
            return
        if (
            not node.function_called.function_selector
            in self.chainlink_deprecated_functions.keys()
        ):
            return

        matched_function_info = self.chainlink_deprecated_functions[
            node.function_called.function_selector
        ]
        if (
            not matched_function_info.state_mutability
            == node.function_called.state_mutability
        ):
            return
        if not matched_function_info.return_parameters == return_parameters_string(
            node.function_called
        ):
            return

        if not isinstance(node.function_called.parent, ir.ContractDefinition):
            return
        if not node.function_called.parent.kind is ContractKind.INTERFACE:
            return

        self._detections.append(
            DetectorResult(
                Detection(node, "Usage of deprecated ChainLink API"),
                DetectorImpact.WARNING,
                DetectorConfidence.HIGH,
                uri=generate_detector_uri(
                    name="chainlink-deprecated-function",
                    version=self.extra["package_versions"]["eth-wake"],
                ),
            )
        )

    @detector.command(name="chainlink-deprecated-function")
    def cli(self) -> None:
        """
        Deprecated ChainLink function called on AggregatorInterface
        """
