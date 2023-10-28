try:
    from importlib import metadata
except ImportError:
    # Python < 3.8
    import importlib_metadata as metadata  # pyright: ignore reportMissingImports


def get_package_version(package_name: str) -> str:
    """Get the version of the given package."""
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        raise RuntimeError(f"Package {package_name} not found.")
