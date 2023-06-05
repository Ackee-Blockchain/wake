import asyncio
import sys
import time
from pathlib import Path
from typing import Set, Tuple, NamedTuple, List
from typing_extensions import Literal, TypedDict
from dataclasses import dataclass, field

import rich_click as click

# There are two main GoJS model types (and their corresponding diagram types)
# that we'll be using in Woke Dash: TreeModel and GraphLinksModel. TreeModel is
# used for the left-hand side diagram, which will show the "extended" file
# explorer, eg:
#
# /
# └── usr
#     └── repos
#          └── uniswap-v3
#              └── contracts
#                 └── Pool.sol
#                     └── Pool
#                         └── swap
#
# (The reason we go from the root '/' is that a user could technically have a
# dependency outside of the current repository)
# GraphLinksModel is used for the right-hand side diagram, which currently shows
# the call graph (but could be extended to show other graphs, eg inheritance).
# Now, the two models work quite differently:
#
# - TreeModel expects (in JS) an array of nodes, each having a unique "key", and
# all nodes except for the root have a "parent" field. We consider the key to be
# the path/contract_name.function_signature (for functions). We also add a "text"
# field to each node, which is what is displayed in the diagram (this doesn't
# include the function arguments).
#
# - GraphLinksModel expects also an array of nodes, each having a unique "key",
# and each node having on optional "group: str" and "isGroup: bool" field
# (yes, groups can be nested).
#
# Now, we are given a list of source units (each an AST of a Solidity file). How
# can we construct the TreeModel from this? Keep in mind we need one, and only
# one, node for every "part" of all source unit paths. There are two solutions
# that come to mind:
#
# 1. We can maintain an intermediate dictionary with intermediate parts.
#    Something like
#
# interm_dict = dict(
#     usr=dict(
#         repos=dict(
#             uniswap-v3=dict(
#                 contracts=dict(
#                     Pool=["swap"],
#                 ),
#             ),
#         ),
#     ),
# )
#
# The downside of this technique is that we can't attach metadata to the nodes,
# such as what type of node it is (eg "folder", "file", etc). We could make the
# keys NamedTuples (dictionaries are not hashable, tuples are). The second
# downside is that we wound need to convert the dictionary to the final format
# (an array).
#
# 2. Instead, we could use a set (possibly of these NamedTuples) to store the
#    visited paths. The downside is sets are unordered, but we want our
#    funnctions (and other nodes) to be ordered by declaration in the file
#    explorer. So we'll define an OrderedSet.
#
# A few more notes:
#
# 1. We'll separate the declarations of our model (which define the objects)
#    from the edges (which are graph-specific), so it is easy to add other
#    graphs in the future.
# 2. We'll prefer dataclasses over NamedTuples, we'll use a NT only for the
#    folders.
# 3. The root node is special, because it musn't have a parent (not even
#    None/null), so we'll define it separately.
# 4. The edges of our call graph expect a "from" and "to" field. We'll use the
#    functional notation of a TypedDict for this, because "from" is a reserved
#    keyword in Python.

class RootNode(NamedTuple):
    key: str
    text: str
    type: Literal["folder"] = "folder"
    checked: Literal[True] = True

class FolderNode(NamedTuple):
    key: str
    text: str
    parent: str
    type: Literal["folder"] = "folder"
    checked: Literal[True] = True

@dataclass
class FileNode:
    key: str
    text: str
    parent: str
    type: Literal["file"] = "file"
    checked: Literal[True] = True

@dataclass
class ContractNode:
    key: str
    text: str
    parent: str
    type: Literal["contract"] = "contract"
    isGroup: Literal[True] = True

@dataclass
class FunctionNode:
    key: str
    text: str
    parent: str
    group: str
    type: Literal["function"] = "function"
    checked: Literal[True] = True

Edge = TypedDict("Edge", {"from": str, "to": str})

@dataclass
class Edges:
    call_graph: List[Edge] = field(default_factory=list)

@dataclass
class Out:
    folders: List[FolderNode] = field(default_factory=list)
    files: List[FileNode] = field(default_factory=list)
    contracts: List[ContractNode] = field(default_factory=list)
    functions: List[FunctionNode] = field(default_factory=list)
    edges: Edges = field(default_factory=Edges)

class OrderedSet:
    def __init__(self):
        self._set = set()
        self._list = []

    def add(self, item):
        if item not in self._set:
            self._set.add(item)
            self._list.append(item)

    def __iter__(self):
        return iter(self._list)

    def __len__(self):
        return len(self._list)

    def __contains__(self, item):
        return item in self._set

    def __getitem__(self, item):
        return self._list[item]

    def __repr__(self):
        return repr(self._list)

    def __eq__(self, other):
        return self._list == other._list

    def __hash__(self):
        return hash(self._list)


@click.command(name="dash")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--no-artifacts", is_flag=True, default=False, help="Do not write build artifacts."
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force recompile the project without previous build artifacts.",
)
@click.pass_context
def run_dash(
    ctx: click.Context, paths: Tuple[str], no_artifacts: bool, force: bool
) -> None:
    """Visualize your project in the browser."""

    from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
    from ..compiler.build_data_model import ProjectBuild
    from ..compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
    from ..config import WokeConfig
    from ..utils.file_utils import is_relative_to
    from .console import console

    config = WokeConfig()
    config.load_configs()  # load ~/.woke/config.toml and ./woke.toml

    sol_files: Set[Path] = set()
    start = time.perf_counter()
    with console.status("[bold green]Searching for *.sol files...[/]"):
        if len(paths) == 0:
            for file in config.project_root_path.rglob("**/*.sol"):
                if (
                    not any(
                        is_relative_to(file, p)
                        for p in config.compiler.solc.ignore_paths
                    )
                    and file.is_file()
                ):
                    sol_files.add(file)
        else:
            for p in paths:
                path = Path(p)
                if path.is_file():
                    if not path.match("*.sol"):
                        raise ValueError(f"Argument `{p}` is not a Solidity file.")
                    sol_files.add(path)
                elif path.is_dir():
                    for file in path.rglob("**/*.sol"):
                        if (
                            not any(
                                is_relative_to(file, p)
                                for p in config.compiler.solc.ignore_paths
                            )
                            and file.is_file()
                        ):
                            sol_files.add(file)
                else:
                    raise ValueError(f"Argument `{p}` is not a file or directory.")
    end = time.perf_counter()
    console.log(
        f"[green]Found {len(sol_files)} *.sol files in [bold green]{end - start:.2f} s[/bold green][/]"
    )

    compiler = SolidityCompiler(config)

    if not force:
        compiler.load(console=console)

    build: ProjectBuild
    errors: Set[SolcOutputError]
    build, errors = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=not no_artifacts,
            force_recompile=force,
            console=console,
        )
    )

    errored = any(
        error.severity == SolcOutputErrorSeverityEnum.ERROR for error in errors
    )
    if errored:
        sys.exit(1)
