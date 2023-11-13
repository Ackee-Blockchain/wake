from __future__ import annotations

from typing import List, Tuple

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.printers import Printer, printer


class TokensPrinter(Printer):
    erc20_functions = {
        b"\x18\x16\x0d\xdd",  # totalSupply()
        b"\x70\xa0\x82\x31",  # balanceOf(address)
        b"\xa9\x05\x9c\xbb",  # transfer(address,uint256)
        b"\xdd\x62\xed\x3e",  # allowance(address,address)
        b"\x09\x5e\xa7\xb3",  # approve(address,uint256)
        b"\x23\xb8\x72\xdd",  # transferFrom(address,address,uint256)
    }
    erc20_events = {
        # Transfer(address,address,uint256)
        b"\xdd\xf2\x52\xad\x1b\xe2\xc8\x9b\x69\xc2\xb0\x68\xfc\x37\x8d\xaa\x95\x2b\xa7\xf1\x63\xc4\xa1\x16\x28\xf5\x5a\x4d\xf5\x23\xb3\xef",
        # Approval(address,address,uint256)
        b"\x8c\x5b\xe1\xe5\xeb\xec\x7d\x5b\xd1\x4f\x71\x42\x7d\x1e\x84\xf3\xdd\x03\x14\xc0\xf7\xb2\x29\x1e\x5b\x20\x0a\xc8\xc7\xc3\xb9\x25",
    }
    erc721_functions = {
        b"\x70\xa0\x82\x31",  # balanceOf(address)
        b"\x63\x52\x21\x1e",  # ownerOf(uint256)
        b"\x42\x84\x2e\x0e",  # safeTransferFrom(address,address,uint256)
        b"\xb8\x8d\x4f\xde",  # safeTransferFrom(address,address,uint256,bytes)
        b"\x23\xb8\x72\xdd",  # transferFrom(address,address,uint256)
        b"\x09\x5e\xa7\xb3",  # approve(address,uint256)
        b"\x08\x18\x12\xfc",  # getApproved(uint256)
        b"\xa2\x2c\xb4\x65",  # setApprovalForAll(address,bool)
        b"\xe9\x85\xe9\xc5",  # isApprovedForAll(address,address)
    }
    erc721_events = {
        # Transfer(address,address,uint256)
        b"\xdd\xf2\x52\xad\x1b\xe2\xc8\x9b\x69\xc2\xb0\x68\xfc\x37\x8d\xaa\x95\x2b\xa7\xf1\x63\xc4\xa1\x16\x28\xf5\x5a\x4d\xf5\x23\xb3\xef",
        # Approval(address,address,uint256)
        b"\x8c\x5b\xe1\xe5\xeb\xec\x7d\x5b\xd1\x4f\x71\x42\x7d\x1e\x84\xf3\xdd\x03\x14\xc0\xf7\xb2\x29\x1e\x5b\x20\x0a\xc8\xc7\xc3\xb9\x25",
        # ApprovalForAll(address,address,bool)
        b"\x17\x30\x7e\xab\x39\xab\x61\x07\xe8\x89\x98\x45\xad\x3d\x59\xbd\x96\x53\xf2\x00\xf2\x20\x92\x04\x89\xca\x2b\x59\x37\x69\x6c\x31",
    }
    erc1155_functions = {
        b"\xf2\x42\x43\x2a",  # safeTransferFrom(address,address,uint256,uint256,bytes)
        b"\x2e\xb2\xc2\xd6",  # safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)
        b"\x00\xfd\xd5\x8e",  # balanceOf(address,uint256)
        b"\x4e\x12\x73\xf4",  # balanceOfBatch(address[],uint256[])
        b"\xa2\x2c\xb4\x65",  # setApprovalForAll(address,bool)
        b"\xe9\x85\xe9\xc5",  # isApprovedForAll(address,address)
    }
    erc1155_events = {
        # ApproveForAll(address,address,bool)
        b"\x17\x30\x7e\xab\x39\xab\x61\x07\xe8\x89\x98\x45\xad\x3d\x59\xbd\x96\x53\xf2\x00\xf2\x20\x92\x04\x89\xca\x2b\x59\x37\x69\x6c\x31",
        # URI(string,uint256)
        b"\x6b\xb7\xff\x70\x86\x19\xba\x06\x10\xcb\xa2\x95\xa5\x85\x92\xe0\x45\x1d\xee\x26\x22\x93\x8c\x87\x55\x66\x76\x88\xda\xf3\x52\x9b",
        # TransferSingle(address,address,address,uint256,uint256)
        b"\xc3\xd5\x81\x68\xc5\xae\x73\x97\x73\x1d\x06\x3d\x5b\xbf\x3d\x65\x78\x54\x42\x73\x43\xf4\xc0\x83\x24\x0f\x7a\xac\xaa\x2d\x0f\x62",
        # TransferBatch(address,address,address,uint256[],uint256[])
        b"\x4a\x39\xdc\x06\xd4\xc0\xdb\xc6\x4b\x70\xaf\x90\xfd\x69\x8a\x23\x3a\x51\x8a\xa5\xd0\x7e\x59\x5d\x98\x3b\x8c\x05\x26\xc8\xf7\xfb",
    }

    _erc20: bool
    _erc721: bool
    _erc1155: bool
    _erc20_threshold: int
    _erc721_threshold: int
    _erc1155_threshold: int
    _interface: bool
    _abstract: bool
    _table_style: str
    _header_style: str
    _style: str
    _contracts: List[Tuple[ir.ContractDefinition, str]]

    def __init__(self):
        self._contracts = []

    def print(self) -> None:
        from rich.table import Table

        table = Table(title="Tokens", style=self._table_style)
        table.add_column("Contract", header_style=self._header_style)
        table.add_column("Type", header_style=self._header_style)
        table.add_column("Location", header_style=self._header_style)

        for contract, type in sorted(
            self._contracts, key=lambda x: x[0].source_unit.source_unit_name
        ):
            table.add_row(
                contract.name,
                type,
                f"[link={self.generate_link(contract)}]{contract.source_unit.source_unit_name}[/]",
                style=self._style,
            )

        print(table)

    def visit_contract_definition(self, node: ir.ContractDefinition):
        from wake.analysis.interface import find_interface

        if not self._abstract and node.abstract:
            return
        if not self._interface and node.kind == ir.enums.ContractKind.INTERFACE:
            return

        erc1155 = find_interface(node, self.erc1155_functions, self.erc1155_events)
        if len(erc1155) >= self._erc1155_threshold:
            if self._erc1155:
                self._contracts.append((node, "ERC-1155"))
            return

        erc721 = find_interface(node, self.erc721_functions, self.erc721_events)
        if len(erc721) >= self._erc721_threshold:
            if self._erc721:
                self._contracts.append((node, "ERC-721"))
            return

        erc20 = find_interface(node, self.erc20_functions, self.erc20_events)
        if len(erc20) >= self._erc20_threshold:
            if self._erc20:
                self._contracts.append((node, "ERC-20"))
            return

    @printer.command(name="tokens")
    @click.option(
        "--erc20/--no-erc20", is_flag=True, default=True, help="Print ERC-20 tokens."
    )
    @click.option(
        "--erc721/--no-erc721", is_flag=True, default=True, help="Print ERC-721 tokens."
    )
    @click.option(
        "--erc1155/--no-erc1155",
        is_flag=True,
        default=True,
        help="Print ERC-1155 tokens.",
    )
    @click.option(
        "--erc20-threshold",
        type=click.IntRange(1, len(erc20_functions) + len(erc20_events)),
        default=4,
        help="Number of ERC-20 functions/events required to consider a contract an ERC-20 token",
    )
    @click.option(
        "--erc721-threshold",
        type=click.IntRange(1, len(erc721_functions) + len(erc721_events)),
        default=6,
        help="Number of ERC-721 functions/events required to consider a contract an ERC-721 token",
    )
    @click.option(
        "--erc1155-threshold",
        type=click.IntRange(1, len(erc1155_functions) + len(erc1155_events)),
        default=4,
        help="Number of ERC-1155 functions/events required to consider a contract an ERC-1155 token",
    )
    @click.option(
        "--interface/--no-interface",
        is_flag=True,
        default=False,
        help="Print interfaces.",
    )
    @click.option(
        "--abstract/--no-abstract",
        is_flag=True,
        default=False,
        help="Print abstract contracts.",
    )
    @click.option("--table-style", type=str, default="", help="Style for the table.")
    @click.option(
        "--header-style", type=str, default="", help="Style for the table header."
    )
    @click.option(
        "--style", type=str, default="cyan", help="Style for the table cells."
    )
    def cli(
        self,
        erc20: bool,
        erc721: bool,
        erc1155: bool,
        erc20_threshold: int,
        erc721_threshold: int,
        erc1155_threshold: int,
        interface: bool,
        abstract: bool,
        table_style: str,
        header_style: str,
        style: str,
    ) -> None:
        """
        Print all tokens in the analyzed contracts.
        """
        self._erc20 = erc20
        self._erc721 = erc721
        self._erc1155 = erc1155
        self._erc20_threshold = erc20_threshold
        self._erc721_threshold = erc721_threshold
        self._erc1155_threshold = erc1155_threshold
        self._interface = interface
        self._abstract = abstract
        self._table_style = table_style
        self._header_style = header_style
        self._style = style
