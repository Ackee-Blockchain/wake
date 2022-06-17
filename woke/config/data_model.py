import re
from dataclasses import astuple
from pathlib import Path
from typing import List, Optional

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


class SolcWokeConfig(WokeConfigModel):
    allow_paths: List[Path] = []
    """Woke should set solc `--allow-paths` automatically. This option allows to specify additional allowed paths."""
    evm_version: Optional[EvmVersionEnum] = None
    """Version of the EVM to compile for. Leave unset to let the solc decide."""
    include_paths: List[Path] = Field(
        default_factory=lambda: [Path.cwd() / "node_modules"]
    )
    remappings: List[SolcRemapping] = []
    target_version: Optional[SolidityVersion] = None

    @validator("allow_paths", pre=True, each_item=True)
    def set_allow_path(cls, v):
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


class CompilerWokeConfig(WokeConfigModel):
    solc: SolcWokeConfig = Field(default_factory=SolcWokeConfig)


class TopLevelWokeConfig(WokeConfigModel):
    subconfigs: List[Path] = []
    compiler: CompilerWokeConfig = Field(default_factory=CompilerWokeConfig)

    @validator("subconfigs", pre=True, each_item=True)
    def set_subconfig(cls, v):
        return Path(v).resolve()
