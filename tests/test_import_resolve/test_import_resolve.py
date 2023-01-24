import os
from pathlib import Path

import pytest

from woke.compiler.source_unit_name_resolver import SourceUnitNameResolver
from woke.config import WokeConfig
from woke.utils import change_cwd

current_path = Path(__file__).parent.resolve()


@pytest.mark.platform_dependent
def test_simple():
    # no config files loaded => no remappings
    os.environ["XDG_CONFIG_HOME"] = str(current_path)
    config = WokeConfig(project_root_path=current_path)
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


@pytest.mark.platform_dependent
def test_cmdline_args():
    os.environ["XDG_CONFIG_HOME"] = str(current_path)
    config = WokeConfig.fromdict(
        {
            "compiler": {
                "solc": {
                    "remappings": [
                        "contracts/a.sol:https://github.com=github",
                        "contracts/a.sol:https://github.co=shorter_than_the_previous_one",
                        "@OpenZeppelin=this_will_be_ignored",
                        ":@OpenZeppelin=node_modules/openzeppelin",
                    ]
                }
            }
        },
        project_root_path=current_path / "project1",
    )
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


@pytest.mark.platform_dependent
def test_remappings():
    os.environ["XDG_CONFIG_HOME"] = str(current_path)
    config = WokeConfig.fromdict(
        {
            "compiler": {
                "solc": {
                    "remappings": [
                        "contracts/a.sol:https://github.com=github",
                        "contracts/a.sol:https://github.co=shorter_than_the_previous_one",
                        "@OpenZeppelin=this_will_be_ignored",
                        ":@OpenZeppelin=node_modules/openzeppelin",
                    ]
                }
            }
        },
    )
    resolver = SourceUnitNameResolver(config)

    assert (
        resolver.resolve_import("contracts/a.sol", "https://github.com/test/abc.sol")
        == "github/test/abc.sol"
    )
    assert (
        resolver.resolve_import("contracts/a.sol", "@OpenZeppelin/test.sol")
        == "node_modules/openzeppelin/test.sol"
    )
