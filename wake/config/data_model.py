import re
from dataclasses import astuple
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Union

from pydantic import BaseModel, Extra, Field, validator
from pydantic.dataclasses import dataclass

from wake.core.enums import EvmVersionEnum
from wake.core.solidity_version import SolidityVersion
from wake.utils import StrEnum


class WakeConfigModel(BaseModel):
    class Config:
        allow_mutation = False
        json_encoders = {
            SolidityVersion: str,
        }
        extra = Extra.forbid


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


class SolcConfig(WakeConfigModel):
    allow_paths: FrozenSet[Path] = frozenset()
    """Wake should set solc `--allow-paths` automatically. This option allows to specify additional allowed paths."""
    evm_version: Optional[EvmVersionEnum] = None
    """Version of the EVM to compile for. Leave unset to let the solc decide."""
    exclude_paths: FrozenSet[Path] = Field(
        default_factory=lambda: frozenset(
            [
                Path.cwd() / "node_modules",
                Path.cwd() / "venv",
                Path.cwd() / "lib",
                Path.cwd() / "script",
                Path.cwd() / "test",
            ]
        )
    )
    include_paths: FrozenSet[Path] = Field(
        default_factory=lambda: frozenset([Path.cwd() / "node_modules"])
    )
    optimizer: SolcOptimizerConfig = Field(default_factory=SolcOptimizerConfig)
    remappings: List[SolcRemapping] = []
    target_version: Optional[SolidityVersion] = None
    via_IR: Optional[bool] = None

    @validator("allow_paths", pre=True, each_item=True)
    def set_allow_path(cls, v):
        return Path(v).resolve()

    @validator("exclude_paths", pre=True, each_item=True)
    def set_exclude_paths(cls, v):
        return Path(v).resolve()

    @validator("include_paths", pre=True, each_item=True)
    def set_include_path(cls, v):
        return Path(v).resolve()

    @validator("remappings", pre=True, each_item=True)
    def set_remapping(cls, v):
        if isinstance(v, SolcRemapping):
            return v
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


class FindReferencesConfig(WakeConfigModel):
    include_declarations: bool = False


class CodeLensConfig(WakeConfigModel):
    enable: bool = True


class DetectorsLspConfig(WakeConfigModel):
    enable: bool = True


class CompilerConfig(WakeConfigModel):
    solc: SolcConfig = Field(default_factory=SolcConfig)


class DetectorsConfig(WakeConfigModel):
    exclude: FrozenSet[str] = frozenset()
    only: Optional[FrozenSet[str]] = None
    ignore_paths: FrozenSet[Path] = Field(
        default_factory=lambda: frozenset(
            [
                Path.cwd() / "venv",
                Path.cwd() / "test",
            ]
        )
    )
    exclude_paths: FrozenSet[Path] = Field(
        default_factory=lambda: frozenset(
            [
                Path.cwd() / "node_modules",
                Path.cwd() / "lib",
                Path.cwd() / "script",
            ]
        )
    )

    @validator("ignore_paths", pre=True, each_item=True)
    def set_ignore_paths(cls, v):
        return Path(v).resolve()

    @validator("exclude_paths", pre=True, each_item=True)
    def set_exclude_paths(cls, v):
        return Path(v).resolve()


# namespace for detector configs
class DetectorConfig(WakeConfigModel, extra=Extra.allow):
    pass


class LspConfig(WakeConfigModel):
    compilation_delay: float = 0
    code_lens: CodeLensConfig = Field(default_factory=CodeLensConfig)
    detectors: DetectorsLspConfig = Field(default_factory=DetectorsLspConfig)
    find_references: FindReferencesConfig = Field(default_factory=FindReferencesConfig)


class ControlFlowGraphConfig(WakeConfigModel):
    direction: GraphsDirection = GraphsDirection.TopBottom
    vscode_urls: bool = True


class ImportsGraphConfig(WakeConfigModel):
    direction: GraphsDirection = GraphsDirection.TopBottom
    imports_direction: ImportsDirection = ImportsDirection.ImportedToImporting
    vscode_urls: bool = True


class InheritanceGraphConfig(WakeConfigModel):
    direction: GraphsDirection = GraphsDirection.BottomTop
    vscode_urls: bool = True


class LinearizedInheritanceGraphConfig(WakeConfigModel):
    direction: GraphsDirection = GraphsDirection.LeftRight
    vscode_urls: bool = True


class GeneratorConfig(WakeConfigModel):
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


class GanacheConfig(WakeConfigModel):
    cmd_args: str = "-k istanbul -q"


class HardhatConfig(WakeConfigModel):
    cmd_args: str = ""


class TestingConfig(WakeConfigModel):
    cmd: str = "anvil"
    anvil: AnvilConfig = Field(default_factory=AnvilConfig)
    ganache: GanacheConfig = Field(default_factory=GanacheConfig)
    hardhat: HardhatConfig = Field(default_factory=HardhatConfig)


class DeploymentConfig(WakeConfigModel):
    confirm_transactions: bool = True
    silent: bool = False


class GeneralConfig(WakeConfigModel):
    call_trace_options: FrozenSet[str] = frozenset(
        [
            "contract_name",
            "function_name",
            "arguments",
            "status",
            "call_type",
            "value",
            "return_value",
            "error",
        ]
    )
    json_rpc_timeout: float = 15
    link_format: str = "vscode://file/{path}:{line}:{col}"


# currently unused
class PrintersConfig(WakeConfigModel):
    pass


# namespace for printer configs
class PrinterConfig(WakeConfigModel, extra=Extra.allow):
    pass


class TopLevelConfig(WakeConfigModel):
    subconfigs: List[Path] = []
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

    @validator("subconfigs", pre=True, each_item=True)
    def set_subconfig(cls, v):
        return Path(v).resolve()
