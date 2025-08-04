from rich import print

from wake.development.core import Abi, Account, Address, Eip712Domain, Wei, abi
from wake.development.globals import get_config, random
from wake.development.internal import ExternalEvent, UnknownEvent
from wake.development.primitive_types import *
from wake.development.transactions import (
    Eip1559Transaction,
    Eip2930Transaction,
    Eip7702Transaction,
    Error,
    ExternalError,
    LegacyTransaction,
    Panic,
    PanicCodeEnum,
    RevertError,
    TransactionAbc,
    UnknownRevertError,
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
    mint_erc721,
    mint_erc1155,
    read_storage_variable,
    write_storage_variable,
)

if get_config().testing.cmd == "revm":
    from wake_rs import Chain
    from wake_rs import default_chain as _default_chain

    chain = _default_chain()
else:
    from .core import Chain, chain
