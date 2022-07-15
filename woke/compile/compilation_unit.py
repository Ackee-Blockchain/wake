from pathlib import Path
from typing import Dict, FrozenSet, Iterable, Set

import networkx as nx
from Cryptodome.Hash import BLAKE2b

from woke.compile.source_path_resolver import SourcePathResolver
from woke.config import WokeConfig
from woke.core.solidity_version import SolidityVersionRanges


class CompilationUnit:
    __unit_graph: nx.DiGraph
    __version_ranges: SolidityVersionRanges
    __hash: bytes
    __source_unit_names_to_paths: Dict[str, Path]

    def __init__(self, unit_graph: nx.DiGraph, version_ranges: SolidityVersionRanges):
        self.__unit_graph = unit_graph
        self.__version_ranges = version_ranges
        self.__source_unit_names_to_paths = {}

        self.__hash = bytes([0] * 32)
        for node in unit_graph.nodes:
            self.__hash = bytes(
                a ^ b for a, b in zip(self.__hash, unit_graph.nodes[node]["hash"])
            )
            self.__source_unit_names_to_paths[
                unit_graph.nodes[node]["source_unit_name"]
            ] = node

    def __len__(self):
        return len(self.__unit_graph.nodes)

    def __str__(self):
        return "\n".join(str(path) for path in self.__unit_graph.nodes)

    def draw(self, path: Path):
        labels = {
            node: data["source_unit_name"]
            for node, data in self.__unit_graph.nodes.items()
        }
        relabeled_graph = nx.reverse(nx.relabel_nodes(self.__unit_graph, labels), False)
        nx.nx_pydot.write_dot(relabeled_graph, path)

    def source_unit_name_to_path(self, source_unit_name: str) -> Path:
        return self.__source_unit_names_to_paths[source_unit_name]

    def contains_unresolved_file(
        self, files: Iterable[Path], config: WokeConfig
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
        return frozenset(self.__unit_graph.nodes)

    @property
    def source_unit_names(self) -> FrozenSet[str]:
        return frozenset(
            self.__unit_graph.nodes[node]["source_unit_name"]
            for node in self.__unit_graph.nodes
        )

    @property
    def versions(self) -> SolidityVersionRanges:
        return self.__version_ranges

    @property
    def hash(self) -> bytes:
        return self.__hash

    @property
    def graph(self) -> nx.DiGraph:
        return self.__unit_graph
