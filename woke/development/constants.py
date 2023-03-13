# tab space width for indentation
TAB_WIDTH = 4

DEFAULT_IMPORTS: str = """
from __future__ import annotations

import dataclasses
from typing import List, Dict, Optional, overload, Union, Callable, Tuple
from typing_extensions import Literal

from woke.development.core import Contract, Library, Address, Account, Chain, RequestType
from woke.development.primitive_types import *
from woke.development.transactions import TransactionAbc, TransactionRevertedError
"""

INIT_CONTENT: str = """
import woke.development.core
from woke.utils import get_package_version

if get_package_version("woke") != "{version}":
    raise RuntimeError("Pytypes generated for a different version of woke. Please regenerate.")

woke.development.core.errors = {errors}
woke.development.core.events = {events}
woke.development.core.contracts_by_fqn = {contracts_by_fqn}
woke.development.core.contracts_by_metadata = {contracts_by_metadata}
woke.development.core.contracts_inheritance = {contracts_inheritance}
woke.development.core.contracts_revert_index = {contracts_revert_index}
woke.development.core.creation_code_index = {creation_code_index}
"""
