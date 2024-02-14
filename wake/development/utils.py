from __future__ import annotations

import asyncio
import functools
import importlib
import inspect
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from json import JSONDecodeError
from pathlib import PurePosixPath
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from Crypto.Hash import keccak
from eth_utils.abi import function_abi_to_4byte_selector
from pydantic import ValidationError, parse_raw_as

from ..compiler import SolcOutputSelectionEnum, SolidityCompiler
from ..compiler.solc_frontend import (
    SolcInput,
    SolcInputSource,
    SolcOutputErrorSeverityEnum,
    SolcOutputStorageLayout,
    SolcOutputStorageLayoutType,
)
from ..config import WakeConfig
from ..core.solidity_version import SolidityVersion
from ..svm import SolcVersionManager
from ..utils import get_package_version
from .core import (
    Abi,
    Account,
    Address,
    Contract,
    abi,
    get_contracts_by_fqn,
    get_fqn_from_address,
    get_user_defined_value_types_index,
)
from .globals import get_config
from .primitive_types import uint256

# pyright: reportGeneralTypeIssues=false, reportOptionalIterable=false, reportOptionalSubscript=false, reportOptionalMemberAccess=false


@dataclass
class ChainExplorer:
    url: str
    api_url: str

    @property
    def config_key(self) -> str:
        return ".".join(urlparse(self.url).netloc.split(".")[:-1])


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
    17000: ChainExplorer(
        "https://holesky.etherscan.io/",
        "https://api-holesky.etherscan.io/api",
    ),
}


@lru_cache(maxsize=1024)
def get_contract_info_from_explorer(
    addr: Address, chain_id: int
) -> Optional[Tuple[str, Dict]]:
    if chain_id not in chain_explorer_urls:
        return None

    config = get_config()
    api_key = config.api_keys.get(chain_explorer_urls[chain_id].config_key, None)
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
            "User-Agent": f"wake/{get_package_version('eth-wake')}",
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
        elif abi_item["type"] == "error":
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


def get_logic_contract(contract: Account) -> Account:
    # keccak256("eip1967.proxy.implementation") - 1
    impl_addr = Abi.decode(
        ["address"],
        contract.chain.chain_interface.get_storage_at(
            str(contract.address),
            0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC,
        ),
    )[0]
    if impl_addr != Address.ZERO:
        return Account(impl_addr, chain=contract.chain)

    # keccak256("org.zeppelinos.proxy.implementation")
    impl_addr = Abi.decode(
        ["address"],
        contract.chain.chain_interface.get_storage_at(
            str(contract.address),
            0x7050C9E0F4CA769C69BD3A8EF740BC37934F8E2C036E5A723FD8EE048ED3F8C3,
        ),
    )[0]
    if impl_addr != Address.ZERO:
        return Account(impl_addr, chain=contract.chain)

    # keccak256("eip1967.proxy.beacon") - 1
    beacon_addr = Abi.decode(
        ["address"],
        contract.chain.chain_interface.get_storage_at(
            str(contract.address),
            0xA3F0AD74E5423AEBFD80D3EF4346578335A9A72AEAEE59FF6CB3582B35133D50,
        ),
    )[0]

    if beacon_addr != Address.ZERO:
        impl_addr_raw = Account(beacon_addr, chain=contract.chain).call(
            data=Abi.encode_with_signature("implementation()", [], [])
        )
        return Account(Abi.decode(["address"], impl_addr_raw)[0], chain=contract.chain)

    return contract


def read_storage_variable(
    contract: Account,
    name: str,
    *,
    keys: Optional[Sequence] = None,
    storage_layout_contract: Optional[Union[Account, Type[Contract]]] = None,
):
    def _get_storage_value(
        slot: int,
        offset: int,
        keys: Sequence,
        type_name: str,
        types: Dict[str, SolcOutputStorageLayoutType],
    ):
        type_info = types[type_name]
        slot_data = contract.chain.chain_interface.get_storage_at(
            str(contract.address), slot
        )
        data = slot_data[
            -offset - type_info.number_of_bytes : (-offset if offset != 0 else None)
        ]

        if type_name in ["t_bytes_storage", "t_string_storage"]:
            data = data.rjust(32, b"\x00")
            l = data[-1]
            if l % 2 == 0:
                # tight packing of length < 32 bytes
                raw = data[: l // 2]
            else:
                # data are stored at data_slot = keccak256(slot)
                length = int.from_bytes(slot_data, "big") // 2
                start_slot = int.from_bytes(keccak256(slot.to_bytes(32, "big")), "big")
                raw = bytearray()

                while length >= 32:
                    raw += contract.chain.chain_interface.get_storage_at(
                        str(contract.address), start_slot
                    )
                    start_slot += 1
                    length -= 32

                if length > 0:
                    raw += contract.chain.chain_interface.get_storage_at(
                        str(contract.address), start_slot
                    )[:length]

            if type_name == "t_string_storage":
                return raw.decode("utf-8")
            return raw
        elif type_name.startswith("t_struct"):
            if len(keys) > 0:
                if not isinstance(keys[0], str):
                    raise ValueError(
                        f"{type_info.label} requires string member name to be specified as key"
                    )
                try:
                    member = next(m for m in type_info.members if m.label == keys[0])
                except StopIteration:
                    raise ValueError(
                        f"{type_info.label} does not have member {keys[0]}"
                    )
                # structs always start a new slot
                return _get_storage_value(
                    slot + member.slot, member.offset, keys[1:], member.type, types
                )
            else:
                return {
                    member.label: _get_storage_value(
                        slot + member.slot, member.offset, keys, member.type, types
                    )
                    for member in type_info.members
                }
        elif type_name.startswith("t_array"):
            base_type = types[type_info.base]
            items_per_slot = 32 // base_type.number_of_bytes

            # arrays always start a new slot
            if type_info.encoding == "dynamic_array":
                slot = int.from_bytes(keccak256(slot.to_bytes(32, "big")), "big")
                length = Abi.decode(["uint256"], slot_data)[0]
            else:
                length = int(type_info.label.split("[")[-1][:-1])

            if len(keys) == 0:
                # reading whole array
                if items_per_slot > 0:
                    return [
                        _get_storage_value(
                            slot + i // items_per_slot,
                            (i % items_per_slot) * base_type.number_of_bytes,
                            keys[1:],
                            type_info.base,
                            types,
                        )
                        for i in range(length)
                    ]
                else:
                    return [
                        _get_storage_value(
                            slot + (base_type.number_of_bytes * i) // 32,
                            0,
                            keys[1:],
                            type_info.base,
                            types,
                        )
                        for i in range(length)
                    ]
            else:
                if not isinstance(keys[0], int):
                    raise ValueError(
                        f"{type_info.label} requires integer index to be specified as key"
                    )
                if keys[0] >= length:
                    raise ValueError(
                        f"index {keys[0]} out of bounds for {type_info.label} with length {length}"
                    )

                if items_per_slot > 0:
                    return _get_storage_value(
                        slot + keys[0] // items_per_slot,
                        (keys[0] % items_per_slot) * base_type.number_of_bytes,
                        keys[1:],
                        type_info.base,
                        types,
                    )
                else:
                    # assuming base_type.number_of_bytes is always a multiple of 32
                    return _get_storage_value(
                        slot + (base_type.number_of_bytes * keys[0]) // 32,
                        0,
                        keys[1:],
                        type_info.base,
                        types,
                    )
        elif type_name.startswith("t_bytes"):
            # bytes1 to bytes32
            data = data.ljust(32, b"\x00")
        elif type_name.startswith("t_mapping"):
            if len(keys) == 0:
                raise ValueError(
                    f"{type_info.label} requires key of type {types[type_info.key].label} to be specified as key"
                )

            key_type_name = type_info.key
            if key_type_name.startswith("t_userDefinedValueType"):
                key_type_name = get_user_defined_value_types_index()[key_type_name]

            if key_type_name.startswith("t_string"):
                if not isinstance(keys[0], str):
                    raise ValueError(
                        f"{type_info.label} requires key to be string but got {keys[0]} of type {type(keys[0])}"
                    )
                encoded_key = keys[0].encode("utf-8")
            elif (
                key_type_name.startswith("t_bytes")
                and types[key_type_name].encoding == "bytes"
            ):
                # do not handle bytes1 to bytes32 in this case
                if not isinstance(keys[0], bytes):
                    raise ValueError(
                        f"{type_info.label} requires key to be bytes but got {keys[0]} of type {type(keys[0])}"
                    )
                encoded_key = keys[0]
            elif key_type_name.startswith("t_contract"):
                encoded_key = Abi.encode(["address"], [keys[0]])
            elif key_type_name.startswith("t_enum"):
                encoded_key = Abi.encode(["uint8"], [keys[0]])
            else:
                encoded_key = Abi.encode([key_type_name[2:]], [keys[0]])

            return _get_storage_value(
                int.from_bytes(
                    keccak256(encoded_key + slot.to_bytes(32, "big")), "big"
                ),
                0,
                keys[1:],
                type_info.value,
                types,
            )
        else:
            data = data.rjust(32, b"\x00")

        return Abi.decode([type_name[2:]], data)[0]

    if storage_layout_contract is None:
        storage_layout = _get_storage_layout(get_logic_contract(contract))
    else:
        storage_layout = _get_storage_layout(storage_layout_contract)

    if keys is None:
        keys = []

    try:
        storage = next(i for i in storage_layout.storage if i.label == name)
    except StopIteration:
        raise ValueError(f"Storage variable {name} not found")

    return _get_storage_value(
        storage.slot, storage.offset, keys, storage.type, storage_layout.types
    )


def write_storage_variable(
    contract: Account,
    name: str,
    value: Any,
    *,
    keys: Optional[Sequence] = None,
    storage_layout_contract: Optional[Union[Account, Type[Contract]]] = None,
):
    def _set_storage_value(
        slot: int,
        offset: int,
        keys: Sequence,
        type_name: str,
        types: Dict[str, SolcOutputStorageLayoutType],
    ):
        nonlocal value

        type_info = types[type_name]

        if type_name in ["t_bytes_storage", "t_string_storage"]:
            if type_name == "t_string_storage":
                if not isinstance(value, str):
                    raise ValueError(
                        f"{type_info.label} requires string value but got {value} of type {type(value)}"
                    )
                value = value.encode("utf-8")
            else:
                if not isinstance(value, bytes):
                    raise ValueError(
                        f"{type_info.label} requires bytes value but got {value} of type {type(value)}"
                    )

            if len(value) >= 32:
                encoded_length = Abi.encode(["uint256"], [len(value) * 2 + 1])
                contract.chain.chain_interface.set_storage_at(
                    str(contract.address), slot, encoded_length
                )

                start_slot = int.from_bytes(keccak256(slot.to_bytes(32, "big")), "big")
                length = len(value)

                while length >= 32:
                    contract.chain.chain_interface.set_storage_at(
                        str(contract.address), start_slot, value[:32]
                    )
                    start_slot += 1
                    value = value[32:]
                    length -= 32

                if length > 0:
                    original_data = contract.chain.chain_interface.get_storage_at(
                        str(contract.address), start_slot
                    )
                    contract.chain.chain_interface.set_storage_at(
                        str(contract.address),
                        start_slot,
                        value + original_data[length:],
                    )
            else:
                encoded_data = Abi.encode(["uint8"], [len(value) * 2])
                encoded_data = value + encoded_data[len(value) :]
                contract.chain.chain_interface.set_storage_at(
                    str(contract.address), slot, encoded_data
                )
        elif type_name.startswith("t_struct"):
            if len(keys) > 0:
                if not isinstance(keys[0], str):
                    raise ValueError(
                        f"{type_info.label} requires string member name to be specified as key"
                    )
                try:
                    member = next(m for m in type_info.members if m.label == keys[0])
                except StopIteration:
                    raise ValueError(
                        f"{type_info.label} does not have member {keys[0]}"
                    )
                # structs always start a new slot
                _set_storage_value(
                    slot + member.slot, member.offset, keys[1:], member.type, types
                )
            else:
                if not isinstance(value, dict):
                    raise ValueError(
                        f"{type_info.label} requires dict value but got {value} of type {type(value)}"
                    )
                if len(value) != len(type_info.members):
                    raise ValueError(
                        f"{type_info.label} requires list of length {len(type_info.members)} but got {value} of length {len(value)}"
                    )

                original_value = value
                for member in type_info.members:
                    if member.label not in original_value:
                        raise ValueError(
                            f"{type_info.label} requires member {member.label} to be specified"
                        )
                    value = original_value[member.label]
                    _set_storage_value(
                        slot + member.slot,
                        member.offset,
                        keys,
                        member.type,
                        types,
                    )
        elif type_name.startswith("t_array"):
            if len(keys) > 0 and not isinstance(keys[0], int):
                raise ValueError(
                    f"{type_info.label} requires integer index to be specified as key"
                )
            elif len(keys) == 0 and not isinstance(value, (list, tuple)):
                raise ValueError(
                    f"{type_info.label} requires list value but got {value} of type {type(value)}"
                )

            base_type = types[type_info.base]
            items_per_slot = 32 // base_type.number_of_bytes

            # arrays always start a new slot
            if type_info.encoding == "dynamic_array":
                slot_data = contract.chain.chain_interface.get_storage_at(
                    str(contract.address), slot
                )
                length_slot = slot
                slot = int.from_bytes(keccak256(slot.to_bytes(32, "big")), "big")
                length = Abi.decode(["uint256"], slot_data)[0]
            else:
                length_slot = -1  # to satisfy linter
                length = int(type_info.label.split("[")[-1][:-1])
                if len(value) != length:
                    raise ValueError(
                        f"{type_info.label} requires list of length {length} but got {value} of length {len(value)}"
                    )

            if len(keys) == 0:
                # setting whole array
                if type_info.encoding == "dynamic_array":
                    encoded_length = Abi.encode(["uint256"], [len(value)])
                    contract.chain.chain_interface.set_storage_at(
                        str(contract.address), length_slot, encoded_length
                    )
                for i, v in enumerate(value):
                    value = v
                    if items_per_slot > 0:
                        _set_storage_value(
                            slot + i // items_per_slot,
                            (i % items_per_slot) * base_type.number_of_bytes,
                            keys[1:],
                            type_info.base,
                            types,
                        )
                    else:
                        # assuming base_type.number_of_bytes is always a multiple of 32
                        _set_storage_value(
                            slot + (base_type.number_of_bytes * i) // 32,
                            0,
                            keys[1:],
                            type_info.base,
                            types,
                        )
            else:
                if keys[0] >= length:
                    raise ValueError(
                        f"index {keys[0]} out of bounds for {type_info.label} with length {length}"
                    )

                if items_per_slot > 0:
                    _set_storage_value(
                        slot + keys[0] // items_per_slot,
                        (keys[0] % items_per_slot) * base_type.number_of_bytes,
                        keys[1:],
                        type_info.base,
                        types,
                    )
                else:
                    # assuming base_type.number_of_bytes is always a multiple of 32
                    _set_storage_value(
                        slot + (base_type.number_of_bytes * keys[0]) // 32,
                        0,
                        keys[1:],
                        type_info.base,
                        types,
                    )
        elif type_name.startswith("t_mapping"):
            if len(keys) == 0:
                raise ValueError(
                    f"{type_info.label} requires key of type {types[type_info.key].label} to be specified as key"
                )

            key_type_name = type_info.key
            if key_type_name.startswith("t_userDefinedValueType"):
                key_type_name = get_user_defined_value_types_index()[key_type_name]

            if key_type_name.startswith("t_string"):
                if not isinstance(keys[0], str):
                    raise ValueError(
                        f"{type_info.label} requires key to be string but got {keys[0]} of type {type(keys[0])}"
                    )
                encoded_key = keys[0].encode("utf-8")
            elif (
                key_type_name.startswith("t_bytes")
                and types[key_type_name].encoding == "bytes"
            ):
                # do not handle bytes1 to bytes32 in this case
                if not isinstance(keys[0], bytes):
                    raise ValueError(
                        f"{type_info.label} requires key to be bytes but got {keys[0]} of type {type(keys[0])}"
                    )
                encoded_key = keys[0]
            elif key_type_name.startswith("t_contract"):
                encoded_key = Abi.encode(["address"], [keys[0]])
            elif key_type_name.startswith("t_enum"):
                encoded_key = Abi.encode(["uint8"], [keys[0]])
            else:
                encoded_key = Abi.encode([key_type_name[2:]], [keys[0]])

            _set_storage_value(
                int.from_bytes(
                    keccak256(encoded_key + slot.to_bytes(32, "big")), "big"
                ),
                0,
                keys[1:],
                type_info.value,
                types,
            )
        else:
            original_data = bytearray(
                contract.chain.chain_interface.get_storage_at(
                    str(contract.address), slot
                )
            )
            encoded_value = Abi.encode_packed([type_name[2:]], [value])
            original_data[
                -offset - type_info.number_of_bytes : (-offset if offset != 0 else None)
            ] = encoded_value
            contract.chain.chain_interface.set_storage_at(
                str(contract.address), slot, original_data
            )

    if storage_layout_contract is None:
        storage_layout = _get_storage_layout(get_logic_contract(contract))
    else:
        storage_layout = _get_storage_layout(storage_layout_contract)

    if keys is None:
        keys = []

    try:
        storage = next(i for i in storage_layout.storage if i.label == name)
    except StopIteration:
        raise ValueError(f"Storage variable {name} not found")

    _set_storage_value(
        storage.slot, storage.offset, keys, storage.type, storage_layout.types
    )


def mint_erc20(
    contract: Account,
    to: Union[Account, Address],
    amount: int,
    *,
    balance_slot: Optional[int] = None,
    total_supply_slot: Optional[int] = None,
) -> None:
    _update_erc20_balance(contract, to, amount, balance_slot, total_supply_slot)


def burn_erc20(
    contract: Account,
    from_: Union[Account, Address],
    amount: int,
    *,
    balance_slot: Optional[int] = None,
    total_supply_slot: Optional[int] = None,
) -> None:
    _update_erc20_balance(contract, from_, -amount, balance_slot, total_supply_slot)


def _try_change_erc20_balance(
    erc20: Account, balance_acc: Account, acc: Account, slot: int, amount: int
):
    call_acc = erc20.chain.default_call_account
    if call_acc is None and len(erc20.chain.accounts) > 0:
        call_acc = erc20.chain.accounts[0]

    try:
        balance_before = abi.decode(
            erc20.call(
                data=abi.encode_with_signature("balanceOf(address)", acc),
                from_=call_acc,
            ),
            [uint256],
        )
    except Exception:
        raise ValueError("Balance change failed")
    if balance_before + amount < 0:
        raise ValueError("Balance underflow")
    if balance_before + amount > 2**256 - 1:
        raise ValueError("Balance overflow")

    data_before = erc20.chain.chain_interface.get_storage_at(
        str(balance_acc.address), slot
    )
    erc20.chain.chain_interface.set_storage_at(
        str(balance_acc.address),
        slot,
        (int.from_bytes(data_before, byteorder="big") + amount).to_bytes(
            32, byteorder="big"
        ),
    )

    try:
        balance_after = abi.decode(
            erc20.call(
                data=abi.encode_with_signature("balanceOf(address)", acc),
                from_=call_acc,
            ),
            [uint256],
        )
        assert balance_after == balance_before + amount
    except Exception:
        erc20.chain.chain_interface.set_storage_at(
            str(balance_acc.address), slot, data_before
        )
        raise ValueError("Balance change failed")


def _try_change_erc20_supply(
    erc20: Account, supply_acc: Account, slot: int, amount: int
):
    call_acc = erc20.chain.default_call_account
    if call_acc is None and len(erc20.chain.accounts) > 0:
        call_acc = erc20.chain.accounts[0]

    try:
        supply_before = abi.decode(
            erc20.call(
                data=abi.encode_with_signature("totalSupply()"),
                from_=call_acc,
            ),
            [uint256],
        )
    except Exception:
        raise ValueError("Total supply change failed")
    if supply_before + amount < 0:
        raise ValueError("Total supply underflow")
    if supply_before + amount > 2**256 - 1:
        raise ValueError("Total supply overflow")

    if slot == -1:
        supply_acc.balance += amount

        try:
            supply_after = abi.decode(
                erc20.call(
                    data=abi.encode_with_signature("totalSupply()"),
                    from_=call_acc,
                ),
                [uint256],
            )
            assert supply_after == supply_before + amount
            return
        except Exception:
            supply_acc.balance -= amount
            raise ValueError("Total supply change failed")

    data_before = erc20.chain.chain_interface.get_storage_at(
        str(supply_acc.address), slot
    )
    erc20.chain.chain_interface.set_storage_at(
        str(supply_acc.address),
        slot,
        (int.from_bytes(data_before, byteorder="big") + amount).to_bytes(
            32, byteorder="big"
        ),
    )

    try:
        supply_after = abi.decode(
            erc20.call(
                data=abi.encode_with_signature("totalSupply()"),
                from_=call_acc,
            ),
            [uint256],
        )
        assert supply_after == supply_before + amount
    except Exception:
        erc20.chain.chain_interface.set_storage_at(
            str(supply_acc.address), slot, data_before
        )
        raise ValueError("Total supply change failed")


@lru_cache(maxsize=1024)
def _detect_erc20_balance_slot(
    erc20: Account, account: Account
) -> Optional[Tuple[Account, int]]:
    access_list_acc = erc20.chain.default_access_list_account
    if access_list_acc is None and len(erc20.chain.accounts) > 0:
        access_list_acc = erc20.chain.accounts[0]
    call_acc = erc20.chain.default_call_account
    if call_acc is None and len(erc20.chain.accounts) > 0:
        call_acc = erc20.chain.accounts[0]

    access_list, _ = erc20.access_list(
        data=abi.encode_with_signature("balanceOf(address)", account),
        from_=access_list_acc,
    )

    impl = get_logic_contract(erc20)

    try:
        balance_before = abi.decode(
            erc20.call(
                data=abi.encode_with_signature("balanceOf(address)", account),
                from_=call_acc,
            ),
            [uint256],
        )
    except Exception:
        return None

    # start with the storage slots of the logic contract since they are more likely to be used
    for addr in sorted(access_list.keys(), key=lambda a: 1 if a == impl.address else 0):
        for slot in access_list[addr]:
            data_before = erc20.chain.chain_interface.get_storage_at(str(addr), slot)

            try:
                erc20.chain.chain_interface.set_storage_at(
                    str(addr),
                    slot,
                    (int.from_bytes(data_before, byteorder="big") + 1).to_bytes(
                        32, byteorder="big"
                    ),
                )
            except Exception:
                continue

            try:
                balance_after = abi.decode(
                    erc20.call(
                        data=abi.encode_with_signature("balanceOf(address)", account),
                        from_=call_acc,
                    ),
                    [uint256],
                )
                assert balance_after == balance_before + 1
                return Account(addr, chain=erc20.chain), slot
            except Exception:
                continue
            finally:
                # revert changes
                erc20.chain.chain_interface.set_storage_at(str(addr), slot, data_before)

    return None


@lru_cache(maxsize=1024)
def _detect_erc20_total_supply_slot(erc20: Account) -> Optional[Tuple[Account, int]]:
    access_list_acc = erc20.chain.default_access_list_account
    if access_list_acc is None and len(erc20.chain.accounts) > 0:
        access_list_acc = erc20.chain.accounts[0]
    call_acc = erc20.chain.default_call_account
    if call_acc is None and len(erc20.chain.accounts) > 0:
        call_acc = erc20.chain.accounts[0]

    access_list, _ = erc20.access_list(
        data=abi.encode_with_signature("totalSupply()"),
        from_=access_list_acc,
    )

    impl = get_logic_contract(erc20)

    try:
        total_supply_before = abi.decode(
            erc20.call(
                data=abi.encode_with_signature("totalSupply()"),
                from_=call_acc,
            ),
            [uint256],
        )
    except Exception:
        return None

    erc20.balance += 1
    try:
        total_supply_after = abi.decode(
            erc20.call(
                data=abi.encode_with_signature("totalSupply()"),
                from_=call_acc,
            ),
            [uint256],
        )
        assert total_supply_after == total_supply_before + 1
        return erc20, -1
    except Exception:
        pass
    finally:
        erc20.balance -= 1

    # start with the storage slots of the logic contract since they are more likely to be used
    for addr in sorted(access_list.keys(), key=lambda a: 1 if a == impl.address else 0):
        for slot in access_list[addr]:
            data_before = erc20.chain.chain_interface.get_storage_at(str(addr), slot)

            try:
                erc20.chain.chain_interface.set_storage_at(
                    str(addr),
                    slot,
                    (int.from_bytes(data_before, byteorder="big") + 1).to_bytes(
                        32, byteorder="big"
                    ),
                )
            except Exception:
                continue

            try:
                total_supply_after = abi.decode(
                    erc20.call(
                        data=abi.encode_with_signature("totalSupply()"),
                        from_=call_acc,
                    ),
                    [uint256],
                )
                assert total_supply_after == total_supply_before + 1
                return Account(addr, chain=erc20.chain), slot
            except Exception:
                continue
            finally:
                # revert changes
                erc20.chain.chain_interface.set_storage_at(str(addr), slot, data_before)

    return None


def _update_erc20_balance(
    contract: Account,
    account: Account,
    amount: int,
    balance_slot: Optional[int],
    total_supply_slot: Optional[int],
) -> None:
    balance_contract = contract
    supply_contract = contract

    if balance_slot is None:
        balance_data = _detect_erc20_balance_slot(contract, account)
        if balance_data is None:
            raise ValueError("Could not detect ERC20 balance slot")
        balance_contract, balance_slot = balance_data

    if total_supply_slot is None:
        supply_data = _detect_erc20_total_supply_slot(contract)
        if supply_data is None:
            raise ValueError("Could not detect ERC20 total supply slot")
        supply_contract, total_supply_slot = supply_data

    _try_change_erc20_balance(contract, balance_contract, account, balance_slot, amount)
    _try_change_erc20_supply(contract, supply_contract, total_supply_slot, amount)


def _get_storage_layout(
    contract: Union[Account, Type[Contract]]
) -> SolcOutputStorageLayout:
    if inspect.isclass(contract):
        if not hasattr(contract, "_storage_layout"):
            raise ValueError("Could not get storage layout from contract source code")

        return SolcOutputStorageLayout.parse_obj(contract._storage_layout)

    fqn = get_fqn_from_address(contract.address, "latest", contract.chain)
    if fqn is None:
        if contract.chain._forked_chain_id is None:
            raise ValueError("Contract not found")

        if contract.chain._forked_chain_id not in chain_explorer_urls:
            raise ValueError(
                f"Chain explorer URL not found for chain ID {contract.chain._forked_chain_id}"
            )

        try:
            return _get_storage_layout_from_explorer(
                str(contract.address), contract.chain.chain_id
            )
        except Exception as e:
            raise ValueError("Could not get storage layout from chain explorer") from e
    else:
        contracts_by_fqn = get_contracts_by_fqn()
        module_name, attrs = contracts_by_fqn[fqn]
        obj = getattr(importlib.import_module(module_name), attrs[0])
        for attr in attrs[1:]:
            obj = getattr(obj, attr)

        if not hasattr(obj, "_storage_layout"):
            raise ValueError("Could not get storage layout from contract source code")

        return SolcOutputStorageLayout.parse_obj(obj._storage_layout)


@functools.lru_cache(maxsize=64)
def _get_storage_layout_from_explorer(
    addr: str, chain_id: int
) -> SolcOutputStorageLayout:
    loop = asyncio.get_event_loop()

    u = urlparse(chain_explorer_urls[chain_id].url)
    config = get_config()
    api_key = config.api_keys.get(".".join(u.netloc.split(".")[:-1]), None)
    if api_key is None:
        raise ValueError(f"Contract not found and API key for {u.netloc} not provided")

    url = (
        chain_explorer_urls[chain_id].api_url
        + f"?module=contract&action=getsourcecode&address={addr}&apikey={api_key}"
    )
    req = Request(
        url,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"wake/{get_package_version('eth-wake')}",
        },
    )

    with urlopen(req) as response:
        parsed = json.loads(response.read().decode("utf-8"))

    if parsed["status"] != "1":
        raise ValueError(f"Request to {u.netloc} failed: {parsed['result']}")

    if "Proxy" in parsed["result"][0] and parsed["result"][0]["Proxy"] == "1":
        return _get_storage_layout_from_explorer(
            parsed["result"][0]["Implementation"], chain_id
        )

    version: str = parsed["result"][0]["CompilerVersion"]
    if version.startswith("vyper"):
        raise ValueError("Cannot set balance of Vyper contract")

    if version.startswith("v"):
        version = version[1:]
    parsed_version = SolidityVersion.fromstring(version)

    if parsed_version < SolidityVersion(0, 5, 13):
        # storageLayout is only available in 0.5.13 and above
        raise ValueError(f"Solidity version {parsed_version} too low, must be >=0.5.13")

    optimizations = bool(parsed["result"][0]["OptimizationUsed"])
    runs = parsed["result"][0]["Runs"]

    config_dict = {
        "compiler": {
            "solc": {
                "target_version": str(parsed_version),
                "optimizer": {
                    "enabled": optimizations,
                    "runs": runs,
                },
            }
        }
    }

    svm = SolcVersionManager(config)
    if not svm.installed(parsed_version):
        loop.run_until_complete(svm.install(parsed_version))

    code = parsed["result"][0]["SourceCode"]
    try:
        standard_input: SolcInput = SolcInput.parse_raw(code[1:-1])
        if any(
            PurePosixPath(filename).is_absolute()
            for filename in standard_input.sources.keys()
        ):
            raise ValueError("Absolute paths not allowed")
        if (
            standard_input.settings is not None
            and standard_input.settings.remappings is not None
        ):
            config_dict["compiler"]["solc"][
                "remappings"
            ] = standard_input.settings.remappings

        if any(source.urls is not None for source in standard_input.sources.values()):
            raise NotImplementedError("Compilation from URLs not supported")

        sources = {
            config.project_root_path / path: source.content
            for path, source in standard_input.sources.items()
        }
    except ValidationError:
        try:
            s = parse_raw_as(Dict[str, SolcInputSource], code)
            if any(PurePosixPath(filename).is_absolute() for filename in s.keys()):
                raise ValueError("Absolute paths not allowed")

            if any(source.urls is not None for source in s.values()):
                raise NotImplementedError("Compilation from URLs not supported")

            sources = {
                config.project_root_path / path: source.content
                for path, source in s.items()
            }
        except (ValidationError, JSONDecodeError):
            sources = {config.project_root_path / "tmp.sol": code}

    compilation_config = WakeConfig.fromdict(
        config_dict,
        project_root_path=config.project_root_path,
    )
    compiler = SolidityCompiler(compilation_config)

    graph, _ = compiler.build_graph(
        sources.keys(),
        {k: v.encode("utf-8") for k, v in sources.items()},
        True,  # pyright: ignore reportGeneralTypeIssues
    )
    compilation_units = compiler.build_compilation_units_maximize(graph)
    compilation_units = compiler.merge_compilation_units(compilation_units, graph)
    if len(compilation_units) != 1:
        raise ValueError("More than one compilation unit")
    solc_output = loop.run_until_complete(
        compiler.compile_unit_raw(
            compilation_units[0],
            parsed_version,
            compiler.create_build_settings([SolcOutputSelectionEnum.STORAGE_LAYOUT]),
        )
    )

    if any(e.severity == SolcOutputErrorSeverityEnum.ERROR for e in solc_output.errors):
        raise ValueError("Errors during compilation")

    contract_name = parsed["result"][0]["ContractName"]
    try:
        info = next(
            c[contract_name]
            for c in solc_output.contracts.values()
            if contract_name in c
        )
    except StopIteration:
        raise ValueError("Contract not found in compilation output")

    assert info.storage_layout is not None
    return info.storage_layout
