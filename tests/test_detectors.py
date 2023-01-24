import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Set

import pytest

from woke.analysis.detectors import detect
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.declaration.contract_definition import ContractDefinition
from woke.ast.ir.declaration.function_definition import FunctionDefinition
from woke.ast.ir.meta.source_unit import SourceUnit
from woke.compiler import SolcOutputSelectionEnum, SolidityCompiler
from woke.compiler.build_data_model import ProjectBuild
from woke.compiler.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
from woke.config import WokeConfig

SOURCES_PATH = Path(__file__).parent.resolve() / "detectors_sources"


def compile_project(sample_path: Path, config: WokeConfig) -> ProjectBuild:
    sol_files: Set[Path] = {sample_path}

    compiler = SolidityCompiler(config)
    build: ProjectBuild
    errors: Set[SolcOutputError]
    build, errors = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.AST],
            write_artifacts=False,
        )
    )

    assert not any(
        error.severity == SolcOutputErrorSeverityEnum.ERROR for error in errors
    )
    return build


def _get_contract_def(node: IrAbc) -> Optional[ContractDefinition]:
    if isinstance(node, ContractDefinition):
        return node
    if node.parent is None or isinstance(node.parent, SourceUnit):
        return None
    return _get_contract_def(node.parent)


def _get_function_def(node: IrAbc) -> Optional[FunctionDefinition]:
    if isinstance(node, FunctionDefinition):
        return node
    if (
        node.parent is None
        or isinstance(node.parent, ContractDefinition)
        or isinstance(node.parent, SourceUnit)
    ):
        return None
    return _get_function_def(node.parent)


def check_detected_in_functions(config, source_path):
    build = compile_project(source_path, config)
    source_file = build.source_units[source_path]

    detections = detect(config, build.source_units)

    detections_fns = [_get_function_def(det.result.ir_node) for det in detections]
    detections_fn_names = [fn.canonical_name for fn in detections_fns if fn is not None]

    detected_something = False
    for contract in source_file.contracts:
        for fn in contract.functions:
            if fn.name.startswith("legit_"):
                assert fn.canonical_name not in detections_fn_names
            elif fn.name.startswith("bug_"):
                detected_something = True
                assert fn.canonical_name in detections_fn_names

    for fn in source_file.functions:
        if fn.name.startswith("legit_"):
            assert fn.canonical_name not in detections_fn_names
        elif fn.name.startswith("bug_"):
            detected_something = True
            assert fn.canonical_name in detections_fn_names
    assert detected_something


def check_detected_in_contracts(config, source_path):
    build = compile_project(source_path, config)
    source_file = build.source_units[source_path]

    detections = detect(config, build.source_units)
    detections_contracts = [_get_contract_def(det.result.ir_node) for det in detections]
    detections_contract_names = [
        contract.name for contract in detections_contracts if contract is not None
    ]

    detected_something = False
    for cf in source_file.contracts:
        if cf.name.startswith("Legit_"):
            assert cf.name not in detections_contract_names
        elif cf.name.startswith("Bug_"):
            detected_something = True
            assert cf.name in detections_contract_names
    assert detected_something


class TestNoReturnDetector:
    @pytest.fixture
    def config(self, tmp_path) -> WokeConfig:
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path)
        os.environ["XDG_DATA_HOME"] = str(tmp_path)
        config_dict = {
            "compiler": {"solc": {"include_paths": ["./node_modules"]}},
            "detectors": {"only": {"no-return"}},
        }
        return WokeConfig.fromdict(
            config_dict,
            project_root_path=tmp_path,
        )

    @pytest.mark.slow
    def test_sources(self, config, tmp_path):
        test_file = "no_return.sol"
        test_source_path = tmp_path / test_file
        shutil.copyfile(SOURCES_PATH / test_file, test_source_path)
        check_detected_in_functions(config, test_source_path)


class TestBugEmptyByteArrayCopy:
    @pytest.fixture
    def config(self, tmp_path) -> WokeConfig:
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path)
        os.environ["XDG_DATA_HOME"] = str(tmp_path)
        config_dict = {
            "compiler": {"solc": {"include_paths": ["./node_modules"]}},
            "detectors": {"only": {"bug-empty-byte-array-copy"}},
        }
        return WokeConfig.fromdict(
            config_dict,
            project_root_path=tmp_path,
        )

    @pytest.mark.slow
    def test_sources(self, config, tmp_path):
        test_file = "bug_empty_byte_array_copy.sol"
        test_source_path = tmp_path / test_file
        shutil.copyfile(SOURCES_PATH / test_file, test_source_path)
        check_detected_in_functions(config, test_source_path)


class TestUnsafeTxOrigin:
    @pytest.fixture
    def config(self, tmp_path) -> WokeConfig:
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path)
        os.environ["XDG_DATA_HOME"] = str(tmp_path)
        config_dict = {
            "compiler": {"solc": {"include_paths": ["./node_modules"]}},
            "detectors": {"only": {"unsafe-tx-origin"}},
        }
        return WokeConfig.fromdict(
            config_dict,
            project_root_path=tmp_path,
        )

    @pytest.mark.slow
    def test_sources(self, config, tmp_path):
        test_file = "unsafe_tx_origin.sol"
        test_source_path = tmp_path / test_file
        shutil.copyfile(SOURCES_PATH / test_file, test_source_path)
        check_detected_in_functions(config, test_source_path)


class TestNotUsed:
    @pytest.fixture
    def config(self, tmp_path) -> WokeConfig:
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path)
        os.environ["XDG_DATA_HOME"] = str(tmp_path)
        config_dict = {
            "compiler": {"solc": {"include_paths": ["./node_modules"]}},
            "detectors": {"only": {"not-used"}},
        }
        return WokeConfig.fromdict(
            config_dict,
            project_root_path=tmp_path,
        )

    @pytest.mark.slow
    def test_sources(self, config, tmp_path):
        test_file = "not_used.sol"
        test_source_path = tmp_path / test_file
        shutil.copyfile(SOURCES_PATH / test_file, test_source_path)
        check_detected_in_contracts(config, test_source_path)


class TestProxyContractSelectorClashes:
    @pytest.fixture
    def config(self, tmp_path) -> WokeConfig:
        os.environ["XDG_CONFIG_HOME"] = str(tmp_path)
        os.environ["XDG_DATA_HOME"] = str(tmp_path)
        config_dict = {
            "compiler": {"solc": {"include_paths": ["./node_modules"]}},
            "detectors": {"only": {"proxy-contract-selector-clashes"}},
        }
        return WokeConfig.fromdict(
            config_dict,
            project_root_path=tmp_path,
        )

    @pytest.mark.slow
    def test_sources(self, config, tmp_path):
        test_file = "proxy_contract_selector_clashes.sol"
        test_source_path = tmp_path / test_file
        shutil.copyfile(SOURCES_PATH / test_file, test_source_path)

        build = compile_project(test_source_path, config)
        detections = detect(config, build.source_units)
        logging.error(detections)
        detections_fns = [_get_function_def(det.result.ir_node) for det in detections]
        detections_fn_names = [
            fn.canonical_name for fn in detections_fns if fn is not None
        ]

        assert "Proxy.bug_clash" in detections_fn_names
