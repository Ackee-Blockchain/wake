# tab space width for indentation
TAB_WIDTH = 4

DEFAULT_IMPORTS: str = """
from __future__ import annotations

import dataclasses
from typing import List, Dict, Optional, overload, Union, Callable, Tuple
from typing_extensions import Literal

from wake.development.core import Contract, Library, Address, Account, Chain, RequestType
from wake.development.primitive_types import *
from wake.development.transactions import TransactionAbc, TransactionRevertedError
"""

INIT_CONTENT: str = """
import wake.development.core
from wake.utils import get_package_version

if get_package_version("eth-wake") != "{version}":
    raise RuntimeError("Pytypes generated for a different version of wake. Please regenerate.")

wake.development.core.errors = {errors}
wake.development.core.events = {events}
wake.development.core.contracts_by_fqn = {contracts_by_fqn}
wake.development.core.contracts_by_metadata = {contracts_by_metadata}
wake.development.core.contracts_inheritance = {contracts_inheritance}
wake.development.core.contracts_revert_constructor_index = {contracts_revert_constructor_index}
wake.development.core.contracts_revert_index = {contracts_revert_index}
wake.development.core.creation_code_index = {creation_code_index}
wake.development.core.user_defined_value_types_index = {user_defined_value_types_index}
"""
