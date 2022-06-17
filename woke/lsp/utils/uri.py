from pathlib import Path
from urllib.parse import quote, unquote, urlparse


def uri_to_path(uri: str) -> Path:
    p = urlparse(unquote(uri))
    return Path(p.path)


def path_to_uri(path: Path) -> str:
    return "file://" + quote(str(path.resolve()))
