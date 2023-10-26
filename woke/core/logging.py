import logging
from typing import Optional, Set

_debug: bool = False
_created_logger_names: Set[str] = set()


def get_logger(name: str, override_level: Optional[int] = None) -> logging.Logger:
    logger = logging.getLogger(name)

    if override_level is not None:
        logger.setLevel(override_level)
    else:
        _created_logger_names.add(name)
        logger.setLevel(logging.DEBUG if _debug else logging.WARNING)
    return logger


def set_debug(debug: bool) -> None:
    global _debug
    _debug = debug
    for name in _created_logger_names:
        get_logger(name).setLevel(logging.DEBUG if _debug else logging.WARNING)
