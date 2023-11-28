from __future__ import annotations

from collections import deque
from typing import Any, Callable, Iterator, Optional, Tuple, Union

import networkx as nx
from typing_extensions import Literal


def graph_iter(
    graph: nx.DiGraph,
    start: Any,
    direction: Union[Literal["in"], Literal["out"], Literal["both"]],
    include_start: bool = True,
    node_predicate_terminates_search: bool = True,
    node_predicate: Optional[Callable[[Any], bool]] = None,
    edge_predicate: Optional[Callable[[Tuple[Any, Any, Any]], bool]] = None,
) -> Iterator[Any]:
    """
    Iterate over the nodes of a directional graph, optionally filtering by node and edge predicates.
    """
    if node_predicate is None:
        node_predicate = lambda _: True
    if edge_predicate is None:
        edge_predicate = lambda _: True

    if include_start:
        if not node_predicate(start):
            if node_predicate_terminates_search:
                return
        else:
            yield start

    queue = deque([start])
    visited = {start}

    while queue:
        node = queue.popleft()

        if direction in ("in", "both"):
            for (
                from_,
                _,
                data,
            ) in graph.in_edges(  # pyright: ignore reportGeneralTypeIssues
                node, data=True  # pyright: ignore reportGeneralTypeIssues
            ):
                if from_ not in visited and edge_predicate((from_, node, data)):
                    pred = node_predicate(from_)
                    if pred:
                        yield from_

                    if pred or not node_predicate_terminates_search:
                        queue.append(from_)
                        visited.add(from_)

        if direction in ("out", "both"):
            for (
                _,
                to,
                data,
            ) in graph.out_edges(  # pyright: ignore reportGeneralTypeIssues
                node, data=True  # pyright: ignore reportGeneralTypeIssues
            ):
                if to not in visited and edge_predicate((node, to, data)):
                    pred = node_predicate(to)
                    if pred:
                        yield to

                    if pred or not node_predicate_terminates_search:
                        queue.append(to)
                        visited.add(to)
