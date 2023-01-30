# tab space width for indentation
TAB_WIDTH = 4

DEFAULT_IMPORTS: str = """
from dataclasses import dataclass 
from typing import List, Optional, overload, Union, Callable
from typing_extensions import Literal

from woke.testing.core import Contract, Library, Address, Account, Chain, RequestType
from woke.testing.internal import TransactionRevertedError
from woke.testing.primitive_types import *
from woke.testing.transactions import LegacyTransaction
"""

INIT_CONTENT: str = """
import woke.testing.core
from woke.utils import get_package_version

if get_package_version("woke") != "{version}":
    raise RuntimeError("Pytypes generated for a different version of woke. Please regenerate.")

woke.testing.core.errors = {errors}
woke.testing.core.events = {events}
woke.testing.core.contracts_by_fqn = {contracts_by_fqn}
woke.testing.core.contracts_by_metadata = {contracts_by_metadata}
woke.testing.core.contracts_inheritance = {contracts_inheritance}
woke.testing.core.contracts_revert_index = {contracts_revert_index}
woke.testing.core.deployment_code_index = {deployment_code_index}
"""
