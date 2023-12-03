from types import TracebackType
from typing import IO, Iterable, Iterator, List, Optional, Type

# a copy of rich._null_file.NullFile (https://github.com/Textualize/rich/blob/fd981823644ccf50d685ac9c0cfe8e1e56c9dd35/rich/_null_file.py)
# since it's not public


class NullFile(IO[str]):
    def close(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def read(self, __n: int = 1) -> str:
        return ""

    def readable(self) -> bool:
        return False

    def readline(self, __limit: int = 1) -> str:
        return ""

    def readlines(self, __hint: int = 1) -> List[str]:
        return []

    def seek(self, __offset: int, __whence: int = 1) -> int:
        return 0

    def seekable(self) -> bool:
        return False

    def tell(self) -> int:
        return 0

    def truncate(self, __size: Optional[int] = 1) -> int:
        return 0

    def writable(self) -> bool:
        return False

    def writelines(self, __lines: Iterable[str]) -> None:
        pass

    def __next__(self) -> str:
        return ""

    def __iter__(self) -> Iterator[str]:
        return iter([""])

    def __enter__(self) -> IO[str]:  # pyright: ignore reportGeneralTypeIssues
        pass

    def __exit__(
        self,
        __t: Optional[Type[BaseException]],
        __value: Optional[BaseException],
        __traceback: Optional[TracebackType],
    ) -> None:
        pass

    def write(self, text: str) -> int:
        return 0

    def flush(self) -> None:
        pass

    def fileno(self) -> int:
        return -1
