import os
import shlex
import shutil
import subprocess
import zipfile

from pathlib import Path


def maturin(*args):
    subprocess.call(["maturin", *list(args)])


def build():
    # Store the original directory to restore it later
    original_dir = os.getcwd()

    # Get absolute paths before changing directory
    wake_rs_dir = Path(__file__).parent.absolute()
    build_dir = wake_rs_dir / "build"
    wheels_dir = wake_rs_dir / "target/wheels"

    build_dir.mkdir(parents=True, exist_ok=True)
    if wheels_dir.exists():
        shutil.rmtree(wheels_dir)

    # Change to wake_rs directory for maturin build
    os.chdir(wake_rs_dir)

    cargo_args = []
    if os.getenv("MATURIN_BUILD_ARGS"):
        cargo_args = shlex.split(os.getenv("MATURIN_BUILD_ARGS", ""))

    maturin("build", "-r", *cargo_args)

    # We won't use the wheel built by maturin directly since
    # we want Poetry to build it, but we need to retrieve the
    # compiled extensions from the maturin wheel.
    wheel = next(iter(wheels_dir.glob("*.whl")))
    with zipfile.ZipFile(wheel.as_posix()) as whl:
        whl.extractall(wheels_dir.as_posix())

        # Create __init__.py if it doesn't exist
        init_file = wake_rs_dir / "__init__.py"
        if not init_file.exists():
            init_file.touch()

        # Copy all .so/.pyd files to wake_rs directory
        for extension in wheels_dir.rglob("**/*.so"):
            dest = wake_rs_dir / extension.name
            shutil.copyfile(extension, dest)
            mode = os.stat(dest).st_mode
            mode |= (mode & 0o444) >> 2
            os.chmod(dest, mode)

        for extension in wheels_dir.rglob("**/*.pyd"):
            dest = wake_rs_dir / extension.name
            shutil.copyfile(extension, dest)

    shutil.rmtree(wheels_dir)

    # Restore the original directory
    os.chdir(original_dir)


if __name__ == "__main__":
    build()
