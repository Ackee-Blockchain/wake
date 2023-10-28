import os
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from urllib.request import pathname2url, url2pathname


def uri_to_path(uri: str) -> Path:
    path = urlparse(unquote(uri)).path
    path = url2pathname(path)
    return Path(path)


def path_to_uri(path: Path) -> str:
    if os.name == "nt":
        return "file:" + pathname2url(str(path.resolve()))
    else:
        return "file://" + pathname2url(str(path.resolve()))
