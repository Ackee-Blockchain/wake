import asyncio
import random
import shutil
from pathlib import Path, PurePath
from typing import Dict, Set
from unittest import mock

import pytest

from woke.compile import SolcOutputSelectionEnum, SolidityCompiler
from woke.compile.build_data_model import BuildInfo
from woke.compile.solc_frontend import SolcOutputError, SolcOutputErrorSeverityEnum
from woke.config import WokeConfig
from woke.testing import coverage
from woke.testing.coverage import ContractCoverage, Coverage, CoverageProvider

SOURCES_PATH = Path(__file__).parent.resolve() / "coverage_sources"


def compile_project(sample_path: Path, config: WokeConfig) -> BuildInfo:
    sol_files: Set[Path] = {sample_path}

    compiler = SolidityCompiler(config)
    build: BuildInfo
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


@pytest.fixture
def config(tmp_path) -> WokeConfig:
    config_dict = {
        "compiler": {"solc": {"include_paths": ["./node_modules"]}},
    }
    return WokeConfig.fromdict(
        config_dict,
        woke_root_path=tmp_path,
        project_root_path=tmp_path,
    )


def get_contract_and_intervals(config, source_path):
    build = compile_project(source_path, config)
    source_unit = build.source_units[source_path]
    assert len(source_unit.contracts) == 1

    contract = source_unit.contracts[0]

    assert contract.compilation_info is not None
    assert contract.compilation_info.evm is not None
    assert contract.compilation_info.evm.deployed_bytecode is not None

    opcodes = contract.compilation_info.evm.deployed_bytecode.opcodes
    source_map = contract.compilation_info.evm.deployed_bytecode.source_map
    line_intervals = coverage._get_line_intervals(contract.file.read_text())

    assert opcodes is not None
    assert source_map is not None

    pc_op_map = coverage._parse_opcodes(opcodes)
    pc_map = coverage._parse_source_map(
        build.interval_trees,
        contract.cu_hash,
        build.reference_resolver,
        source_map,
        pc_op_map,
    )

    return contract, line_intervals, pc_map


class TestContractCoverage:
    @pytest.fixture
    def basic_contract_coverage(self, config, tmp_path) -> ContractCoverage:
        test_file = "basic_contract_coverage.sol"
        source_path = tmp_path / test_file
        shutil.copy(SOURCES_PATH / test_file, source_path)

        covs = coverage._construct_coverage_data(config)
        assert len(covs) == 1
        cov = list(covs.values())[0]
        return cov

    @pytest.fixture
    def parsing_contract_coverages(
        self, config, tmp_path
    ) -> Dict[str, ContractCoverage]:
        test_file = "parsing_contract_coverage.sol"
        source_path = tmp_path / test_file
        shutil.copy(SOURCES_PATH / test_file, source_path)

        covs = coverage._construct_coverage_data(config)
        assert len(covs) == 2
        return covs

    @pytest.mark.slow
    def test_add_random_coverage(self, basic_contract_coverage):
        covered_pcs = random.sample(list(basic_contract_coverage.pc_map.keys()), 50)

        expected_cov = {}
        for pc in covered_pcs:
            basic_contract_coverage.add_cov(pc)
            if pc not in expected_cov:
                expected_cov[pc] = 0
            expected_cov[pc] += 1

        for pc in covered_pcs:
            assert pc in basic_contract_coverage.pc_instruction_cov
            assert (
                basic_contract_coverage.pc_instruction_cov[pc].hit_count
                == expected_cov[pc]
            )

    @pytest.mark.slow
    def test_add_random_branch_coverage(self, basic_contract_coverage):
        covered_pcs = random.sample(
            list(basic_contract_coverage.pc_branch_cov.keys()), 5
        )

        expected_cov = {}
        for pc in covered_pcs:
            basic_contract_coverage.add_cov(pc)
            if pc not in expected_cov:
                expected_cov[pc] = 0
            expected_cov[pc] += 1

        for pc in covered_pcs:
            assert pc in basic_contract_coverage.pc_branch_cov
            assert (
                basic_contract_coverage.pc_branch_cov[pc].hit_count == expected_cov[pc]
            )

    @pytest.mark.slow
    def test_get_ide_branch_coverage(self, basic_contract_coverage):
        for pc in basic_contract_coverage.pc_branch_cov.keys():
            basic_contract_coverage.add_cov(pc)

        ide_branch_coverage = basic_contract_coverage.get_ide_coverage()
        for records in ide_branch_coverage.values():
            for fn_rec in records.values():
                for branch in fn_rec.branch_records.values():
                    assert branch.coverage_hits == 1

    @pytest.mark.slow
    def test_get_ide_modifier_coverage(self, basic_contract_coverage):
        for pc in basic_contract_coverage.pc_modifier_cov.keys():
            basic_contract_coverage.add_cov(pc)

        ide_modifier_coverage = basic_contract_coverage.get_ide_coverage()
        for records in ide_modifier_coverage.values():
            for fn_rec in records.values():
                for mod in fn_rec.mod_records.values():
                    assert mod.coverage_hits == 1

    @pytest.mark.slow
    def test_get_ide_function_calls_coverage(self, basic_contract_coverage):
        for pc in basic_contract_coverage.pc_instruction_cov.keys():
            basic_contract_coverage.add_cov(pc)

        ide_function_calls_coverage = basic_contract_coverage.get_ide_coverage()
        for records in ide_function_calls_coverage.values():
            for fn_rec in records.values():
                assert fn_rec.coverage_hits == 1

    @pytest.mark.slow
    def test_parsing_modifiers(self, parsing_contract_coverages):
        cov = parsing_contract_coverages["parsing_contract_coverage.sol:Parsing"]
        calls_func = cov.functions[
            "Parsing:function fcalls_func(uint a) public mod_test1(a) mod_test2(a) returns (uint b)"
        ]
        assert len(calls_func.modifiers) == 2
        assert len(calls_func.modifier_cov) == 2
        if_func = cov.functions[
            "Parsing:function if_func(uint a) public mod_test1(a) returns (uint b)"
        ]
        assert len(if_func.modifiers) == 1
        assert len(if_func.modifier_cov) == 1

    @pytest.mark.slow
    def test_parsing_branches(self, parsing_contract_coverages):
        cov = parsing_contract_coverages["parsing_contract_coverage.sol:Parsing"]

        calls_func = cov.functions[
            "Parsing:function fcalls_func(uint a) public mod_test1(a) mod_test2(a) returns (uint b)"
        ]
        assert len(calls_func.branch_cov) == 2
        if_func = cov.functions[
            "Parsing:function if_func(uint a) public mod_test1(a) returns (uint b)"
        ]
        assert len(if_func.branch_cov) == 7
        for_func = cov.functions["Parsing:function for_func() public"]
        assert len(for_func.branch_cov) == 6
        assembly_func = cov.functions[
            "Parsing:function assembly_func(uint256 a) public returns (uint)"
        ]
        assert len(assembly_func.branch_cov) == 5


class TestCoverage:
    @pytest.fixture
    def basic_coverage(self, config, tmp_path) -> Coverage:
        test_file = "basic_contract_coverage.sol"
        source_path = tmp_path / test_file
        shutil.copy(SOURCES_PATH / test_file, source_path)

        cov = Coverage(config)
        assert len(cov.contracts_cov) == 1
        return cov

    @pytest.fixture
    def parent_coverage(self, config, tmp_path) -> Coverage:
        test_file = "parents_contract_coverage.sol"
        source_path = tmp_path / test_file
        shutil.copy(SOURCES_PATH / test_file, source_path)

        cov = Coverage(config)
        assert len(cov.contracts_cov) == 2
        return cov

    @pytest.mark.slow
    def test_get_contract_ide_coverage(self, basic_coverage):
        fqn = "basic_contract_coverage.sol:C"

        contract_coverage = basic_coverage.contracts_cov[fqn]

        for pc in contract_coverage.pc_branch_cov.keys():
            contract_coverage.add_cov(pc)
        for pc in contract_coverage.pc_modifier_cov.keys():
            contract_coverage.add_cov(pc)

        ide_branch_coverage = contract_coverage.get_ide_coverage()
        for records in ide_branch_coverage.values():
            for fn_rec in records.values():
                for branch in fn_rec.branch_records.values():
                    assert branch.coverage_hits == 1

    @pytest.mark.slow
    def test_process_trace(self, basic_coverage):
        fqn = "basic_contract_coverage.sol:C"
        contract_coverage = basic_coverage.contracts_cov[fqn]

        covered_pcs = random.sample(list(contract_coverage.pc_map.keys()), 50)

        trace = {"structLogs": [{"pc": pc, "op": "ADD"} for pc in covered_pcs]}

        basic_coverage.process_trace(fqn, trace)

        for pc in covered_pcs:
            assert pc in contract_coverage.pc_instruction_cov
            assert contract_coverage.pc_instruction_cov[pc].hit_count == 1

    @pytest.mark.slow
    def test_parent_coverage(self, parent_coverage):
        child = parent_coverage.contracts_cov["parents_contract_coverage.sol:Child"]
        parent = parent_coverage.contracts_cov["parents_contract_coverage.sol:Parent"]

        for pc in child.pc_branch_cov:
            child.add_cov(pc)
        for pc in parent.pc_branch_cov:
            parent.add_cov(pc)

        ide_coverage = parent_coverage.get_contract_ide_coverage(False)
        for file_path, coverages in ide_coverage.items():
            for fn_rec in coverages.values():
                if fn_rec.name == "Parent:function func1(uint a) public returns (uint)":
                    assert fn_rec.coverage_hits == 2
                    for branch in fn_rec.branch_records.values():
                        assert branch.coverage_hits == 2
                else:
                    assert fn_rec.coverage_hits == 1
                    for branch in fn_rec.branch_records.values():
                        assert branch.coverage_hits == 1


class TestCoverageProvider:
    def create_coverage_provider(
        self, test_files, config, tmp_path
    ) -> CoverageProvider:
        for test_file in test_files:
            source_path = tmp_path / test_file
            shutil.copy(SOURCES_PATH / test_file, source_path)

        cov = Coverage(config)
        coverage.default_chain = mock.MagicMock()
        provider = CoverageProvider(cov, None)
        return provider

    @pytest.fixture
    def basic_coverage_provider(self, config, tmp_path) -> CoverageProvider:
        test_file = "basic_contract_coverage.sol"
        return self.create_coverage_provider([test_file], config, tmp_path)

    @pytest.fixture
    def parents_coverage_provider(self, config, tmp_path) -> CoverageProvider:
        test_file = "parents_contract_coverage.sol"
        return self.create_coverage_provider([test_file], config, tmp_path)

    @pytest.fixture
    def calls_coverage_provider(self, config, tmp_path) -> CoverageProvider:
        test_file = "call_contract_coverage.sol"
        test_file_2 = "call_contract_coverage_2.sol"
        return self.create_coverage_provider([test_file, test_file_2], config, tmp_path)

    @pytest.mark.slow
    def test_basic_coverage(self, basic_coverage_provider):
        fqn = "basic_contract_coverage.sol:C"
        cov = basic_coverage_provider.get_coverage().contracts_cov[fqn]
        covered_pcs = random.sample(list(cov.pc_map.keys()), 50)
        trace = {"structLogs": [{"pc": pc, "op": "ADD"} for pc in covered_pcs]}

        basic_coverage_provider._dev_chain.get_block_number.return_value = 0
        basic_coverage_provider._dev_chain.get_block.return_value = {
            "transactions": [
                {"to": "0xA7910644A290B659B4049848bbe966388D30C0d7", "hash": "0x0"}
            ]
        }
        basic_coverage_provider._dev_chain.debug_trace_transaction.return_value = trace
        coverage.get_fqn_from_address = mock.MagicMock(return_value=fqn)

        basic_coverage_provider.update_coverage()

        for pc in covered_pcs:
            assert pc in cov.pc_instruction_cov
            assert cov.pc_instruction_cov[pc].hit_count == 1

        basic_coverage_provider._dev_chain.get_block_number.assert_called_once()
        basic_coverage_provider._dev_chain.get_block.assert_called_once()
        basic_coverage_provider._dev_chain.debug_trace_transaction.assert_called_once()
        coverage.get_fqn_from_address.assert_called_once()

    @pytest.mark.slow
    def test_calls_coverage(self, calls_coverage_provider):
        callee_fqn = "call_contract_coverage.sol:Callee"
        called_fqn = "call_contract_coverage_2.sol:Called"
        callee = calls_coverage_provider.get_coverage().contracts_cov[callee_fqn]
        called = calls_coverage_provider.get_coverage().contracts_cov[called_fqn]

        call_pc = [
            pc
            for pc in callee.pc_function.keys()
            if callee.pc_map[pc].op == "CALL"
            and callee.pc_function[pc].ident
            == "Callee:function call(uint a, address _addr) public payable"
        ][0]

        trace = {
            "structLogs": [{"pc": call_pc, "op": "CALL", "stack": ["0xff", "0x1"]}]
        }
        trace["structLogs"].extend([{"pc": pc, "op": "ADD"} for pc in called.pc_instruction_cov.keys()])  # type: ignore

        calls_coverage_provider._dev_chain.get_block_number.return_value = 0
        calls_coverage_provider._dev_chain.get_block.return_value = {
            "transactions": [
                {"to": "0xA7910644A290B659B4049848bbe966388D30C0d7", "hash": "0x0"}
            ]
        }
        calls_coverage_provider._dev_chain.debug_trace_transaction.return_value = trace
        coverage.get_fqn_from_address = mock.MagicMock()
        coverage.get_fqn_from_address.side_effect = [callee_fqn, called_fqn]

        calls_coverage_provider.update_coverage()

        assert coverage.get_fqn_from_address.call_count == 2
        for pc in called.pc_branch_cov:
            assert called.pc_branch_cov[pc].hit_count == 1
        assert (
            called.functions[
                "Called:function receive_A() public payable returns (uint)"
            ].calls
            == 1
        )

        ide_coverage = calls_coverage_provider._coverage.get_contract_ide_coverage(
            False
        )
        for file_name, ide_cov in ide_coverage.items():
            if called_fqn.split(":")[0] in str(file_name):
                for record in ide_cov.values():
                    assert record.coverage_hits == 1
            if callee_fqn.split(":")[0] in str(file_name):
                for record in ide_cov.values():
                    assert record.coverage_hits == 0

    @pytest.mark.slow
    def test_constructor(self, parents_coverage_provider):
        child_fqn = "parents_contract_coverage.sol:Child"
        undeployed_cov = (
            parents_coverage_provider.get_coverage().contracts_undeployed_cov[child_fqn]
        )

        trace = {
            "structLogs": [{"pc": pc, "op": "ADD"} for pc in undeployed_cov.pc_map]
        }

        parents_coverage_provider._dev_chain.get_block_number.return_value = 0
        parents_coverage_provider._dev_chain.get_block.return_value = {
            "transactions": [{"to": None, "hash": "0x0", "input": "0xABCD"}]
        }

        parents_coverage_provider._dev_chain.debug_trace_transaction.return_value = (
            trace
        )
        coverage.get_fqn_from_deployment_code = mock.MagicMock(return_value=child_fqn)

        parents_coverage_provider.update_coverage()

        for pc in undeployed_cov.pc_map:
            assert undeployed_cov.pc_instruction_cov[pc].hit_count == 1

        parents_coverage_provider._dev_chain.get_block_number.assert_called_once()
        parents_coverage_provider._dev_chain.get_block.assert_called_once()
        parents_coverage_provider._dev_chain.debug_trace_transaction.assert_called_once()
        coverage.get_fqn_from_deployment_code.assert_called_once()
