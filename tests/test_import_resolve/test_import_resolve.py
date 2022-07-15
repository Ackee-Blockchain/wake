from pathlib import Path, PurePath

import pytest

from woke.compile.source_unit_name_resolver import SourceUnitNameResolver
from woke.config import WokeConfig
from woke.utils import change_cwd

current_path = Path(__file__).parent.resolve()


@pytest.mark.platform_dependent
def test_simple():
    # no config files loaded => no remappings
    config = WokeConfig(project_root_path=current_path, woke_root_path=current_path)
    resolver = SourceUnitNameResolver(config)
    assert resolver.resolve_import(
        PurePath("contracts/a.sol"), "./util.sol"
    ) == PurePath("contracts/util.sol")
    assert resolver.resolve_import(
        PurePath("contracts/a.sol"), "../token.sol"
    ) == PurePath("token.sol")
    assert resolver.resolve_import(
        PurePath("contracts/a.sol"), "./x/x.sol"
    ) == PurePath("contracts/x/x.sol")
    assert resolver.resolve_import(
        PurePath("contracts/a.sol"), "contracts/tokens/y.sol"
    ) == PurePath("contracts/tokens/y.sol")
    assert resolver.resolve_import(
        PurePath("lib/src/..///contract.sol"), "./util/./util.sol"
    ) == PurePath("lib/src/../util/util.sol")
    assert resolver.resolve_import(
        PurePath("lib/src/../contract.sol"), "./util///util.sol"
    ) == PurePath("lib/src/../util/util.sol")
    assert resolver.resolve_import(
        PurePath("lib/src/../contract.sol"), "../util/../array/util.sol"
    ) == PurePath("lib/src/array/util.sol")
    assert resolver.resolve_import(
        PurePath("lib/src/../contract.sol"), "../.././../util.sol"
    ) == PurePath("util.sol")
    assert resolver.resolve_import(
        PurePath("lib/src/../contract.sol"), "../../.././../util.sol"
    ) == PurePath("util.sol")
    assert resolver.resolve_import(
        PurePath("protocol://test/abc.sol"), "./dummy.sol"
    ) == PurePath("protocol://test/dummy.sol")
    assert resolver.resolve_import(
        PurePath("protocol://test/abc///"), "./dummy.sol"
    ) == PurePath("protocol://test/dummy.sol")


@pytest.mark.platform_dependent
def test_cmdline_args():
    config = WokeConfig(
        project_root_path=current_path / "project1", woke_root_path=current_path
    )
    config.load_configs()
    resolver = SourceUnitNameResolver(config)

    with change_cwd(current_path):
        assert resolver.resolve_cmdline_arg("project1/contracts/a.sol") == PurePath(
            "contracts/a.sol"
        )
        assert resolver.resolve_cmdline_arg("project1/interfaces/b.sol") == PurePath(
            "interfaces/b.sol"
        )


@pytest.mark.platform_dependent
def test_remappings():
    config = WokeConfig(
        project_root_path=current_path / "project1", woke_root_path=current_path
    )
    config.load_configs()
    resolver = SourceUnitNameResolver(config)
    assert resolver.resolve_import(
        PurePath("contracts/a.sol"), "https://github.com/test/abc.sol"
    ) == PurePath("github/test/abc.sol")
    assert resolver.resolve_import(
        PurePath("contracts/a.sol"), "@OpenZeppelin/test.sol"
    ) == PurePath("node_modules/openzeppelin/test.sol")
