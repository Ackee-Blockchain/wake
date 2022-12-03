# tab space width for indentation
TAB_WIDTH = 4

# TODO move to constants file
DEFAULT_IMPORTS: str = """
import random 
from dataclasses import dataclass 
from typing import List, NewType, Optional, overload, Union
from typing_extensions import Literal

from woke.testing.contract import Contract, Library, TransactionObject, Address, Wei, Account, ChainInterface
from woke.testing.internal import TransactionRevertedError
"""

INIT_CONTENT: str = """
import woke.testing.contract

woke.testing.contract.errors = {errors}
woke.testing.contract.events = {events}
woke.testing.contract.contracts_by_metadata = {contracts_by_metadata}
woke.testing.contract.contracts_inheritance = {contracts_inheritance}
woke.testing.contract.bytecode_index = {bytecode_index}
"""
