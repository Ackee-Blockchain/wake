import asyncio
import os
import platform
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from git import Repo  # type: ignore

from wake.cli.__main__ import main
from wake.compiler import SolcOutputSelectionEnum, SolidityCompiler
from wake.compiler.solc_frontend import (
    SolcFrontend,
    SolcInputDebugInfoSettingsEnum,
    SolcInputDebugSettings,
    SolcInputOptimizerSettings,
    SolcInputSettings,
)
from wake.config import WakeConfig
from wake.core.enums import EvmVersionEnum
from wake.core.solidity_version import SolidityVersion
from wake.ir import ContractDefinition, FunctionCall, InlineAssembly
from wake.ir.enums import FunctionTypeKind, GlobalSymbol, InlineAssemblyEvmVersion
from wake.utils import change_cwd

PYTEST_BUILD_PATH = Path.home() / ".tmpwake_rkDv61DDf7"


@pytest.fixture()
def config():
    os.environ["XDG_CONFIG_HOME"] = str(PYTEST_BUILD_PATH)
    os.environ["XDG_DATA_HOME"] = str(PYTEST_BUILD_PATH)
    config_dict = {"compiler": {"solc": {"include_paths": ["./node_modules"]}}}
    return WakeConfig.fromdict(
        config_dict,
        project_root_path=PYTEST_BUILD_PATH,
    )


@pytest.fixture()
def setup_project(request):
    clone_url, dependencies_installer = request.param
    repo = None

    try:
        repo = Repo.clone_from(
            clone_url, PYTEST_BUILD_PATH, multi_options=["--depth=1"]
        )
        subprocess.run(
            [dependencies_installer, "install"],
            cwd=PYTEST_BUILD_PATH,
            shell=(platform.system() == "Windows"),
        )

        yield
    finally:

        def onerror(func, path, exc_info):
            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR)
                func(path)
            else:
                raise

        if repo is not None:
            repo.close()
        shutil.rmtree(PYTEST_BUILD_PATH, onerror=onerror)


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project",
    [(r"https://github.com/Uniswap/v3-core.git", "yarn")],
    indirect=True,
)
def test_compile_uniswap_v3(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config)
    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    (PYTEST_BUILD_PATH / "wake.toml").write_text(
        """
        [compiler.solc]
        exclude_paths = ["node_modules", "audits"]
        """
    )

    cli_runner = CliRunner()
    with change_cwd(PYTEST_BUILD_PATH):
        cli_result = cli_runner.invoke(
            main,
            ["compile"],
            env={
                "XDG_CONFIG_HOME": str(PYTEST_BUILD_PATH),
                "XDG_DATA_HOME": str(PYTEST_BUILD_PATH),
            },
        )
    assert cli_result.exit_code == 0


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project",
    [(r"https://github.com/graphprotocol/contracts.git", "yarn")],
    indirect=True,
)
@pytest.mark.skip()
def test_compile_the_graph(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config)
    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    compiler = SolidityCompiler(config)
    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    cli_runner = CliRunner()
    with change_cwd(PYTEST_BUILD_PATH):
        cli_result = cli_runner.invoke(
            main,
            ["compile"],
            env={
                "XDG_CONFIG_HOME": str(PYTEST_BUILD_PATH),
                "XDG_DATA_HOME": str(PYTEST_BUILD_PATH),
            },
        )
    assert cli_result.exit_code == 0


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project",
    [(r"https://github.com/traderjoe-xyz/joe-core.git", "yarn")],
    indirect=True,
)
def test_compile_trader_joe(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config)
    output = asyncio.run(
        compiler.compile(
            files,
            [SolcOutputSelectionEnum.ALL],
        )
    )
    assert len(output)

    output = asyncio.run(
        compiler.compile(
            files,
            [SolcOutputSelectionEnum.ALL],
        )
    )
    assert len(output)

    (PYTEST_BUILD_PATH / "wake.toml").write_text(
        """
        [compiler.solc]
        exclude_paths = ["node_modules", "test", "lib"]
        """
    )

    cli_runner = CliRunner()
    with change_cwd(PYTEST_BUILD_PATH):
        cli_result = cli_runner.invoke(
            main,
            ["compile"],
            env={
                "XDG_CONFIG_HOME": str(PYTEST_BUILD_PATH),
                "XDG_DATA_HOME": str(PYTEST_BUILD_PATH),
            },
        )
    assert cli_result.exit_code == 0


@pytest.mark.slow
@pytest.mark.parametrize(
    "setup_project",
    [(r"https://github.com/axelarnetwork/axelar-cgp-solidity.git", "npm")],
    indirect=True,
)
def test_compile_axelar(setup_project, config):
    files = list((PYTEST_BUILD_PATH / "contracts").rglob("*.sol"))
    compiler = SolidityCompiler(config)
    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    output = asyncio.run(compiler.compile(files, [SolcOutputSelectionEnum.ALL]))
    assert len(output)

    (PYTEST_BUILD_PATH / "wake.toml").write_text(
        """
        [compiler.solc.optimizer]
        enabled = true
        """
    )

    cli_runner = CliRunner()
    with change_cwd(PYTEST_BUILD_PATH):
        cli_result = cli_runner.invoke(
            main,
            ["compile"],
            env={
                "XDG_CONFIG_HOME": str(PYTEST_BUILD_PATH),
                "XDG_DATA_HOME": str(PYTEST_BUILD_PATH),
            },
        )
    assert cli_result.exit_code == 0


@pytest.mark.slow
@pytest.mark.platform_dependent
def test_compile_solidity_0_8_35(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    source_path = (
        Path(__file__).parent / "solidity_versions" / "solidity_0_8_35.sol"
    ).resolve()
    project_root = Path(__file__).parent.parent.resolve()
    config = WakeConfig.fromdict(
        {
            "compiler": {
                "solc": {
                    "target_version": "0.8.35",
                    "experimental": True,
                    "evm_version": "@future",
                    "via_SSA_CFG": True,
                    "optimizer": {"enabled": True},
                }
            }
        },
        project_root_path=project_root,
    )
    compiler = SolidityCompiler(config)

    build, errors = asyncio.run(
        compiler.compile(
            [source_path],
            [SolcOutputSelectionEnum.ALL],
            write_artifacts=False,
            force_recompile=True,
        )
    )

    assert errors == set()
    source_unit = build.source_units[source_path]
    inline_assembly = next(
        node for node in source_unit if isinstance(node, InlineAssembly)
    )
    assert inline_assembly.evm_version == InlineAssemblyEvmVersion.FUTURE
    contract = next(
        declaration
        for declaration in source_unit.declarations_iter()
        if isinstance(declaration, ContractDefinition)
    )
    assert contract.storage_layout is not None
    base_slot_expression = contract.storage_layout.base_slot_expression
    assert isinstance(base_slot_expression, FunctionCall)
    assert base_slot_expression.function_called == GlobalSymbol.ERC7201
    assert base_slot_expression.expression.type.kind == FunctionTypeKind.ERC7201

    frontend = SolcFrontend(config)
    version = SolidityVersion.fromstring("0.8.35")
    source = source_path.read_text()
    ssa_output = asyncio.run(
        frontend.compile(
            {},
            {"C.sol": source},
            version,
            SolcInputSettings(
                experimental=True,
                evm_version=EvmVersionEnum.FUTURE,
                via_SSA_CFG=True,
                optimizer=SolcInputOptimizerSettings(enabled=True),
                output_selection={"*": {"*": [SolcOutputSelectionEnum.YUL_CFG_JSON]}},
            ),
        )
    )
    assert ssa_output.contracts["C.sol"]["Solidity0835"].yul_CFG_json is not None

    ethdebug_output = asyncio.run(
        frontend.compile(
            {},
            {"C.sol": source},
            version,
            SolcInputSettings(
                experimental=True,
                via_IR=True,
                debug=SolcInputDebugSettings(
                    debug_info=[
                        SolcInputDebugInfoSettingsEnum.AST_ID,
                        SolcInputDebugInfoSettingsEnum.ETHDEBUG,
                    ]
                ),
                optimizer=SolcInputOptimizerSettings(enabled=False),
                output_selection={
                    "*": {
                        "*": [
                            SolcOutputSelectionEnum.EVM_BYTECODE_ETHDEBUG,
                            SolcOutputSelectionEnum.EVM_DEPLOYED_BYTECODE_ETHDEBUG,
                            SolcOutputSelectionEnum.ETHDEBUG_RESOURCES,
                            SolcOutputSelectionEnum.ETHDEBUG_COMPILATION,
                        ]
                    }
                },
            ),
        )
    )
    assert ethdebug_output.ethdebug is not None
    assert ethdebug_output.ethdebug["resources"] is not None
    assert ethdebug_output.ethdebug["compilation"] is not None
