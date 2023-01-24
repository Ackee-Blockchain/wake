import os
from pathlib import Path

import pydantic
import pytest

from woke.config import WokeConfig
from woke.config.data_model import SolcRemapping
from woke.core.enums import EvmVersionEnum
from woke.core.solidity_version import SolidityVersion

sources_path = (Path(__file__).parent / "config_sources").resolve()


@pytest.mark.platform_dependent
def test_config_empty():
    config = WokeConfig()
    assert len(config.loaded_files) == 0

    file_path = (sources_path / "empty.toml").resolve()
    config.load(file_path)
    assert len(config.loaded_files) == 1
    assert file_path in config.loaded_files
    assert len(config.compiler.solc.remappings) == 0


@pytest.mark.platform_dependent
def test_config_simple():
    os.environ["XDG_CONFIG_HOME"] = str(sources_path)

    config = WokeConfig()
    config.load_configs()  # should not have any effect
    assert len(config.loaded_files) == 0
    assert config.global_config_path.resolve() == sources_path / "woke"
    assert len(config.compiler.solc.remappings) == 0

    config.load(sources_path / "a.toml")
    assert config.global_config_path.resolve() == sources_path / "woke"
    assert len(config.loaded_files) == 4
    assert (sources_path / "a.toml").resolve() in config.loaded_files
    assert (sources_path / "b.toml").resolve() in config.loaded_files
    assert (sources_path / "c.toml").resolve() in config.loaded_files
    assert (sources_path / "empty.toml").resolve() in config.loaded_files
    assert len(config.compiler.solc.remappings) == 1
    assert config.compiler.solc.remappings[0] == SolcRemapping(
        context=None, prefix="xyz", target=None
    )
    assert str(config.compiler.solc.remappings[0]) == ":xyz="
    assert len(config.compiler.solc.include_paths) == 1
    assert sources_path in config.compiler.solc.include_paths
    assert len(config.compiler.solc.allow_paths) == 1
    assert (sources_path / "../").resolve() in config.compiler.solc.allow_paths


def test_config_from_dict():
    os.environ["XDG_CONFIG_HOME"] = str(sources_path)
    config_dict = {
        "compiler": {
            "solc": {
                "allow_paths": ["."],
                "evm_version": "london",
                "include_paths": ["../"],
                "remappings": ["hardhat/=node_modules/hardhat/"],
                "target_version": "0.8.12",
            }
        }
    }
    config = WokeConfig.fromdict(
        config_dict,
        project_root_path=(sources_path / "containing_global_conf"),
    )

    assert len(config.compiler.solc.allow_paths) == 1
    assert sources_path / "containing_global_conf" in config.compiler.solc.allow_paths
    assert config.compiler.solc.evm_version == EvmVersionEnum.LONDON
    assert len(config.compiler.solc.include_paths) == 1
    assert sources_path in config.compiler.solc.include_paths
    assert len(config.compiler.solc.remappings) == 1
    assert config.compiler.solc.remappings[0] == SolcRemapping(
        context=None, prefix="hardhat/", target="node_modules/hardhat/"
    )
    assert config.compiler.solc.target_version == SolidityVersion.fromstring("0.8.12")


@pytest.mark.platform_dependent
def test_config_global():
    os.environ["XDG_CONFIG_HOME"] = str(sources_path / "containing_global_conf")
    config = WokeConfig()
    assert len(config.loaded_files) == 0
    config.load_configs()
    assert len(config.loaded_files) == 2
    assert (
        sources_path / "containing_global_conf" / "woke" / "config.toml"
    ).resolve() in config.loaded_files
    assert (sources_path / "empty.toml").resolve() in config.loaded_files
    assert len(config.compiler.solc.remappings) == 2
    assert config.compiler.solc.remappings[0] == SolcRemapping(
        context=None, prefix="https://url.com", target=None
    )
    assert config.compiler.solc.remappings[1] == SolcRemapping(
        context=None, prefix="123", target="xyz"
    )


@pytest.mark.platform_dependent
def test_config_project():
    os.environ["XDG_CONFIG_HOME"] = str(sources_path / "containing_global_conf")
    config = WokeConfig(
        project_root_path=(sources_path / "containing_project_conf"),
    )
    config.load_configs()

    assert len(config.compiler.solc.remappings) == 1
    assert config.compiler.solc.remappings[0] == SolcRemapping(
        context=None, prefix="woke", target="test-target"
    )


@pytest.mark.platform_dependent
def test_config_project_path_not_dir():
    with pytest.raises(ValueError):
        config = WokeConfig(project_root_path=(sources_path / "a,toml"))


@pytest.mark.platform_dependent
def test_config_import_abs_path():
    os.environ["XDG_CONFIG_HOME"] = str(sources_path)
    tmp_file = sources_path / "tmp_bHtvhGrDp6.toml"
    abs_path = (sources_path / "a.toml").resolve()
    content = 'subconfigs = ["{path}"]'.format(path=str(abs_path).replace("\\", "\\\\"))

    tmp_file.write_text(content)
    config = WokeConfig()
    # this one should load: a.toml -> b.toml -> c.toml
    config.load(tmp_file)

    assert len(config.loaded_files) == 5
    assert tmp_file.resolve() in config.loaded_files
    assert (sources_path / "a.toml").resolve() in config.loaded_files
    assert (sources_path / "b.toml").resolve() in config.loaded_files
    assert (sources_path / "c.toml").resolve() in config.loaded_files
    assert (sources_path / "empty.toml").resolve() in config.loaded_files
    assert len(config.compiler.solc.remappings) == 1
    assert config.compiler.solc.remappings[0] == SolcRemapping(
        context=None, prefix="xyz", target=None
    )
    assert len(config.compiler.solc.include_paths) == 1
    assert sources_path in config.compiler.solc.include_paths

    tmp_file.unlink()


@pytest.mark.platform_dependent
def test_config_invalid_format():
    os.environ["XDG_CONFIG_HOME"] = str(sources_path)
    config = WokeConfig()

    with pytest.raises(pydantic.ValidationError):
        config.load(sources_path / "invalid_1.toml")
    with pytest.raises(pydantic.ValidationError):
        config.load(sources_path / "invalid_2.toml")
    with pytest.raises(pydantic.ValidationError):
        config.load(sources_path / "invalid_3.toml")


@pytest.mark.platform_dependent
def test_config_cyclic_import():
    os.environ["XDG_CONFIG_HOME"] = str(sources_path)
    config = WokeConfig()
    with pytest.raises(ValueError):
        config.load(sources_path / "cyclic_x.toml")

    with pytest.raises(ValueError):
        config.load(sources_path / "cyclic_1.toml")

    with pytest.raises(ValueError):
        config.load(sources_path / "cyclic_2.toml")
