# tab space width for indentation
TAB_WIDTH = 4

# TODO move to constants file
DEFAULT_IMPORTS: str = """
import random 
from dataclasses import dataclass 
from typing import List, NewType, Optional, overload, Union
from typing_extensions import Literal

from woke.testing.contract import Contract, TransactionObject, Address, Wei
"""

INIT_CONTENT: str = """
import woke.testing.contract

woke.testing.contract.errors = {errors}
woke.testing.contract.events = {events}
"""
