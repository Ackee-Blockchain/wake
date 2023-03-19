import re
from dataclasses import astuple
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Union

from pydantic import BaseModel, Extra, Field, validator
from pydantic.dataclasses import dataclass

from woke.core.enums import EvmVersionEnum
from woke.core.solidity_version import SolidityVersion
from woke.utils import StrEnum


class WokeConfigModel(BaseModel):
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


class SolcOptimizerConfig(WokeConfigModel):
    enabled: Optional[bool] = None
    runs: int = 200


class SolcConfig(WokeConfigModel):
    allow_paths: FrozenSet[Path] = frozenset()
    """Woke should set solc `--allow-paths` automatically. This option allows to specify additional allowed paths."""
    evm_version: Optional[EvmVersionEnum] = None
    """Version of the EVM to compile for. Leave unset to let the solc decide."""
    ignore_paths: FrozenSet[Path] = Field(
        default_factory=lambda: frozenset(
            [
                Path.cwd() / "node_modules",
                Path.cwd() / ".woke-build",
                Path.cwd() / "venv",
                Path.cwd() / "lib",
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

    @validator("ignore_paths", pre=True, each_item=True)
    def set_ignore_paths(cls, v):
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


class FindReferencesConfig(WokeConfigModel):
    include_declarations: bool = False


class CodeLensConfig(WokeConfigModel):
    enable: bool = True


class DetectorsLspConfig(WokeConfigModel):
    enable: bool = True


class CompilerConfig(WokeConfigModel):
    solc: SolcConfig = Field(default_factory=SolcConfig)


class DetectorsConfig(WokeConfigModel):
    exclude: FrozenSet[Union[int, str]] = frozenset()
    only: Optional[FrozenSet[Union[int, str]]] = None
    ignore_paths: FrozenSet[Path] = Field(
        default_factory=lambda: frozenset(
            [
                Path.cwd() / "node_modules",
                Path.cwd() / ".woke-build",
                Path.cwd() / "venv",
                Path.cwd() / "lib",
            ]
        )
    )

    @validator("ignore_paths", pre=True, each_item=True)
    def set_ignore_paths(cls, v):
        return Path(v).resolve()


class LspConfig(WokeConfigModel):
    compilation_delay: float = 0
    code_lens: CodeLensConfig = Field(default_factory=CodeLensConfig)
    detectors: DetectorsLspConfig = Field(default_factory=DetectorsLspConfig)
    find_references: FindReferencesConfig = Field(default_factory=FindReferencesConfig)


class ControlFlowGraphConfig(WokeConfigModel):
    direction: GraphsDirection = GraphsDirection.TopBottom
    vscode_urls: bool = True


class ImportsGraphConfig(WokeConfigModel):
    direction: GraphsDirection = GraphsDirection.TopBottom
    imports_direction: ImportsDirection = ImportsDirection.ImportedToImporting
    vscode_urls: bool = True


class InheritanceGraphConfig(WokeConfigModel):
    direction: GraphsDirection = GraphsDirection.BottomTop
    vscode_urls: bool = True


class LinearizedInheritanceGraphConfig(WokeConfigModel):
    direction: GraphsDirection = GraphsDirection.LeftRight
    vscode_urls: bool = True


class GeneratorConfig(WokeConfigModel):
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


class AnvilConfig(WokeConfigModel):
    cmd_args: str = "--prune-history 100 --steps-tracing --silent"


class GanacheConfig(WokeConfigModel):
    cmd_args: str = "-k istanbul -q"


class HardhatConfig(WokeConfigModel):
    cmd_args: str = ""


class TestingConfig(WokeConfigModel):
    cmd: str = "anvil"
    timeout: float = 5
    anvil: AnvilConfig = Field(default_factory=AnvilConfig)
    ganache: GanacheConfig = Field(default_factory=GanacheConfig)
    hardhat: HardhatConfig = Field(default_factory=HardhatConfig)


class TopLevelConfig(WokeConfigModel):
    subconfigs: List[Path] = []
    api_keys: Dict[str, str] = {}
    compiler: CompilerConfig = Field(default_factory=CompilerConfig)
    detectors: DetectorsConfig = Field(default_factory=DetectorsConfig)
    generator: GeneratorConfig = Field(default_factory=GeneratorConfig)
    lsp: LspConfig = Field(default_factory=LspConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)

    @validator("subconfigs", pre=True, each_item=True)
    def set_subconfig(cls, v):
        return Path(v).resolve()
