from rich import print

from wake.development.core import Abi, Account, Address, Eip712Domain, Wei, abi
from wake.development.globals import random
from wake.development.internal import UnknownEvent
from wake.development.primitive_types import *
from wake.development.transactions import (
    Eip1559Transaction,
    Eip2930Transaction,
    Error,
    LegacyTransaction,
    Panic,
    PanicCodeEnum,
    TransactionAbc,
    TransactionRevertedError,
    UnknownTransactionRevertedError,
    may_revert,
    must_revert,
    on_revert,
)
from wake.development.utils import (
    burn_erc20,
    get_create2_address_from_code,
    get_create2_address_from_hash,
    get_create_address,
    get_logic_contract,
    keccak256,
    mint_erc20,
    read_storage_variable,
    write_storage_variable,
)

from .core import Chain, default_chain

chain = default_chain
