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


class AbiEncodeWithSignatureDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        from parsimonious import Grammar

        self._detections = []

        # inspired by https://github.com/ethereum/eth-abi/blob/master/eth_abi/grammar.py
        self._grammar = Grammar(
            r"""
            type = tuple_type / basic_type
            
            tuple_type = "(" type ("," type)* ")"
            
            basic_type = base_type array_suffix*
            base_type = "address" / "bool" / "string" / "function" / int_type / uint_type / fixed_type / ufixed_type / bytesN_type / "bytes"
            
            int_type = "int" int_size
            uint_type = "uint" int_size
            int_size = "256" / "248" / "240" / "232" / "224" / "216" / "208" / "200" / "192" / "184" / "176" / "168" / "160" / "152" / "144" / "136" / "128" / "120" / "112" / "104" / "96" / "88" / "80" / "72" / "64" / "56" / "48" / "40" / "32" / "24" / "16" / "8"
            
            fixed_type = "fixed" fixed_size "x" fixed_decimal
            ufixed_type = "ufixed" fixed_size "x" fixed_decimal
            fixed_size = "256" / "248" / "240" / "232" / "224" / "216" / "208" / "200" / "192" / "184" / "176" / "168" / "160" / "152" / "144" / "136" / "128" / "120" / "112" / "104" / "96" / "88" / "80" / "72" / "64" / "56" / "48" / "40" / "32" / "24" / "16" / "8"
            fixed_decimal = "80" / ~"[1-7][0-9]" / ~"[1-9]"

            bytesN_type = "bytes" bytesN_size
            bytesN_size = "32" / "31" / "30" / ~"[1-2][0-9]" / ~"[1-9]"

            array_suffix = ("[" array_len "]") / ("[" "]")
            array_len = ~"[1-9][0-9]*"
            """
        )

    def detect(self) -> List[DetectorResult]:
        return self._detections

    def visit_member_access(self, node: ir.MemberAccess):
        from parsimonious import ParseError

        if (
            node.referenced_declaration
            != ir.enums.GlobalSymbol.ABI_ENCODE_WITH_SIGNATURE
        ):
            return

        parent = node.parent
        if not isinstance(parent, ir.FunctionCall):
            return

        arg0 = parent.arguments[0]
        if (
            not isinstance(arg0, ir.Literal)
            or arg0.kind != ir.enums.LiteralKind.STRING
            or arg0.value is None
        ):
            return

        try:
            signature_args = "(" + "(".join(arg0.value.split("(")[1:])
            if signature_args == "()":
                return
            self._grammar.parse(signature_args)
        except (IndexError, ParseError):
            self._detections.append(
                DetectorResult(
                    detection=Detection(
                        ir_node=arg0,
                        message="abi.encodeWithSignature() argument is invalid ABI signature",
                    ),
                    confidence=DetectorConfidence.HIGH,
                    impact=DetectorImpact.MEDIUM,
                    uri=generate_detector_uri(
                        name="abi-encode-with-signature",
                        version=self.extra["package_versions"]["eth-wake"],
                    ),
                )
            )

    @detector.command(name="abi-encode-with-signature")
    def cli(self) -> None:
        """
        Invalid ABI signature in abi.encodeWithSignature() arguments
        """
