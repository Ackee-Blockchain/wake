from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, FrozenSet, Iterable, Set

import networkx as nx
from Crypto.Hash import BLAKE2b

from wake.compiler.source_path_resolver import SourcePathResolver
from wake.config import WakeConfig
from wake.core.solidity_version import SolidityVersionRanges

# pyright: reportGeneralTypeIssues=false


class CompilationUnit:
    __unit_graph: nx.DiGraph
    __version_ranges: SolidityVersionRanges
    __hash: bytes
    __paths_to_source_unit_names: DefaultDict[Path, Set[str]]

    def __init__(self, unit_graph: nx.DiGraph, version_ranges: SolidityVersionRanges):
        self.__unit_graph = unit_graph
        self.__version_ranges = version_ranges
        self.__paths_to_source_unit_names = defaultdict(set)

        self.__hash = bytes([0] * 32)
        for node in unit_graph.nodes:
            source_unit_name_hash = BLAKE2b.new(
                data=str(node).encode("utf-8"), digest_bits=256
            ).digest()
            self.__hash = bytes(
                a ^ b ^ c
                for a, b, c in zip(
                    self.__hash, source_unit_name_hash, unit_graph.nodes[node]["hash"]
                )
            )

            path = unit_graph.nodes[node]["path"]
            self.__paths_to_source_unit_names[path].add(node)

    def __len__(self):
        return len(self.__unit_graph.nodes)

    def __str__(self):
        return "\n".join(
            str(self.__unit_graph.nodes[node]["path"])
            for node in self.__unit_graph.nodes
        )

    def draw(self, path: Path):
        reversed_graph = nx.reverse(self.__unit_graph, False)
        nx.nx_pydot.write_dot(reversed_graph, path)

    def source_unit_name_to_path(self, source_unit_name: str) -> Path:
        return self.__unit_graph.nodes[source_unit_name]["path"]

    def path_to_source_unit_names(self, path: Path) -> FrozenSet[str]:
        return frozenset(self.__paths_to_source_unit_names[path])

    def contains_unresolved_file(
        self, files: Iterable[Path], config: WakeConfig
    ) -> bool:
        unresolved_imports: Set[str] = set()
        for node in self.__unit_graph.nodes:
            unresolved_imports.update(
                self.__unit_graph.nodes[node]["unresolved_imports"]
            )

        source_path_resolver = SourcePathResolver(config)

        for unresolved_import in unresolved_imports:
            for file in files:
                if source_path_resolver.matches(unresolved_import, file):
                    return True
        return False

    @property
    def files(self) -> FrozenSet[Path]:
        return frozenset(
            self.__unit_graph.nodes[node]["path"] for node in self.__unit_graph.nodes
        )

    @property
    def source_unit_names(self) -> FrozenSet[str]:
        return frozenset(self.__unit_graph.nodes)

    @property
    def versions(self) -> SolidityVersionRanges:
        return self.__version_ranges

    @property
    def hash(self) -> bytes:
        return self.__hash

    @property
    def graph(self) -> nx.DiGraph:
        return self.__unit_graph
