from pathlib import Path

from woke.a_config import WokeConfig
from woke.d_compile.source_unit_name_resolver import SourceUnitNameResolver
from woke.utils import change_cwd

current_path = Path(__file__).parent.resolve()


def test_simple():
    # no config files loaded => no remappings
    config = WokeConfig(project_root_path=current_path, woke_root_path=current_path)
    resolver = SourceUnitNameResolver(config)
    assert (
        resolver.resolve_import("contracts/a.sol", "./util.sol") == "contracts/util.sol"
    )
    assert resolver.resolve_import("contracts/a.sol", "../token.sol") == "token.sol"
    assert (
        resolver.resolve_import("contracts/a.sol", "./x/x.sol") == "contracts/x/x.sol"
    )
    assert (
        resolver.resolve_import("contracts/a.sol", "contracts/tokens/y.sol")
        == "contracts/tokens/y.sol"
    )
    assert (
        resolver.resolve_import("lib/src/..///contract.sol", "./util/./util.sol")
        == "lib/src/../util/util.sol"
    )
    assert (
        resolver.resolve_import("lib/src/../contract.sol", "./util///util.sol")
        == "lib/src/../util/util.sol"
    )
    assert (
        resolver.resolve_import("lib/src/../contract.sol", "../util/../array/util.sol")
        == "lib/src/array/util.sol"
    )
    assert (
        resolver.resolve_import("lib/src/../contract.sol", "../.././../util.sol")
        == "util.sol"
    )
    assert (
        resolver.resolve_import("lib/src/../contract.sol", "../../.././../util.sol")
        == "util.sol"
    )
    assert (
        resolver.resolve_import("protocol://test/abc.sol", "./dummy.sol")
        == "protocol://test/dummy.sol"
    )
    assert (
        resolver.resolve_import("protocol://test/abc///", "./dummy.sol")
        == "protocol://test/dummy.sol"
    )


def test_cmdline_args():
    config = WokeConfig(
        project_root_path=current_path / "project1", woke_root_path=current_path
    )
    config.load_configs()
    resolver = SourceUnitNameResolver(config)

    with change_cwd(current_path):
        assert (
            resolver.resolve_cmdline_arg("project1/contracts/a.sol")
            == "contracts/a.sol"
        )
        assert (
            resolver.resolve_cmdline_arg("project1/interfaces/b.sol")
            == "interfaces/b.sol"
        )


def test_remappings():
    config = WokeConfig(
        project_root_path=current_path / "project1", woke_root_path=current_path
    )
    config.load_configs()
    resolver = SourceUnitNameResolver(config)
    assert (
        resolver.resolve_import("contracts/a.sol", "https://github.com/test/abc.sol")
        == "github/test/abc.sol"
    )
    assert (
        resolver.resolve_import("contracts/a.sol", "@OpenZeppelin/test.sol")
        == "node_modules/openzeppelin/test.sol"
    )
