from __future__ import annotations

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class LspOpenzeppelinDocsPrinter(Printer):
    execution_mode = "lsp"

    def __init__(self):
        from wake.utils.openzeppelin import get_contracts_package_version

        self._openzeppelin_version = get_contracts_package_version(self.config)

    def print(self) -> None:
        pass

    def visit_contract_definition(self, node: ir.ContractDefinition) -> None:
        if self._openzeppelin_version is None or self._openzeppelin_version < "2.0.0":
            return

        source_unit = node.parent
        version_string = f"{self._openzeppelin_version.major}.x"
        url_base = f"https://docs.openzeppelin.com/contracts/{version_string}"
        doc_url = None
        api_doc_url = None

        if "openzeppelin/contracts/access" in source_unit.source_unit_name:
            doc_url = "access-control"
            api_doc_url = "access"
        elif "openzeppelin/contracts/crosschain" in source_unit.source_unit_name:
            doc_url = "crosschain"
            api_doc_url = "crosschain"
        elif "openzeppelin/contracts/finance" in source_unit.source_unit_name:
            if node.name == "PaymentSplitter":
                doc_url = "utilities#payment"
            api_doc_url = "finance"
        elif "openzeppelin/contracts/governance" in source_unit.source_unit_name:
            doc_url = "governance"
            api_doc_url = "governance"
        elif (
            "openzeppelin/contracts/interfaces" in source_unit.source_unit_name
            or "openzeppelin/contracts/token" in source_unit.source_unit_name
        ):
            if "ERC20" in node.name:
                doc_url = "erc20"
                api_doc_url = "token/erc20"
            elif "ERC721" in node.name:
                doc_url = "erc721"
                api_doc_url = "token/erc721"
            elif "ERC777" in node.name:
                doc_url = "erc777"
                api_doc_url = "token/erc777"
            elif "ERC1155" in node.name:
                doc_url = "erc1155"
                api_doc_url = "token/erc1155"
            elif node.name.startswith("I"):
                api_doc_url = "interfaces"
            else:
                api_doc_url = "token/common"
        elif "openzeppelin/contracts/metatx" in source_unit.source_unit_name:
            api_doc_url = "metatx"
        elif "openzeppelin/contracts/proxy" in source_unit.source_unit_name:
            api_doc_url = "proxy"
        elif "openzeppelin/contracts/security" in source_unit.source_unit_name:
            if node.name == "PullPayment":
                doc_url = "utilities#payment"
            api_doc_url = "security"
        elif "openzeppelin/contracts/utils" in source_unit.source_unit_name:
            doc_url = "utilities"
            api_doc_url = "utils"
        elif "openzeppelin/contracts/GSN" in source_unit.source_unit_name:
            doc_url = "gsn"
            api_doc_url = "gsn"
        elif "openzeppelin/contracts/cryptography" in source_unit.source_unit_name:
            doc_url = "utilities#cryptography"
            api_doc_url = "cryptography"
        elif "openzeppelin/contracts/drafts" in source_unit.source_unit_name:
            api_doc_url = "drafts"
        elif "openzeppelin/contracts/math" in source_unit.source_unit_name:
            doc_url = "utilities#math"
            api_doc_url = "math"
        elif "openzeppelin/contracts/payment" in source_unit.source_unit_name:
            doc_url = "utilities#payment"
            api_doc_url = "payment"
        elif "openzeppelin/contracts/presets" in source_unit.source_unit_name:
            if "ERC20" in node.name:
                doc_url = "erc20#Presets"
            elif "ERC721" in node.name:
                doc_url = "erc721#Presets"
            elif "ERC777" in node.name:
                doc_url = "erc777#Presets"
            elif "ERC1155" in node.name:
                doc_url = "erc1155#Presets"
            api_doc_url = "presets"

        hover_text = ""
        if doc_url is not None:
            hover_text += f"\n\n[OpenZeppelin documentation]({url_base}/{doc_url})"
        if api_doc_url is not None:
            hover_text += f"\n\n[OpenZeppelin API documentation]({url_base}/api/{api_doc_url}#{node.name})"

        assert self.lsp_provider is not None
        self.lsp_provider.add_hover(node, hover_text)

    @printer.command(name="lsp-openzeppelin-docs")
    def cli(self) -> None:
        pass
