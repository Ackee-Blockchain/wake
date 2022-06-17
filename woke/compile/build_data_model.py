from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Extra

from woke.compile.solc_frontend import SolcInputSettings, SolcOutputError


class BuildInfoModel(BaseModel):
    class Config:
        extra = Extra.allow
        allow_mutation = False


class CompilationUnitBuildInfo(BuildInfoModel):
    build_dir: str  # TODO unused
    sources: Dict[str, Path]
    contracts: Dict[str, Dict[str, Path]]
    errors: List[SolcOutputError]
    source_units: List[str]
    allow_paths: List[Path]
    include_paths: List[Path]
    settings: SolcInputSettings


class ProjectBuildInfo(BuildInfoModel):
    compilation_units: Dict[str, CompilationUnitBuildInfo]
