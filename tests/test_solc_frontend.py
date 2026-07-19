import asyncio
import json

import pytest

from wake.compiler import SolcOutputSelectionEnum, SolidityCompiler
from wake.compiler.solc_frontend import (
    SolcFrontend,
    SolcInput,
    SolcInputDebugInfoSettingsEnum,
    SolcInputSettings,
    SolcOutput,
)
from wake.config import WakeConfig
from wake.core.enums import EvmVersionEnum
from wake.core.solidity_version import SolidityVersion


def test_solidity_0_8_35_standard_json_models():
    settings = SolcInputSettings(
        experimental=True,
        evm_version=EvmVersionEnum.FUTURE,
        via_SSA_CFG=True,
    )

    assert settings.model_dump(by_alias=True, exclude_none=True) == {
        "experimental": True,
        "evmVersion": "@future",
        "viaSSACFG": True,
    }

    output = SolcOutput.model_validate(
        {
            "contracts": {
                "C.sol": {
                    "C": {
                        "yulCFGJson": {},
                        "evm": {
                            "bytecode": {"ethdebug": {}},
                            "deployedBytecode": {"ethdebug": {}},
                        },
                    }
                }
            },
            "ethdebug": {"resources": {}, "compilation": {}},
        }
    )

    contract = output.contracts["C.sol"]["C"]
    assert contract.yul_CFG_json == {}
    assert contract.evm is not None
    assert contract.evm.bytecode is not None
    assert contract.evm.bytecode.ethdebug == {}
    assert contract.evm.deployed_bytecode is not None
    assert contract.evm.deployed_bytecode.ethdebug == {}
    assert output.ethdebug == {"resources": {}, "compilation": {}}


@pytest.mark.parametrize(
    ("value", "expected", "experimental"),
    (
        ("ast-id", SolcInputDebugInfoSettingsEnum.AST_ID, False),
        ("ethdebug", SolcInputDebugInfoSettingsEnum.ETHDEBUG, True),
    ),
)
def test_solidity_0_8_35_debug_info_input(value, expected, experimental):
    standard_input = SolcInput.model_validate_json(
        json.dumps(
            {
                "language": "Solidity",
                "sources": {"C.sol": {"content": "contract C {}"}},
                "settings": {
                    "experimental": experimental,
                    "debug": {"debugInfo": [value]},
                },
            }
        )
    )

    assert standard_input.settings is not None
    assert standard_input.settings.debug is not None
    assert standard_input.settings.debug.debug_info == [expected]
    serialized = json.loads(
        standard_input.model_dump_json(by_alias=True, exclude_none=True)
    )
    assert serialized["settings"]["debug"] == {"debugInfo": [value]}


def test_global_experimental_outputs_remain_globally_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    config = WakeConfig(project_root_path=tmp_path)
    compiler = SolidityCompiler(config)
    settings = SolcInputSettings(
        output_selection={
            "*": {
                "": [SolcOutputSelectionEnum.AST],
                "*": [
                    SolcOutputSelectionEnum.ABI,
                    SolcOutputSelectionEnum.ETHDEBUG_RESOURCES,
                    SolcOutputSelectionEnum.ETHDEBUG_COMPILATION,
                ],
            }
        }
    )

    optimized = compiler.optimize_build_settings(settings, {"C.sol"})

    assert optimized.output_selection == {
        "*": {
            "": [SolcOutputSelectionEnum.AST],
            "*": [
                SolcOutputSelectionEnum.ETHDEBUG_RESOURCES,
                SolcOutputSelectionEnum.ETHDEBUG_COMPILATION,
            ],
        },
        "C.sol": {"*": [SolcOutputSelectionEnum.ABI]},
    }


def test_compiler_build_settings_include_experimental_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    config = WakeConfig.fromdict(
        {
            "compiler": {
                "solc": {
                    "experimental": True,
                    "evm_version": "@future",
                    "via_SSA_CFG": True,
                }
            }
        },
        project_root_path=tmp_path,
    )

    settings = SolidityCompiler(config).create_build_settings([], None)

    assert settings.experimental is True
    assert settings.evm_version == EvmVersionEnum.FUTURE
    assert settings.via_SSA_CFG is True


def test_solidity_0_8_35_settings_are_not_forwarded_to_older_compilers(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    config = WakeConfig(project_root_path=tmp_path)
    captured = {}

    async def run_solc(_self, target_version, standard_input):
        captured["target_version"] = target_version
        captured["settings"] = standard_input.settings
        return SolcOutput()

    monkeypatch.setattr(SolcFrontend, "_SolcFrontend__run_solc", run_solc)
    frontend = SolcFrontend(config)

    asyncio.run(
        frontend.compile(
            {},
            {"C.sol": "pragma solidity 0.8.34; contract C {}"},
            SolidityVersion.fromstring("0.8.34"),
            SolcInputSettings(
                experimental=True,
                evm_version=EvmVersionEnum.FUTURE,
                via_SSA_CFG=True,
            ),
        )
    )

    assert captured["target_version"] == SolidityVersion.fromstring("0.8.34")
    assert captured["settings"].experimental is None
    assert captured["settings"].via_SSA_CFG is None
    assert captured["settings"].evm_version == EvmVersionEnum.OSAKA
