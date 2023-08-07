import asyncio
import sys
import time
from pathlib import Path
from typing import (
    Set,
    Tuple,
    NamedTuple,
    List,
    TypeVar,
    Generic,
    Iterator,
    Union,
    Optional,
    Dict,
)
from typing_extensions import Literal, NewType, TypedDict
from dataclasses import dataclass, field, asdict
import json
import shutil
import time
import platform

import rich_click as click
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.meta import inheritance_specifier

from woke.ast.ir.statement.inline_assembly import ExternalReference
from woke.ast.ir.meta.identifier_path import IdentifierPathPart
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.declaration.modifier_definition import ModifierDefinition
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.variable_declaration import VariableDeclaration
from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.enums import ContractKind, FunctionKind, Visibility, StateMutability
from woke.ast.types import Modifier

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
# GraphLinksModel is used for the right-hand side diagram, which currently
# shows the reference graph (but could be extended to show other graphs, eg
# inheritance). Now, the two models work quite differently:
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
# 5. We also need to handle top-level functions. Unfortunately, we can't just
#    use None as the `group` (GoJS would throw). So we'll need a new node type
#    for that.
# 6. We also need to handle function references in contract storage
#    initiliazation (eg `uint x = computeX()`).
# 7. We also need to add arguments to our functions to ensure they are unique.
# 8. On the other hand, we don't need to consider references in assembly blocks,
#    because they cannot contain Solidity functions.
# 9. Finally, we technically should handle a function reference vs. an actual
#    call. That said, it's better to keep it simple and just consider all
#    references: so it's actually a reference_graph. ;-)
# 10. For declarations, we use the `path` field, the first element of the
#     tuples in `build.item()`. However, for references we use the `file` field
#     of functions and contracts. We assume they are the same.
# 11. Possible improvements: handle references in modifiers and storage
#     initialization. Handle child_functions that are `VariableDeclaration`s.
#     Handle calls to base constructors.
#     Put modifiers, base_functions and child_functions as links. 
#     Include function complexity and references to state variables.

Key = NewType("Key", str)


class RootFolderNode(NamedTuple):
    key: Key
    name: str
    node_type: Literal["folder"] = "folder"
    checked: Literal[True] = True


class FolderNode(NamedTuple):
    key: Key
    name: str
    parent: Key
    node_type: Literal["folder"] = "folder"
    checked: Literal[True] = True


@dataclass
class FileNode:
    key: Key
    name: str
    parent: Key
    node_type: Literal["file"] = "file"
    checked: Literal[True] = True


@dataclass
class ContractNode:
    key: Key
    name: str
    parent: Key
    kind: ContractKind
    fully_implemented: Optional[bool]
    node_type: Literal["contract"] = "contract"
    checked: Literal[True] = True
    isGroup: Literal[True] = True


@dataclass
class FunctionBase:
    """Base dataclass for FreeFunctionNode and FunctionNode."""

    key: Key
    signature: str
    name: str
    name_with_params: str
    declaration_string: str
    kind: FunctionKind
    visibility: Visibility
    state_mutability: StateMutability
    modifiers: List[Key]
    base_functions: List[Key]
    child_functions: List[Key]
    parent: Key
    # We can't have fields without default value _after_ fields with default
    # values. We also can't override fields in a subclass.
    # node_type: Union[Literal["function"], Literal["free_function"]]
    checked: Literal[True]


@dataclass
class FreeFunctionNode(FunctionBase):
    """Free functions."""

    node_type: Literal["free_function"] = "free_function"


@dataclass
class FunctionNode(FunctionBase):
    """Contract functions."""

    contract: Key
    node_type: Literal["function"] = "function"


# We use a TypedDict because "from" is a reserved keyword in Python.
Link = TypedDict("Link", {"from": Key, "to": Key})
# We'll also need a hashable version of a Link, for the inheritance graph.
HashableLink = NamedTuple("HashableLink", [("from_", Key), ("to", Key)])


@dataclass
class Links:
    contract_inheritance: List[Link] = field(default_factory=list)
    function_inheritance: List[Link] = field(default_factory=list)
    function_references: List[Link] = field(default_factory=list)

@dataclass
class Metadata:
    project_root_path: str = ""
    project_name: str = ""


@dataclass
class WokeDashModel:
    # This will have the same shape as FolderNode, but we'll convert it to a
    # dictionary at the end. Before that, we'll keep it a NamedTuple so it's
    # hashable.
    folders: List[Dict] = field(default_factory=list)
    files: List[FileNode] = field(default_factory=list)
    free_functions: List[FreeFunctionNode] = field(default_factory=list)
    contracts: List[ContractNode] = field(default_factory=list)
    functions: List[FunctionNode] = field(default_factory=list)
    links: Links = field(default_factory=Links)
    metadata: Metadata = field(default_factory=Metadata)


T = TypeVar("T")


class OrderedSet(Generic[T]):
    _set: Set[T]
    _list: List[T]

    def __init__(self):
        self._set = set()
        self._list = []

    def add(self, item: T):
        if item not in self._set:
            self._set.add(item)
            self._list.append(item)

    def __iter__(self) -> Iterator[T]:
        return iter(self._list)

    def __len__(self) -> int:
        return len(self._list)

    def __contains__(self, item: T):
        return item in self._set

    def __getitem__(self, item: int) -> T:
        return self._list[item]

    def __repr__(self) -> str:
        return repr(self._list)

    def __eq__(self, other) -> bool:
        return self._list == other._list

    def __hash__(self) -> int:
        return hash(self._list)


class ProcessedFunction(NamedTuple):
    modifiers: List[Key]
    base_functions: List[Key]
    child_functions: List[Key]
    signature: str
    name_with_params: str


def process_function(function: FunctionDefinition) -> ProcessedFunction:
    modifiers: List[Key] = []
    for modifier_invocation in function.modifiers:
        modifier = modifier_invocation.modifier_name.referenced_declaration
        # modifier can also be a ContractDefinition (if it's a call to a base constructor)
        # We omit that for now.
        if isinstance(modifier, ModifierDefinition):
            modifiers.append(get_modifier_key(modifier))
        else:
            continue

    base_functions = []
    for base_function in function.base_functions:
        assert isinstance(base_function, FunctionDefinition)
        base_functions.append(get_function_key(base_function))

    child_functions = []
    for child_function in function.child_functions:
        # `child_function`s can be a variable declaration
        # (See the docs for `FunctionDefinition.child_functions`.)
        # We're going to skip those.
        if isinstance(child_function, VariableDeclaration):
            continue
        elif isinstance(child_function, FunctionDefinition):
            child_functions.append(get_function_key(child_function))
        else:
            assert False

    signature = get_function_signature(function)
    name_with_params = get_function_name_with_params(function)

    return ProcessedFunction(
        modifiers,
        base_functions,
        child_functions,
        signature,
        name_with_params,
    )


def get_modifier_key(modifier: ModifierDefinition) -> Key:
    """There cannot be multiple modifiers with the same name, so we can use the name as the key."""
    # We loop back to get the contract
    contract = modifier
    while not isinstance(contract, ContractDefinition):
        contract = contract.parent
    return Key(f"{modifier.file}.{contract.name}.{modifier.name}")


def get_function_key(function: FunctionDefinition) -> Key:
    """Get a function's (free or contract) key. We use the path, (optionally) contract and ABI signature for the key."""
    function_signature = get_function_signature(function)
    # We loop back to get the contract
    parent = function
    while True:
        parent = parent.parent
        if isinstance(parent, ContractDefinition):
            # Contract function
            return Key(f"{function.file}.{parent.name}.{function_signature}")
        if isinstance(parent, SourceUnit):
            # Free function
            return Key(f"{function.file}.{function_signature}")
    # return Key(str(function.ast_node_id))

def var_decl_to_type_str(variable_declaration: VariableDeclaration) -> str:
    try:
        return variable_declaration.type.abi_type()
    except NotImplementedError:
        return variable_declaration.type_string

def get_function_signature(function: FunctionDefinition) -> str:
    signature = f"{function.name}("
    # if function.name == 'nextInitializedTickWithinOneWord':
    #     breakpoint()
    signature += ",".join(
        var_decl_to_type_str(param) for param in function.parameters.parameters
    )
    signature += ")"
    # breakpoint()
    return signature


def get_function_name_with_params(function: FunctionDefinition) -> str:
    name_with_params = f"{function.name}("
    name_with_params += ", ".join(
        param.name for param in function.parameters.parameters
    )
    name_with_params += ")"
    return name_with_params

def get_contract_key(contract: ContractDefinition) -> Key:
    """Get a contract's key. We use the path and contract name for the key."""
    return Key(f"{contract.file}.{contract.name}")


@click.command(name="dash")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
# default is project_root_path / ".woke-dash" / timestamp
@click.option("--out-directory", type=click.Path(), help="Where `woke dash` will write the files. By default `.woke-dash`.")
@click.option("--use-timestamp-directory", is_flag=True, default=True, help="In the out-directory, create a directory with the current timestamp and a symlink called `latest` that points to it.")
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
    ctx: click.Context, paths: Tuple[str], out_directory: Optional[Path], use_timestamp_directory: bool, no_artifacts: bool, force: bool
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

    model = WokeDashModel()

    folder_ordered_set: OrderedSet[Union[RootFolderNode, FolderNode]] = OrderedSet()
    contract_inheritance_ordered_set: OrderedSet[HashableLink] = OrderedSet()

    for path, source_unit in sorted(build.source_units.items()):
        # First add root folder
        root_folder = RootFolderNode(
            key=Key(path.root),
            name=path.root,
            node_type="folder",
            checked=True,
        )
        folder_ordered_set.add(root_folder)

        # Next, add all other predecessors
        parent = path.parent
        while parent != Path(path.root):
            folder_ordered_set.add(
                FolderNode(
                    key=Key(str(parent)),
                    name=str(parent.name),
                    parent=Key(str(parent.parent)),
                    node_type="folder",
                    checked=True,
                )
            )
            parent = parent.parent

        # Finally, add the file
        model.files.append(
            FileNode(
                key=Key(str(path)),
                name=str(path.name),
                parent=Key(str(path.parent)),
                node_type="file",
                checked=True,
            )
        )

        import os


        os.environ["PYTHONBREAKPOINT"] = "pdbr.set_trace"
        # breakpoint()

        # Next, add free functions
        for function in source_unit.functions:
            assert function.kind is FunctionKind.FREE_FUNCTION

            processed = process_function(function)

            model.free_functions.append(
                FreeFunctionNode(
                    key=Key(f"{path}/{processed.signature}"),
                    signature=processed.signature,
                    name=function.name,
                    name_with_params=processed.name_with_params,
                    declaration_string=function.declaration_string,
                    kind=function.kind,
                    visibility=function.visibility,
                    state_mutability=function.state_mutability,
                    modifiers=processed.modifiers,
                    base_functions=processed.base_functions,
                    child_functions=processed.child_functions,
                    parent=Key(str(path)),
                    node_type="free_function",
                    checked=True,
                )
            )

        # Next, add contract and function nodes
        for contract in source_unit.contracts:
            # breakpoint()
            contract_key = f"{path}.{contract.name}"
            # This is a sanity check so that future references to this contract work
            assert contract_key == get_contract_key(contract)
            model.contracts.append(
                ContractNode(
                    key=Key(contract_key),
                    name=contract.name,
                    parent=Key(str(path)),
                    kind=contract.kind,
                    fully_implemented=contract.fully_implemented,
                    node_type="contract",
                    isGroup=True,
                    checked=True,
                )
            )

            # Add contract inheritance edges
            for inheritance_specifier in contract.base_contracts:
                # breakpoint()
                base_contract = inheritance_specifier.base_name.referenced_declaration
                assert isinstance(base_contract, ContractDefinition)
                contract_inheritance_ordered_set.add(HashableLink(
                    Key(contract_key),
                    get_contract_key(base_contract),
                ))

            # Add contract functions
            for function in contract.functions:
                processed = process_function(function)

                model.functions.append(
                    FunctionNode(
                        key=Key(f"{contract_key}.{processed.signature}"),
                        signature=processed.signature,
                        name=function.name,
                        name_with_params=processed.name_with_params,
                        declaration_string=function.declaration_string,
                        kind=function.kind,
                        visibility=function.visibility,
                        state_mutability=function.state_mutability,
                        modifiers=processed.modifiers,
                        base_functions=processed.base_functions,
                        child_functions=processed.child_functions,
                        parent=Key(contract_key),
                        contract=Key(contract_key),
                        node_type="function",
                        checked=True,
                    )
                )
                
                # Add function references
                for reference in function.references:
                    # at this point, ref is one of:
                    # Identifier, IdentifierPathPart, MemberAccess,
                    # ExternalReference, UnaryOperation, BinaryOperation

                    # ExternalReference is a reference to a Solidity variable in Yul
                    # It cannot represent a call to a Solidity function
                    assert not isinstance(reference, ExternalReference)

                    # IdentifierPathPart is a helper class and technically
                    # not an IR node (it doesn't have `.parent`)
                    if isinstance(reference, IdentifierPathPart):
                        reference = reference.underlying_node

                    # A function may be referenced:
                    #   1. In a function of a contract
                    #   2. In a top-level (free) function
                    #   3. As part of storage initiliazation (`uint x = computeX()`)
                    #   4. In a modifier
                    # We're going to loop through the parents of the ref
                    # to find the contract and function that it belongs to

                    # `referencing_function` will represent this function.
                    # `referencing_contract` will represent this contract.
                    parent = reference
                    while True:
                        parent = parent.parent # type: ignore
                        if isinstance(parent, FunctionDefinition):
                            break
                        if isinstance(parent, ModifierDefinition):
                            # skip references in modifiers
                            break
                        if isinstance(parent, ContractDefinition):
                            # skip references in storage initialization
                            break

                    if isinstance(parent, FunctionDefinition):
                        model.links.function_references.append({
                            "from": Key(get_function_key(function)),
                            "to": Key(get_function_key(parent)),
                        })

                    # Inside of loop function.references
                # Same level as loop function.references
            # Same level as loop contract.functions
        # Same level as loop source_unit.contracts
    # Same level as loop build.source_units

    # Add folder nodes
    for folder in folder_ordered_set:
        model.folders.append(folder._asdict())

    # Add contract inheritance edges
    for hashable_link in contract_inheritance_ordered_set:
        model.links.contract_inheritance.append({
            "from": hashable_link.from_,
            "to": hashable_link.to,
        })

    # Add metadata to model
    model.metadata.project_root_path = str(config.project_root_path)
    model.metadata.project_name = config.project_root_path.name

    # Create a file that will contain our `model`. Html does not support
    # importing JSONs, so we'll turn it into a Js file.
    model_js_contents = f"window.model = {json.dumps(asdict(model), indent=4)}"

    # Write the file
    if out_directory is None:
        out_directory = config.project_root_path / ".woke-dash"
    else:
        out_directory = Path(out_directory).resolve()

    if use_timestamp_directory:
        out_directory = out_directory / str(int(time.time()))

    out_directory.mkdir(parents=True, exist_ok=True)

    # woke dash assets directory
    wd_assets_directory = Path(__file__).parent.parent / "assets" / "woke-dash"
    assert wd_assets_directory.exists()

    model_js_path = out_directory / "woke-dash-model.js"

    model_js_path.write_text(model_js_contents)

    # We could use `copytree`, but it requires the directory be empty.
    # According to ChatGpt, `copyfile` only copies file contents, `copy` also
    # copies file permissions, and `copy2` also copies file metadata. It seems
    # like `copy` is the best choice.
    # We could do a loop on `.glob("**/*")`, but let's just do it individually.
    (out_directory / "vendor").mkdir(exist_ok=True)
    (out_directory / "js").mkdir(exist_ok=True)
    shutil.copy(wd_assets_directory / "index.html", out_directory)
    shutil.copy(wd_assets_directory / "favicon.svg", out_directory)
    shutil.copy(wd_assets_directory / "vendor" / "fomantic-2.9.2.js", out_directory / "vendor")
    shutil.copy(wd_assets_directory / "vendor" / "go-2.3.8.js", out_directory / "vendor")
    shutil.copy(wd_assets_directory / "vendor" / "jquery-3.6.3.js", out_directory / "vendor")
    shutil.copy(wd_assets_directory / "js" / "common.js", out_directory / "js")
    shutil.copy(wd_assets_directory / "js" / "declGraph.js", out_directory / "js")
    shutil.copy(wd_assets_directory / "js" / "declGraphKeyboard.js", out_directory / "js")
    shutil.copy(wd_assets_directory / "js" / "refGraph.js", out_directory / "js")
    shutil.copy(wd_assets_directory / "js" / "inhGraph.js", out_directory / "js")

    if use_timestamp_directory:
        # Create a symlink to the latest directory
        latest_directory = out_directory.parent / "latest"

        if platform.system() != "Windows":
            if latest_directory.is_symlink():
                latest_directory.unlink()
            latest_directory.symlink_to(out_directory, target_is_directory=True)

