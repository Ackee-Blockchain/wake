import re
from dataclasses import astuple
from pathlib import Path
from typing import FrozenSet, List, Optional

from pydantic import BaseModel, Extra, Field, validator
from pydantic.dataclasses import dataclass

from woke.core.enums import EvmVersionEnum
from woke.core.solidity_version import SolidityVersion


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
        return f"{self.context or ''}:{self.prefix}={self.target or ''}"


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
    enable: bool = False


class CompilerConfig(WokeConfigModel):
    solc: SolcConfig = Field(default_factory=SolcConfig)


class LspConfig(WokeConfigModel):
    code_lens: CodeLensConfig = Field(default_factory=CodeLensConfig)
    find_references: FindReferencesConfig = Field(default_factory=FindReferencesConfig)


class TopLevelConfig(WokeConfigModel):
    subconfigs: List[Path] = []
    compiler: CompilerConfig = Field(default_factory=CompilerConfig)
    lsp: LspConfig = Field(default_factory=LspConfig)

    @validator("subconfigs", pre=True, each_item=True)
    def set_subconfig(cls, v):
        return Path(v).resolve()
