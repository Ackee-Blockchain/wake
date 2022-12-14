# tab space width for indentation
TAB_WIDTH = 4

# TODO move to constants file
DEFAULT_IMPORTS: str = """
import random 
from dataclasses import dataclass 
from typing import List, NewType, Optional, overload, Union
from typing_extensions import Literal

from woke.testing.core import Contract, Library, Address, Wei, Account, ChainInterface
from woke.testing.internal import TransactionRevertedError
from woke.testing.transactions import LegacyTransaction
"""

INIT_CONTENT: str = """
import woke.testing.core

woke.testing.core.errors = {errors}
woke.testing.core.events = {events}
woke.testing.core.contracts_by_metadata = {contracts_by_metadata}
woke.testing.core.contracts_inheritance = {contracts_inheritance}
woke.testing.core.contracts_revert_index = {contracts_revert_index}
woke.testing.core.bytecode_index = {bytecode_index}
"""
