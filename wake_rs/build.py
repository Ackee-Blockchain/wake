import os
import platform
import shlex
import shutil
import subprocess
import zipfile

from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def maturin(*args):
    # Prepare environment for maturin execution
    env = os.environ.copy()  # Start with current environment

    # On ARM Windows, ensure Cargo bin directory is in PATH
    if platform.system() == 'Windows' and platform.machine().lower() in ['arm64', 'aarch64']:  # ARM Windows
        userprofile = os.getenv('USERPROFILE')
        if userprofile:
            cargo_bin = os.path.join(userprofile, '.cargo', 'bin')
            if os.path.exists(cargo_bin):
                current_path = env.get('PATH', '')
                if cargo_bin not in current_path:
                    env['PATH'] = cargo_bin + os.pathsep + current_path
                    print(f"Added {cargo_bin} to PATH for maturin execution (ARM Windows)")
                else:
                    print(f"Cargo bin directory already in PATH: {cargo_bin}")
            else:
                print(f"Warning: Cargo bin directory not found: {cargo_bin}")
        else:
            print("Warning: USERPROFILE environment variable not set")

    subprocess.call(["maturin", *list(args)], env=env)


def build():
    print("Starting Rust build process")
    # Store the original directory to restore it later
    original_dir = os.getcwd()

    # Get absolute paths before changing directory
    wake_rs_dir = Path(__file__).parent.absolute()
    build_dir = wake_rs_dir / "build"
    wheels_dir = wake_rs_dir / "target/wheels"

    print(f"wake_rs_dir: {wake_rs_dir}")
    print(f"wheels_dir: {wheels_dir}")

    build_dir.mkdir(parents=True, exist_ok=True)
    if wheels_dir.exists():
        shutil.rmtree(wheels_dir)

    # Change to wake_rs directory for maturin build
    os.chdir(wake_rs_dir)

    cargo_args = []
    if os.getenv("MATURIN_BUILD_ARGS"):
        cargo_args = shlex.split(os.getenv("MATURIN_BUILD_ARGS", ""))

    print(f"Running maturin build with args: {cargo_args}")
    if platform.system() == 'Linux':
        maturin("build", "--auditwheel", "skip", "--release", "--strip", *cargo_args)
    else:
        maturin("build", "--release", "--strip", *cargo_args)

    # We won't use the wheel built by maturin directly since
    # we want Hatchling to build it, but we need to retrieve the
    # compiled extensions from the maturin wheel.
    wheel_files = list(wheels_dir.glob("*.whl"))
    print(f"Found wheel files: {wheel_files}")

    wheel = next(iter(wheels_dir.glob("*.whl")))
    print(f"Extracting wheel: {wheel}")

    with zipfile.ZipFile(wheel.as_posix()) as whl:
        whl.extractall(wheels_dir.as_posix())

        # Create __init__.py if it doesn't exist
        init_file = wake_rs_dir / "__init__.py"
        if not init_file.exists():
            init_file.touch()
            print(f"Created __init__.py: {init_file}")

        # Copy all .so/.pyd files to wake_rs directory
        so_files = list(wheels_dir.rglob("**/*.so"))
        pyd_files = list(wheels_dir.rglob("**/*.pyd"))
        print(f"Found .so files: {so_files}")
        print(f"Found .pyd files: {pyd_files}")

        for extension in so_files:
            dest = wake_rs_dir / extension.name
            shutil.copyfile(extension, dest)
            mode = os.stat(dest).st_mode
            mode |= (mode & 0o444) >> 2
            os.chmod(dest, mode)
            print(f"Copied .so: {extension} -> {dest}")

        for extension in pyd_files:
            dest = wake_rs_dir / extension.name
            shutil.copyfile(extension, dest)
            print(f"Copied .pyd: {extension} -> {dest}")

    # List final wake_rs directory contents
    final_files = list(wake_rs_dir.glob("*"))
    print(f"Final wake_rs contents: {[f.name for f in final_files]}")

    shutil.rmtree(wheels_dir)

    # Restore the original directory
    os.chdir(original_dir)
    print("Rust build completed")


class CustomBuildHook(BuildHookInterface):
    """Custom build hook for compiling Rust extensions with Maturin."""

    def initialize(self, version, build_data):
        """Initialize hook - called before build starts."""
        build_data["infer_tag"] = True
        build_data["pure_pyton"] = False

        # Clean up old dynamic libraries before building new ones
        wake_rs_dir = Path(__file__).parent.absolute()

        # Remove .so and .pyd files from previous builds
        for so_file in wake_rs_dir.glob("*.so"):
            so_file.unlink()
            print(f"Cleaned up old dynamic library: {so_file.name}")

        for pyd_file in wake_rs_dir.glob("*.pyd"):
            pyd_file.unlink()
            print(f"Cleaned up old dynamic library: {pyd_file.name}")

        build()


if __name__ == "__main__":
    build()
