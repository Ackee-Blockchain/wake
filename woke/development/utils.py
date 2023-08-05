from __future__ import annotations

import asyncio
import functools
import importlib
import inspect
import json
import math
from collections import namedtuple
from functools import lru_cache
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
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
    SolcOutputStorageLayoutStorage,
    SolcOutputStorageLayoutType,
)
from ..config import WokeConfig
from ..core.solidity_version import SolidityVersion
from ..svm import SolcVersionManager
from ..utils import get_package_version
from .chain_interfaces import ChainInterfaceAbc
from .core import (
    Abi,
    Account,
    Address,
    get_contracts_by_fqn,
    get_fqn_from_address,
    get_user_defined_value_types_index,
)
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


def _get_storage_layout(contract: Account) -> SolcOutputStorageLayout:
    fqn = get_fqn_from_address(contract.address, "latest", contract.chain)
    if fqn is None:
        if contract.chain._fork is None:
            raise ValueError("Contract not found")

        forked_chain_interface = ChainInterfaceAbc.connect(
            get_config(), contract.chain._fork
        )
        try:
            forked_chain_id = forked_chain_interface.get_chain_id()
        finally:
            forked_chain_interface.close()

        if forked_chain_id not in chain_explorer_urls:
            raise ValueError(
                f"Chain explorer URL not found for chain ID {forked_chain_id}"
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
            "User-Agent": f"woke/{get_package_version('woke')}",
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

    compilation_config = WokeConfig.fromdict(
        config_dict,
        project_root_path=config.project_root_path,
    )
    compiler = SolidityCompiler(compilation_config)

    graph, _ = compiler.build_graph(
        sources.keys(), sources, True  # pyright: ignore reportGeneralTypeIssues
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
