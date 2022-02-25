from typing import Optional, List
from pathlib import Path
from dataclasses import astuple
import re

from pydantic import BaseModel, Field, Extra, validator
from pydantic.dataclasses import dataclass


class WokeConfigModel(BaseModel):
    class Config:
        allow_mutation = False
        extra = Extra.forbid


@dataclass
class SolcRemapping:
    context: Optional[str]
    prefix: str
    target: Optional[str]

    def __iter__(self):
        return iter(astuple(self))


class SolcWokeConfig(WokeConfigModel):
    allow_paths: List[Path] = []
    """Woke should set solc `--allow-paths` automatically. This option allows to specify additional allowed paths."""
    include_paths: List[Path] = []
    remappings: List[SolcRemapping] = []

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
        return SolcRemapping(context, prefix, target)


class CompilerWokeConfig(WokeConfigModel):
    solc: SolcWokeConfig = Field(default_factory=SolcWokeConfig)


class TopLevelWokeConfig(WokeConfigModel):
    subconfigs: List[Path] = []
    compiler: CompilerWokeConfig = Field(default_factory=CompilerWokeConfig)

    @validator("subconfigs", pre=True, each_item=True)
    def set_subconfig(cls, v):
        return Path(v).resolve()
