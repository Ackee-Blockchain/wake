import re
from dataclasses import astuple
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_serializer
from pydantic.dataclasses import dataclass
from pydantic.functional_validators import BeforeValidator
from typing_extensions import Annotated

from wake.core.enums import EvmVersionEnum
from wake.core.solidity_version import SolidityVersion
from wake.utils import StrEnum


class WakeConfigModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


@dataclass
class SolcRemapping:
    context: Optional[str]
    prefix: str
    target: Optional[str]

    def __iter__(self):
        return iter(astuple(self))

    def __str__(self):
        if self.context is None:
            return f"{self.prefix}={self.target or ''}"
        else:
            return f"{self.context}:{self.prefix}={self.target or ''}"


class GraphsDirection(StrEnum):
    TopBottom = "TB"
    BottomTop = "BT"
    LeftRight = "LR"
    RightLeft = "RL"


class ImportsDirection(StrEnum):
    ImportedToImporting = "imported-to-importing"
    ImportingToImported = "importing-to-imported"


class SolcOptimizerYulDetailsConfig(WakeConfigModel):
    stack_allocation: Optional[bool] = None
    optimizer_steps: Optional[str] = None


class SolcOptimizerDetailsConfig(WakeConfigModel):
    peephole: Optional[bool] = None
    inliner: Optional[bool] = None
    jumpdest_remover: Optional[bool] = None
    order_literals: Optional[bool] = None
    deduplicate: Optional[bool] = None
    cse: Optional[bool] = None
    constant_optimizer: Optional[bool] = None
    simple_counter_for_loop_unchecked_increment: Optional[bool] = None
    # no need to add yul option here, since it applies only to solc < 0.6.0
    yul_details: SolcOptimizerYulDetailsConfig = Field(
        default_factory=SolcOptimizerYulDetailsConfig
    )


class SolcOptimizerConfig(WakeConfigModel):
    enabled: Optional[bool] = None
    runs: int = 200
    details: SolcOptimizerDetailsConfig = Field(
        default_factory=SolcOptimizerDetailsConfig
    )


def convert_remapping(v):
    if isinstance(v, SolcRemapping):
        return v
    elif isinstance(v, dict):
        return SolcRemapping(**v)

    remapping_re = re.compile(
        r"(?:(?P<context>[^:\s]+)?:)?(?P<prefix>[^\s=]+)=(?P<target>[^\s]+)?"
    )
    match = remapping_re.match(v)
    assert match, f"`{v}` is not a valid solc remapping."

    groupdict = match.groupdict()
    context = groupdict["context"]
    prefix = groupdict["prefix"]
    target = groupdict["target"]
    return SolcRemapping(context=context, prefix=prefix, target=target)


class SolcConfig(WakeConfigModel):
    allow_paths: FrozenSet[
        Annotated[Path, BeforeValidator(lambda p: Path(p).resolve())]
    ] = frozenset()
    """Wake should set solc `--allow-paths` automatically. This option allows to specify additional allowed paths."""
    evm_version: Optional[EvmVersionEnum] = None
    """Version of the EVM to compile for. Leave unset to let the solc decide."""
    exclude_paths: FrozenSet[
        Annotated[Path, BeforeValidator(lambda p: Path(p).resolve())]
    ] = Field(
        default_factory=lambda: frozenset(
            [
                Path.cwd() / "node_modules",
                Path.cwd() / "venv",
                Path.cwd() / ".venv",
                Path.cwd() / "lib",
                Path.cwd() / "script",
                Path.cwd() / "test",
            ]
        )
    )
    """
    Solidity files in these paths are excluded from compilation unless imported from a non-excluded file.
    """
    include_paths: FrozenSet[
        Annotated[Path, BeforeValidator(lambda p: Path(p).resolve())]
    ] = Field(default_factory=lambda: frozenset([Path.cwd() / "node_modules"]))
    """
    Paths where to search for Solidity files imported using direct (non-relative) import paths.
    """
    optimizer: SolcOptimizerConfig = Field(default_factory=SolcOptimizerConfig)
    """
    Optimizer config options.
    """
    remappings: List[
        Annotated[
            SolcRemapping,
            BeforeValidator(convert_remapping),
            PlainSerializer(lambda r: str(r), when_used="json"),
        ]
    ] = []
    """
    Remappings to apply during compilation.
    """
    target_version: Optional[SolidityVersion] = None
    """
    Target Solidity version to use for all files during compilation.
    """
    via_IR: Optional[bool] = None
    """
    Use new IR-based compiler pipeline.
    """

    @field_serializer("target_version", when_used="json")
    def serialize_target_version(self, version: Optional[SolidityVersion], info):
        return str(version) if version is not None else None


class FindReferencesConfig(WakeConfigModel):
    include_declarations: bool = False
    """
    Include declarations in the results.
    """


class CodeLensConfig(WakeConfigModel):
    enable: bool = True
    """
    Show code lenses.
    """
    sort_tag_priority: List[str] = [
        "lsp-references",
        "lsp-selectors",
        "lsp-inheritance-graph",
        "lsp-linearized-inheritance-graph",
    ]
    """
    Order of code lens with the same start and end position based on sort tags used in detectors/printers. Sort tags default to the printer/detector name.
    """


class InlayHintsConfig(WakeConfigModel):
    enable: bool = True
    """
    Show inlay hints.
    """
    sort_tag_priority: List[str] = []
    """
    Order of inlay hints with the same position based on sort tags used in detectors/printers. Sort tags default to the printer/detector name.
    """


class DetectorsLspConfig(WakeConfigModel):
    enable: bool = True
    """
    Run detectors in LSP.
    """


class CompilerConfig(WakeConfigModel):
    solc: SolcConfig = Field(default_factory=SolcConfig)


class DetectorsConfig(WakeConfigModel):
    exclude: FrozenSet[str] = frozenset()
    """
    Names of detectors that should not be loaded.
    """
    only: Optional[FrozenSet[str]] = None
    """
    Names of detectors that should only be loaded.
    """
    ignore_paths: FrozenSet[
        Annotated[Path, BeforeValidator(lambda p: Path(p).resolve())]
    ] = Field(
        default_factory=lambda: frozenset(
            [
                Path.cwd() / "venv",
                Path.cwd() / ".venv",
                Path.cwd() / "test",
            ]
        )
    )
    """
    Detections in these paths must be ignored under all circumstances.
    Useful for ignoring detections in Solidity test files.
    """
    exclude_paths: FrozenSet[
        Annotated[Path, BeforeValidator(lambda p: Path(p).resolve())]
    ] = Field(
        default_factory=lambda: frozenset(
            [
                Path.cwd() / "node_modules",
                Path.cwd() / "lib",
                Path.cwd() / "script",
            ]
        )
    )
    """
    Detections in these paths are ignored unless linked to a (sub)detection in a non-excluded path.
    Useful for ignoring detections in dependencies.
    """


# namespace for detector configs
class DetectorConfig(WakeConfigModel, extra="allow"):
    """
    Namespace for detector-specific config options.
    Each attribute should be named after the detector name and hold a dictionary with string keys matching the Click option names.
    """


class LspConfig(WakeConfigModel):
    compilation_delay: float = 0
    """
    Delay to wait after a file content change before recompiling.
    """
    code_lens: CodeLensConfig = Field(default_factory=CodeLensConfig)
    """
    Code lens config options.
    """
    detectors: DetectorsLspConfig = Field(default_factory=DetectorsLspConfig)
    """
    Detectors config options specific to LSP.
    """
    find_references: FindReferencesConfig = Field(default_factory=FindReferencesConfig)
    """
    Find references config options.
    """
    inlay_hints: InlayHintsConfig = Field(default_factory=InlayHintsConfig)
    """
    Inlay hints config options.
    """


class ControlFlowGraphConfig(WakeConfigModel):
    """
    Unstable, may change in the future.
    """

    direction: GraphsDirection = GraphsDirection.TopBottom
    vscode_urls: bool = True


class ImportsGraphConfig(WakeConfigModel):
    """
    Unstable, may change in the future.
    """

    direction: GraphsDirection = GraphsDirection.TopBottom
    imports_direction: ImportsDirection = ImportsDirection.ImportedToImporting
    vscode_urls: bool = True


class InheritanceGraphConfig(WakeConfigModel):
    """
    Unstable, may change in the future.
    """

    direction: GraphsDirection = GraphsDirection.BottomTop
    vscode_urls: bool = True


class LinearizedInheritanceGraphConfig(WakeConfigModel):
    """
    Unstable, may change in the future.
    """

    direction: GraphsDirection = GraphsDirection.LeftRight
    vscode_urls: bool = True


class GeneratorConfig(WakeConfigModel):
    """
    Unstable, may change in the future.
    """

    control_flow_graph: ControlFlowGraphConfig = Field(
        default_factory=ControlFlowGraphConfig
    )
    imports_graph: ImportsGraphConfig = Field(default_factory=ImportsGraphConfig)
    inheritance_graph: InheritanceGraphConfig = Field(
        default_factory=InheritanceGraphConfig
    )
    inheritance_graph_full: InheritanceGraphConfig = Field(
        default_factory=InheritanceGraphConfig
    )
    linearized_inheritance_graph: LinearizedInheritanceGraphConfig = Field(
        default_factory=LinearizedInheritanceGraphConfig
    )


class AnvilConfig(WakeConfigModel):
    cmd_args: str = (
        "--prune-history 100 --transaction-block-keeper 10 --steps-tracing --silent"
    )
    """
    Command line arguments to pass to `anvil`.
    """


class GanacheConfig(WakeConfigModel):
    cmd_args: str = "-k istanbul -q"
    """
    Command line arguments to pass to `ganache`.
    """


class HardhatConfig(WakeConfigModel):
    cmd_args: str = ""
    """
    Command line arguments to pass to `npx hardhat node`.
    """


class TestingConfig(WakeConfigModel):
    cmd: str = "anvil"
    """
    Which development chain to use for testing. Should be one of `anvil`, `ganache` or `hardhat`.
    """
    anvil: AnvilConfig = Field(default_factory=AnvilConfig)
    """
    Anvil-specific config options.
    """
    ganache: GanacheConfig = Field(default_factory=GanacheConfig)
    """
    Ganache-specific config options.
    """
    hardhat: HardhatConfig = Field(default_factory=HardhatConfig)
    """
    Hardhat-specific config options.
    """


class DeploymentConfig(WakeConfigModel):
    confirm_transactions: bool = True
    """
    Require confirmation for each transaction.
    """
    silent: bool = False
    """
    Do not require confirmation for each transaction and do not print transaction status.
    """


class GeneralConfig(WakeConfigModel):
    call_trace_options: FrozenSet[str] = frozenset(
        [
            "contract_name",
            "function_name",
            "named_arguments",
            "status",
            "call_type",
            "value",
            "return_value",
            "error",
        ]
    )
    """
    Options to include in call traces.
    """
    json_rpc_timeout: float = 15
    """
    Timeout applied to JSON-RPC requests.
    """
    link_format: str = "vscode://file/{path}:{line}:{col}"
    """
    Format of links used in detectors and printers.
    """


class PrintersConfig(WakeConfigModel):
    """
    Holds general printer config options for all printers.
    """

    exclude: FrozenSet[str] = frozenset()
    """
    Names of printers that should not be loaded.
    """
    only: Optional[FrozenSet[str]] = None
    """
    Names of printers that should only be loaded.
    """


# namespace for printer configs
class PrinterConfig(WakeConfigModel, extra="allow"):
    """
    Namespace for printer-specific config options.
    Each attribute should be named after the printer name and hold a dictionary with string keys matching the Click option names.
    """


class TopLevelConfig(WakeConfigModel):
    subconfigs: List[Annotated[Path, BeforeValidator(lambda p: Path(p).resolve())]] = []
    api_keys: Dict[str, str] = {}
    compiler: CompilerConfig = Field(default_factory=CompilerConfig)
    detectors: DetectorsConfig = Field(default_factory=DetectorsConfig)
    detector: DetectorConfig = Field(default_factory=DetectorConfig)
    generator: GeneratorConfig = Field(default_factory=GeneratorConfig)
    lsp: LspConfig = Field(default_factory=LspConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    printers: PrintersConfig = Field(default_factory=PrintersConfig)
    printer: PrinterConfig = Field(default_factory=PrinterConfig)
    general: GeneralConfig = Field(default_factory=GeneralConfig)
