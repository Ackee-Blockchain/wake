from __future__ import annotations

import inspect
import json
import math
from collections import namedtuple
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

ChainExplorer = namedtuple("ChainExplorer", ["url", "api_url"])

chain_explorer_urls: Dict[int, ChainExplorer] = {
    1: ChainExplorer("https://etherscan.io", "https://api.etherscan.io/api"),
    5: ChainExplorer(
        "https://goerli.etherscan.io", "https://api-goerli.etherscan.io/api"
    ),
    56: ChainExplorer("https://bscscan.com", "https://api.bscscan.com/api"),
    97: ChainExplorer(
        "https://testnet.bscscan.com", "https://api-testnet.bscscan.com/api"
    ),
    137: ChainExplorer("https://polygonscan.com", "https://api.polygonscan.com/api"),
    80001: ChainExplorer(
        "https://mumbai.polygonscan.com", "https://api-mumbai.polygonscan.com/api"
    ),
    43114: ChainExplorer("https://snowtrace.io/", "https://api.snowtrace.io/api"),
    43113: ChainExplorer(
        "https://testnet.snowtrace.io/", "https://api-testnet.snowtrace.io/api"
    ),
    10: ChainExplorer(
        "https://optimistic.etherscan.io/", "https://api-optimistic.etherscan.io/api"
    ),
    420: ChainExplorer(
        "https://goerli-optimism.etherscan.io/",
        "https://api-goerli-optimism.etherscan.io/api",
    ),
    100: ChainExplorer("https://gnosisscan.io/", "https://api.gnosisscan.io/api"),
    42161: ChainExplorer("https://arbiscan.io/", "https://api.arbiscan.io/api"),
    421613: ChainExplorer(
        "https://testnet.arbiscan.io/", "https://api-testnet.arbiscan.io/api"
    ),
    84531: ChainExplorer(
        "https://goerli.basescan.org/", "https://api-goerli.basescan.org/api"
    ),
    11155111: ChainExplorer(
        "https://sepolia.etherscan.io/", "https://api-sepolia.etherscan.io/api"
    ),
    1101: ChainExplorer(
        "https://zkevm.polygonscan.com/", "https://api-zkevm.polygonscan.com/api"
    ),
    1442: ChainExplorer(
        "https://testnet-zkevm.polygonscan.com/",
        "https://api-testnet-zkevm.polygonscan.com/api",
    ),
    42220: ChainExplorer(
        "https://celoscan.io/",
        "https://api.celoscan.io/api",
    ),
    44787: ChainExplorer(
        "https://alfajores.celoscan.io/",
        "https://api-alfajores.celoscan.io/api",
    ),
    1284: ChainExplorer(
        "https://moonscan.io/",
        "https://api-moonbeam.moonscan.io/api",
    ),
    1287: ChainExplorer(
        "https://moonbase.moonscan.io/",
        "https://api-moonbase.moonscan.io/api",
    ),
    250: ChainExplorer(
        "https://ftmscan.com/",
        "https://api.ftmscan.com/api",
    ),
    4002: ChainExplorer(
        "https://testnet.ftmscan.com/",
        "https://api-testnet.ftmscan.com/api",
    ),
}


@lru_cache(maxsize=1024)
def get_contract_info_from_explorer(
    addr: Address, chain_id: int
) -> Optional[Tuple[str, Dict]]:
    if chain_id not in chain_explorer_urls:
        return None

    u = urlparse(chain_explorer_urls[chain_id].url)
    config = get_config()
    api_key = config.api_keys.get(".".join(u.netloc.split(".")[:-1]), None)
    if api_key is None:
        return None

    url = (
        chain_explorer_urls[chain_id].api_url
        + f"?module=contract&action=getsourcecode&address={addr}&apikey={api_key}"
    )

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
