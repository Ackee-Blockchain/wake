from __future__ import annotations

import inspect
import json
import math
from functools import lru_cache
from typing import Callable, Dict, Iterable, List, Optional, Tuple, TypeVar, Union
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from Crypto.Hash import keccak
from eth_utils.abi import function_abi_to_4byte_selector

from ..utils import get_package_version
from .core import Account, Address
from .globals import get_config

chain_explorer_urls = {
    1: "https://etherscan.io",
    5: "https://goerli.etherscan.io",
    56: "https://bscscan.com",
    97: "https://testnet.bscscan.com",
    137: "https://polygonscan.com",
    80001: "https://mumbai.polygonscan.com",
    43114: "https://snowtrace.io/",
    43113: "https://testnet.snowtrace.io/",
    10: "https://optimistic.etherscan.io/",
    420: "https://goerli-optimism.etherscan.io/",
    100: "https://gnosisscan.io/",
    42161: "https://arbiscan.io",
    421613: "https://testnet.arbiscan.io/",
}


@lru_cache(maxsize=1024)
def get_contract_info_from_explorer(
    addr: Address, chain_id: int
) -> Optional[Tuple[str, Dict]]:
    if chain_id not in chain_explorer_urls:
        return None

    u = urlparse(chain_explorer_urls[chain_id])
    config = get_config()
    api_key = config.api_keys.get(".".join(u.netloc.split(".")[:-1]), None)
    if api_key is None:
        return None

    url = f"{u.scheme}://api.{u.netloc}/api?module=contract&action=getsourcecode&address={addr}&apikey={api_key}"

    req = Request(
        url,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"woke/{get_package_version('woke')}",
        },
    )

    try:
        with urlopen(req) as response:
            ret = json.loads(response.read().decode("utf-8"))
    except URLError as e:
        return None

    if ret["status"] != "1":
        return None

    data = ret["result"][0]
    if data["ContractName"] == "":
        return None

    abi = {}
    # TODO library ABI is different and has to be fixed to compute the correct selector
    # however, it is not possible to detect if a contract is a library or not without parsing the source code
    for abi_item in json.loads(data["ABI"]):
        if abi_item["type"] in {"constructor", "fallback", "receive"}:
            abi[abi_item["type"]] = abi_item
        elif abi_item["type"] == "function":
            abi[function_abi_to_4byte_selector(abi_item)] = abi_item

    return data["ContractName"], abi


def format_int(x: int) -> str:
    if abs(x) < 10**5:
        return f"{x:_}"
    no_of_digits = int(math.log10(abs(x))) + 1
    if x % 10 ** (no_of_digits - 3) == 0:
        return f"{x:.2e}"
    return f"{x:.2E} ({x:_})"


def exists(a) -> bool:
    if a is None:
        return False
    if len(a) >= 0:
        return True
    return bool(a)


T = TypeVar("T")


def partition(
    seq: Iterable[T], predicate: Callable[[T], bool]
) -> Tuple[List[T], List[T]]:
    p = []
    not_p = []
    for el in seq:
        if predicate(el):
            p.append(el)
        else:
            not_p.append(el)
    return p, not_p


def keccak256(b: bytes) -> bytes:
    h = keccak.new(data=b, digest_bits=256)
    return h.digest()


def get_current_fn_name(back_count=1) -> str:
    frame = inspect.currentframe()
    assert frame is not None
    for _ in range(back_count):
        frame = frame.f_back
        assert frame is not None
    return frame.f_code.co_name


def negate(fn):
    def inner(*args, **kwargs) -> bool:
        return not fn(*args, **kwargs)

    return inner


def get_create_address(deployer: Union[Account, Address, str], nonce: int) -> Address:
    if isinstance(deployer, Account):
        deployer = deployer.address
    deployer_bytes = bytes.fromhex(str(deployer)[2:])

    # see https://ethereum.org/en/developers/docs/data-structures-and-encoding/rlp
    if nonce < 0:
        raise ValueError("Nonce must be positive")
    elif nonce == 0:
        data = b"\xd6\x94" + deployer_bytes + b"\x80"
    elif nonce <= 0x7F:
        data = b"\xd6\x94" + deployer_bytes + bytes([nonce])
    elif nonce <= 0xFF:
        data = b"\xd7\x94" + deployer_bytes + b"\x81" + bytes([nonce])
    elif nonce <= 0xFFFF:
        data = b"\xd8\x94" + deployer_bytes + b"\x82" + nonce.to_bytes(2, "big")
    elif nonce <= 0xFFFFFF:
        data = b"\xd9\x94" + deployer_bytes + b"\x83" + nonce.to_bytes(3, "big")
    elif nonce <= 0xFFFFFFFF:
        data = b"\xda\x94" + deployer_bytes + b"\x84" + nonce.to_bytes(4, "big")
    else:
        raise ValueError("Nonce too large")

    return Address("0x" + keccak256(data)[-20:].hex())


def get_create2_address_from_hash(
    deployer: Union[Account, Address, str], salt: bytes, creation_code_hash: bytes
) -> Address:
    if isinstance(deployer, Account):
        deployer = deployer.address
    deployer_bytes = bytes.fromhex(str(deployer)[2:])

    return Address(
        "0x"
        + keccak256(b"\xff" + deployer_bytes + salt + creation_code_hash)[-20:].hex()
    )


def get_create2_address_from_code(
    deployer: Union[Account, Address, str], salt: bytes, creation_code: bytes
) -> Address:
    return get_create2_address_from_hash(deployer, salt, keccak256(creation_code))
