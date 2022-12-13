import asyncio
import random
import shutil
from pathlib import Path, PurePath
from typing import Dict, List, Set, Tuple
from unittest import mock

import pytest
from intervaltree import IntervalTree

from woke.ast.ir.meta.source_unit import SourceUnit
from woke.ast.ir.reference_resolver import CallbackParams, ReferenceResolver
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import AstSolc
from woke.compile import SolcOutput, SolcOutputSelectionEnum, SolidityCompiler
from woke.compile.compilation_unit import CompilationUnit
from woke.compile.solc_frontend import SolcOutputErrorSeverityEnum
from woke.config import WokeConfig
from woke.testing import coverage
from woke.testing.coverage import ContractCoverage, Coverage, CoverageProvider

SOURCES_PATH = Path(__file__).parent.resolve() / "coverage_sources"


def compile_project(
    sample_path: Path, config: WokeConfig
) -> Tuple[Dict[Path, IntervalTree], Dict[Path, SourceUnit]]:
    sol_files: Set[Path] = {sample_path}

    compiler = SolidityCompiler(config)
    outputs: List[Tuple[CompilationUnit, SolcOutput]] = asyncio.run(
        compiler.compile(
            sol_files,
            [SolcOutputSelectionEnum.AST],
            maximize_compilation_units=True,
        )
    )

    errored = False
    for _, output in outputs:
        for error in output.errors:
            if error.severity == SolcOutputErrorSeverityEnum.ERROR:
                errored = True
    assert errored is False

    processed_files: Set[Path] = set()
    reference_resolver = ReferenceResolver()
    interval_trees: Dict[Path, IntervalTree] = {}
    source_units: Dict[Path, SourceUnit] = {}

    for cu, output in outputs:
        for source_unit_name, info in output.sources.items():
            path = cu.source_unit_name_to_path(PurePath(source_unit_name))
            ast = AstSolc.parse_obj(info.ast)

            reference_resolver.index_nodes(ast, path, cu.hash)

            if path in processed_files:
                continue
            processed_files.add(path)
            interval_trees[path] = IntervalTree()

            init = IrInitTuple(
                path,
                path.read_bytes(),
                cu,
                interval_trees[path],
                reference_resolver,
                output.contracts[source_unit_name]
                if source_unit_name in output.contracts
                else None,
            )
            source_units[path] = SourceUnit(init, ast)

    reference_resolver.run_post_process_callbacks(
        CallbackParams(interval_trees=interval_trees, source_units=source_units)
    )

    return interval_trees, source_units


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
    interval_trees, source_units = compile_project(source_path, config)
    source_file = source_units[source_path]
    assert len(source_file.contracts) == 1

    contract = source_file.contracts[0]
    interval_tree = interval_trees[source_path]

    assert contract.compilation_info is not None
    assert contract.compilation_info.evm is not None
    assert contract.compilation_info.evm.deployed_bytecode is not None

    opcodes = contract.compilation_info.evm.deployed_bytecode.opcodes
    source_map = contract.compilation_info.evm.deployed_bytecode.source_map
    line_intervals = coverage._get_line_intervals(contract.file.read_text())

    assert opcodes is not None
    assert source_map is not None

    pc_op_map = coverage._parse_opcodes(opcodes)
    pc_map = coverage._parse_source_map(interval_tree, source_map, pc_op_map)

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

    def test_get_ide_branch_coverage(self, basic_contract_coverage):
        for pc in basic_contract_coverage.pc_branch_cov.keys():
            basic_contract_coverage.add_cov(pc)

        ide_branch_coverage = basic_contract_coverage.get_ide_branch_coverage()
        for record in ide_branch_coverage.values():
            assert record.coverage_hits == 1

    def test_get_ide_modifier_coverage(self, basic_contract_coverage):
        for pc in basic_contract_coverage.pc_modifier_cov.keys():
            basic_contract_coverage.add_cov(pc)

        ide_modifier_coverage = (
            basic_contract_coverage.get_ide_modifier_calls_coverage()
        )
        for record in ide_modifier_coverage.values():
            assert record.coverage_hits == 1

    def test_get_ide_function_calls_coverage(self, basic_contract_coverage):
        for pc in basic_contract_coverage.pc_instruction_cov.keys():
            basic_contract_coverage.add_cov(pc)

        ide_function_calls_coverage = (
            basic_contract_coverage.get_ide_function_calls_coverage()
        )
        for record in ide_function_calls_coverage.values():
            assert record.coverage_hits == 1


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

    def test_covered_contracts(self, basic_coverage):
        fqn = "basic_contract_coverage.sol:C"
        assert len(basic_coverage.get_covered_contracts()) == 1
        assert list(basic_coverage.get_covered_contracts())[0] == fqn

    def test_get_contract_coverage(self, basic_coverage):
        fqn = "basic_contract_coverage.sol:C"
        contract_coverage = basic_coverage.get_contract_coverage(fqn, False)
        assert contract_coverage == basic_coverage.contracts_cov[fqn]
        contract_coverage = basic_coverage.get_contract_coverage(fqn, True)
        assert contract_coverage == basic_coverage.contracts_per_trans_cov[fqn]

    def test_get_contract_ide_coverage(self, basic_coverage):
        fqn = "basic_contract_coverage.sol:C"

        contract_coverage = basic_coverage.get_contract_coverage(fqn, False)

        for pc in contract_coverage.pc_branch_cov.keys():
            contract_coverage.add_cov(pc)
        for pc in contract_coverage.pc_modifier_cov.keys():
            contract_coverage.add_cov(pc)

        ide_branch_coverage = contract_coverage.get_ide_branch_coverage()
        for record in ide_branch_coverage.values():
            assert record.coverage_hits == 1

    def test_process_trace(self, basic_coverage):
        fqn = "basic_contract_coverage.sol:C"
        contract_coverage = basic_coverage.get_contract_coverage(fqn, False)

        covered_pcs = random.sample(list(contract_coverage.pc_map.keys()), 50)

        trace = {"structLogs": [{"pc": pc, "op": "ADD"} for pc in covered_pcs]}

        basic_coverage.process_trace(fqn, trace)

        for pc in covered_pcs:
            assert pc in contract_coverage.pc_instruction_cov
            assert contract_coverage.pc_instruction_cov[pc].hit_count == 1

    def test_parent_coverage(self, parent_coverage):
        child = parent_coverage.contracts_cov["parents_contract_coverage.sol:Child"]
        parent = parent_coverage.contracts_cov["parents_contract_coverage.sol:Parent"]

        for pc in child.pc_branch_cov:
            child.add_cov(pc)
        for pc in parent.pc_branch_cov:
            parent.add_cov(pc)

        parents_pos = [l.branch.ide_pos for l in parent.pc_branch_cov.values()]
        child_pos = [l.branch.ide_pos for l in child.pc_branch_cov.values()]

        ide_coverage = parent_coverage.get_contract_ide_coverage(False)
        for file, coverages in ide_coverage.items():
            for record in coverages:
                pos = (
                    (record["startLine"], record["startCol"]),
                    (record["endLine"], record["endCol"]),
                )
                if pos in parents_pos:
                    assert record["coverageHits"] == 2
                elif pos in child_pos:
                    assert record["coverageHits"] == 1


class TestCoverageProvider:
    @pytest.fixture
    def basic_coverage_provider(self, config, tmp_path) -> CoverageProvider:
        test_file = "basic_contract_coverage.sol"
        source_path = tmp_path / test_file
        shutil.copy(SOURCES_PATH / test_file, source_path)

        cov = Coverage(config)
        coverage.default_chain = mock.MagicMock()
        provider = CoverageProvider(cov, None)
        return provider

    @pytest.fixture
    def calls_coverage_provider(self, config, tmp_path) -> CoverageProvider:
        test_file = "call_contract_coverage.sol"
        source_path = tmp_path / test_file
        shutil.copy(SOURCES_PATH / test_file, source_path)

        cov = Coverage(config)
        coverage.default_chain = mock.MagicMock()
        provider = CoverageProvider(cov, None)
        return provider

    def test_get_coverage(self, basic_coverage_provider):
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

    def test_calls_coverage(self, calls_coverage_provider):
        callee_fqn = "call_contract_coverage.sol:Callee"
        called_fqn = "call_contract_coverage.sol:Called"
        callee = calls_coverage_provider.get_coverage().contracts_cov[callee_fqn]
        called = calls_coverage_provider.get_coverage().contracts_cov[called_fqn]

        call_pc = [
            pc
            for pc in callee.pc_function.keys()
            if callee.pc_map[pc].op == "CALL"
            and callee.pc_function[pc].name == "Callee.call"
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
        assert called._functions["Called.receive_A"].calls == 1
