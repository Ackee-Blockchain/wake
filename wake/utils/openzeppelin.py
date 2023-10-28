import json
import platform
import subprocess
from typing import Optional

from wake.config import WakeConfig
from wake.core.solidity_version import SemanticVersion


def get_contracts_package_version(config: WakeConfig) -> Optional[SemanticVersion]:
    try:
        node_modules_path = next(
            path
            for path in config.compiler.solc.include_paths
            if "node_modules" in path.stem and path.is_dir()
        )
    except StopIteration:
        node_modules_path = config.project_root_path / "node_modules"
        if not node_modules_path.is_dir():
            return None

    try:
        out = subprocess.run(
            ["npm", "list", "@openzeppelin/contracts", "--depth=0"],
            capture_output=True,
            cwd=node_modules_path.parent,
            check=True,
            shell=(platform.system() == "Windows"),
        ).stdout.decode("utf-8")
        return SemanticVersion.fromstring(out.splitlines()[1].split("@")[-1])
    except Exception:
        return None
