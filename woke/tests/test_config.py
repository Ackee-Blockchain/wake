from pathlib import Path, PosixPath, WindowsPath
import pydantic
import pytest

from woke.a_config import WokeConfig, SolcRemapping


sources_path = Path(__file__).parent.resolve() / "config_sources"


@pytest.mark.platform_dependent
def test_config_empty():
    config = WokeConfig(woke_root_path=sources_path)
    assert config.woke_root_path.resolve() == sources_path.resolve()
    assert len(config.loaded_files) == 0

    file_path = (sources_path / "empty.toml").resolve()
    config.load(file_path)
    assert len(config.loaded_files) == 1
    assert file_path in config.loaded_files
    assert len(config.solc.remappings) == 0


@pytest.mark.platform_dependent
def test_config_simple():
    config = WokeConfig(woke_root_path=sources_path)
    config.load_configs()  # should not have any effect
    assert len(config.loaded_files) == 0
    assert config.woke_root_path.resolve() == sources_path.resolve()
    assert len(config.solc.remappings) == 0

    config.load(sources_path / "a.toml")
    assert config.woke_root_path.resolve() == sources_path.resolve()
    assert len(config.loaded_files) == 4
    assert (sources_path / "a.toml").resolve() in config.loaded_files
    assert (sources_path / "b.toml").resolve() in config.loaded_files
    assert (sources_path / "c.toml").resolve() in config.loaded_files
    assert (sources_path / "empty.toml").resolve() in config.loaded_files
    assert len(config.solc.remappings) == 1
    assert config.solc.remappings[0] == SolcRemapping(None, "xyz", None)

    # loaded config should be short enough not to be truncated by reprlib.repr
    repr_config = eval(repr(config))
    assert repr_config.woke_root_path.resolve() == sources_path.resolve()
    assert len(repr_config.loaded_files) == 0
    assert len(repr_config.solc.remappings) == 1
    assert repr_config.solc.remappings[0] == SolcRemapping(None, "xyz", None)


@pytest.mark.platform_dependent
def test_config_global():
    config = WokeConfig(woke_root_path=(sources_path / "containing_global_conf"))
    assert len(config.loaded_files) == 0
    config.load_configs()
    assert len(config.loaded_files) == 2
    assert (
        sources_path / "containing_global_conf" / "config.toml"
    ).resolve() in config.loaded_files
    assert (sources_path / "empty.toml").resolve() in config.loaded_files
    assert len(config.solc.remappings) == 2
    assert config.solc.remappings[0] == SolcRemapping(None, "https://url.com", None)
    assert config.solc.remappings[1] == SolcRemapping(None, "123", "xyz")


@pytest.mark.platform_dependent
def test_config_project():
    config = WokeConfig(
        project_root_path=(sources_path / "containing_project_conf"),
        woke_root_path=(sources_path / "containing_global_conf"),
    )
    config.load_configs()

    assert len(config.solc.remappings) == 1
    assert config.solc.remappings[0] == SolcRemapping(None, "woke", "test-target")


@pytest.mark.platform_dependent
def test_config_import_abs_path():
    tmp_file = sources_path / "tmp_bHtvhGrDp6.toml"
    abs_path = (sources_path / "a.toml").resolve()
    content = 'imports = ["{path}"]'.format(path=str(abs_path).replace("\\", "\\\\"))

    tmp_file.write_text(content)
    config = WokeConfig(woke_root_path=sources_path)
    # this one should load: a.toml -> b.toml -> c.toml
    config.load(tmp_file)

    assert len(config.loaded_files) == 5
    assert tmp_file.resolve() in config.loaded_files
    assert (sources_path / "a.toml").resolve() in config.loaded_files
    assert (sources_path / "b.toml").resolve() in config.loaded_files
    assert (sources_path / "c.toml").resolve() in config.loaded_files
    assert (sources_path / "empty.toml").resolve() in config.loaded_files
    assert len(config.solc.remappings) == 1
    assert config.solc.remappings[0] == SolcRemapping(None, "xyz", None)

    tmp_file.unlink()


@pytest.mark.platform_dependent
def test_config_invalid_format():
    config = WokeConfig(woke_root_path=sources_path)

    with pytest.raises(pydantic.ValidationError):
        config.load(sources_path / "invalid_1.toml")
    with pytest.raises(pydantic.ValidationError):
        config.load(sources_path / "invalid_2.toml")
    with pytest.raises(pydantic.ValidationError):
        config.load(sources_path / "invalid_3.toml")


@pytest.mark.platform_dependent
def test_config_cyclic_import():
    config = WokeConfig(woke_root_path=sources_path)
    with pytest.raises(ValueError):
        config.load(sources_path / "cyclic_x.toml")

    with pytest.raises(ValueError):
        config.load(sources_path / "cyclic_1.toml")

    with pytest.raises(ValueError):
        config.load(sources_path / "cyclic_2.toml")
