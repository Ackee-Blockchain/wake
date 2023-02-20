from pathlib import Path
from typing import Dict, FrozenSet, List, NamedTuple, Optional

import pydantic
from intervaltree import IntervalTree
from pydantic import BaseModel, Extra

from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.ir.reference_resolver import ReferenceResolver
from woke.compiler.solc_frontend import SolcInputSettings, SolcOutputError
from woke.core.solidity_version import SolidityVersion


class BuildInfoModel(BaseModel):
    class Config:
        extra = Extra.allow
        allow_mutation = False
        arbitrary_types_allowed = True
        json_encoders = {SolidityVersion: str, bytes: lambda b: b.hex()}


class CompilationUnitBuildInfo(BuildInfoModel):
    errors: List[SolcOutputError]


# workaround for pydantic bytes JSON encode bug: https://github.com/pydantic/pydantic/issues/3756
class HexBytes(bytes):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, bytes):
            return v
        elif isinstance(v, bytearray):
            return bytes(v)
        elif isinstance(v, str):
            return bytes.fromhex(v)
        raise pydantic.errors.BytesError()


class SourceUnitInfo(NamedTuple):
    fs_path: Path
    blake2b_hash: HexBytes


class ProjectBuildInfo(BuildInfoModel):
    compilation_units: Dict[str, CompilationUnitBuildInfo]
    source_units_info: Dict[str, SourceUnitInfo]
    allow_paths: FrozenSet[Path]
    ignore_paths: FrozenSet[Path]
    include_paths: FrozenSet[Path]
    settings: SolcInputSettings
    target_solidity_version: Optional[SolidityVersion]
    woke_version: str


class ProjectBuild(NamedTuple):
    interval_trees: Dict[Path, IntervalTree]
    reference_resolver: ReferenceResolver
    source_units: Dict[Path, SourceUnit]
