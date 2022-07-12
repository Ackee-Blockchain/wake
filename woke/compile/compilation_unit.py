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
    __blake2b_digest: bytes
    __source_unit_names_to_paths: Dict[str, Path]

    def __init__(self, unit_graph: nx.DiGraph, version_ranges: SolidityVersionRanges):
        self.__unit_graph = unit_graph
        self.__version_ranges = version_ranges
        self.__source_unit_names_to_paths = {}

        sorted_nodes = sorted(
            unit_graph, key=(lambda node: unit_graph.nodes[node]["source_unit_name"])
        )
        blake2 = BLAKE2b.new(digest_bits=256)

        for node in sorted_nodes:
            blake2.update(unit_graph.nodes[node]["hash"])
            self.__source_unit_names_to_paths[
                unit_graph.nodes[node]["source_unit_name"]
            ] = node
        self.__blake2b_digest = blake2.digest()

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
    def blake2b_digest(self) -> bytes:
        return self.__blake2b_digest

    @property
    def blake2b_hexdigest(self) -> str:
        return self.blake2b_digest.hex()

    @property
    def graph(self) -> nx.DiGraph:
        return self.__unit_graph
