import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from Crypto.Hash import keccak

from wake.cli.console import console
from wake.config import WakeConfig
from wake.utils import get_package_version
from wake.utils.keyed_default_dict import KeyedDefaultDict
from .constants import DEFAULT_IMPORTS, INIT_CONTENT


class VyperPytypesGenerator:
    _config: WakeConfig
    _return_tx: bool

    _abi_map = Dict[str, str]

    def __init__(self, config: WakeConfig, return_tx: bool = False):
        self._config = config
        self._return_tx = return_tx

        self._abi_map = KeyedDefaultDict(
            lambda k: k
        )
        self._abi_map["string"] = "str"

    def generate(self, vy_build: Dict[str, Any]) -> None:
        shutil.rmtree(Path.cwd() / "pytypes", ignore_errors=True)

        for p in vy_build["contracts"].keys():
            if p in {"version", "compiler"}:
                continue

            x = Path.cwd() / "pytypes"
            for part in Path(p).relative_to(Path.cwd()).with_suffix("").parts:
                x = x / part
            x = x.with_suffix(".py")

            for contract_name, build in vy_build["contracts"][p].items():
                self._generate(x, contract_name, build)

        init_path = Path.cwd() / "pytypes" / "__init__.py"
        init_path.parent.mkdir(parents=True, exist_ok=True)
        init_path.write_text(
            INIT_CONTENT.format(
                version=get_package_version("eth-wake"),
                errors={},
                events={},
                contracts_by_fqn={},
                contracts_by_metadata={},
                contracts_inheritance={},
                contracts_revert_index={},
                creation_code_index={},
                user_defined_value_types_index={},
            )
        )

    def _gen_struct(self, struct: Dict[str, Any]) -> str:

        return ""

    def _gen_function(self, abi: Dict[str, Any]) -> str:
        console.print_json(
            json.dumps(abi, indent=4, sort_keys=True, ensure_ascii=False)
        )

        params = []
        for i in abi["inputs"]:
            params.append((i["name"], self._abi_map[i["type"]]))

        params_str = ", ".join(f"{p[0]}: {p[1]}" for p in params)
        param_names = [p[0] for p in params]

        ret_types = []
        for i in abi["outputs"]:
            ret_types.append(self._abi_map[i["type"]])

        if len(ret_types) == 0:
            return_types = "NoneType"
        elif len(ret_types) == 1:
            return_types = ret_types[0]
        else:
            return_types = f"Tuple[{', '.join(ret_types)}]"

        sig = abi["name"] + "(" + ",".join(i["type"] for i in abi["inputs"]) + ")"
        fn_selector = keccak.new(data=sig.encode("utf-8"), digest_bits=256).hexdigest()[:8]

        is_view_or_pure = abi["stateMutability"] in {"view", "pure"}

        out = ""
        out += f"""    def {abi["name"]}(self, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, to: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, request_type: RequestType = '{'call' if is_view_or_pure else 'tx'}', gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> Union[{return_types}, TransactionAbc[{return_types}], int, Tuple[Dict[Address, List[int]], int]]:\n"""
        out += f'        return self._execute(self.chain, request_type, "{fn_selector}", [{", ".join(param_names)}], True if request_type == "tx" else False, {return_types}, from_, to if to is not None else str(self.address), value, gas_limit, gas_price, max_fee_per_gas, max_priority_fee_per_gas, access_list, type, block, confirmations)\n\n'
        return out

    def _gen_deploy(self, contract_name: str, abi: Optional[Dict[str, Any]]) -> str:
        if abi is None:
            inputs = []
        else:
            inputs = abi["inputs"]
        params = []
        for i in inputs:
            params.append((i["name"], self._abi_map[i["type"]]))

        params_str = ", ".join(f"{p[0]}: {p[1]}" for p in params)
        param_names = [p[0] for p in params]

        out = ""
        out += f"    @classmethod\n"
        out += f'    def deploy(cls, {params_str}*, from_: Optional[Union[Account, Address, str]] = None, value: Union[int, str] = 0, gas_limit: Optional[Union[int, Literal["max"], Literal["auto"]]] = None, return_tx: bool = {self._return_tx}, request_type: RequestType = "tx", chain: Optional[Chain] = None, gas_price: Optional[Union[int, str]] = None, max_fee_per_gas: Optional[Union[int, str]] = None, max_priority_fee_per_gas: Optional[Union[int, str]] = None, access_list: Optional[Union[Dict[Union[Account, Address, str], List[int]], Literal["auto"]]] = None, type: Optional[int] = None, block: Optional[Union[int, Literal["latest"], Literal["pending"], Literal["earliest"], Literal["safe"], Literal["finalized"]]] = None, confirmations: Optional[int] = None) -> Union[bytearray, {contract_name}, int, Tuple[Dict[Address, List[int]], int], TransactionAbc[{contract_name}]]:\n'
        out += f"        return cls._deploy(request_type, [{', '.join(param_names)}], return_tx, {contract_name}, from_, value, gas_limit, {{}}, chain, gas_price, max_fee_per_gas, max_priority_fee_per_gas, access_list, type, block, confirmations)\n\n"

        return out

    def _generate(self, path: Path, contract_name: str, build: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        abi = build["abi"]

        try:
            constructor_abi = next(i for i in abi if i["type"] == "constructor")
        except StopIteration:
            constructor_abi = None

        abi_by_selector = {}
        if constructor_abi is not None:
            abi_by_selector["constructor"] = constructor_abi

        for i in abi:
            if i["type"] == "function":
                sig = i["name"] + "(" + ",".join(i["type"] for i in i["inputs"]) + ")"
                fn_selector = keccak.new(data=sig.encode("utf-8"), digest_bits=256).digest()[:4] # wow
                abi_by_selector[fn_selector] = i

        out = ""
        out += DEFAULT_IMPORTS
        out += "\n"
        out += f"class {contract_name}(Contract):\n"
        out += f"    _abi={abi_by_selector}\n"
        out += f'    _creation_code="{build["evm"]["bytecode"]["object"][2:]}"\n\n'
        out += f"    @classmethod\n"
        out += f"    def get_creation_code(cls) -> bytes:\n"
        out += f'        return bytes.fromhex(cls._creation_code)\n\n'

        out += self._gen_deploy(contract_name, constructor_abi)

        for i in abi:
            if i["type"] == "function":
                out += self._gen_function(i)

        path.write_text(out)
        return
