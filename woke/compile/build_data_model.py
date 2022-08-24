from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Dict, FrozenSet, List

from pydantic import BaseModel, Extra, validator

from woke.compile.solc_frontend import SolcInputSettings, SolcOutputError
from woke.core.solidity_version import SolidityVersion


class BuildInfoModel(BaseModel):
    class Config:
        extra = Extra.allow
        allow_mutation = False
        arbitrary_types_allowed = True
        json_encoders = {PurePosixPath: str, PureWindowsPath: str, SolidityVersion: str}


class CompilationUnitBuildInfo(BuildInfoModel):
    build_dir: str  # TODO unused
    sources: Dict[str, Path]
    contracts: Dict[str, Dict[str, Path]]
    errors: List[SolcOutputError]
    source_units: FrozenSet[PurePath]
    allow_paths: FrozenSet[Path]
    include_paths: FrozenSet[Path]
    settings: SolcInputSettings
    compiler_version: SolidityVersion

    @validator("source_units", pre=True, each_item=True)
    def set_source_units(cls, v):
        return PurePath(v)


class ProjectBuildInfo(BuildInfoModel):
    compilation_units: Dict[str, CompilationUnitBuildInfo]
