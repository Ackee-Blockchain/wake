import pathlib as plib
import keyword
from typing import Union
from typing_extensions import TypedDict

import brownie.project
from brownie.network.contract import ProjectContract
from brownie.network.account import Account

from woke.a_config import WokeConfig


EvmAccount = Union[Account, ProjectContract]
TxnConfig = TypedDict("TxnConfig", {"from": EvmAccount})


def _sol_to_py(sol: str, input: bool) -> str:
    primitive = None

    if sol.startswith("int") or sol.startswith("uint"):
        if input:
            primitive = "Union[int, float, Decimal]"
        else:
            primitive = "int"

    if sol.startswith("contract") or sol.startswith("address"):
        primitive = "EvmAccount"

    if sol.startswith("bool"):
        primitive = "bool"

    if sol.startswith("string"):
        primitive = "str"

    if sol.startswith("bytes"):
        primitive = "bytes"

    assert primitive, f"Unexpected type: {sol}"

    if sol.endswith("[]"):
        return f"List[{primitive}]"
    else:
        return primitive


template = """from typing import Tuple, Union, List

from brownie.network.contract import ProjectContract
from brownie.network.transaction import TransactionReceipt

from woke.m_fuzz.abi_to_type import EvmAccount, TxnConfig

from decimal import Decimal


"""


def generate_types(config: WokeConfig, overwrite: bool = False) -> None:
    pytypes_dir = config.project_root_path / "pytypes"
    pytypes_dir.mkdir(exist_ok=True)
    if any(pytypes_dir.iterdir()) and not overwrite:
        raise ValueError("'pytypes' directory is not empty.")

    project = brownie.project.load()
    for contract in project:
        contract_name = contract._name
        abi = contract.abi
        target_path = pytypes_dir / f"{contract_name}.py"
        class_name = f"{contract_name}Type"
        res = template
        res += f"class {class_name}(ProjectContract):\n"
        for el in abi:
            try:
                if el["type"] == "function":
                    # region function_name
                    function_name = el["name"]
                    # endregion function_name

                    # region params
                    inputs = el["inputs"]
                    params = []
                    # We need to keep track of unknown parameters, so we don't name them equally
                    no_of_unknowns = 0
                    for input in inputs:
                        param_name = input["name"]
                        if not param_name:
                            param_name = f"_unkown_{no_of_unknowns}"
                            no_of_unknowns += 1
                        if keyword.iskeyword(param_name):
                            param_name += "_"
                        params.append(
                            (param_name, _sol_to_py(input["type"], input=True))
                        )
                        del param_name

                    del inputs

                    params_strs = (
                        ["self"]
                        + [f"{p[0]}: {p[1]}" for p in params]
                        + ["d: Union[TxnConfig, None] = None"]
                    )

                    del params

                    params_str = ", ".join(params_strs)

                    del params_strs

                    # endregion params

                    # region return_values

                    if el["stateMutability"] in ["pure", "view"]:
                        return_values = [
                            _sol_to_py(output["type"], input=False)
                            for output in el["outputs"]
                        ]

                        if len(return_values) == 0:
                            return_values_str = "None"
                        elif len(return_values) == 1:
                            return_values_str = return_values[0]
                        else:
                            return_values_str = (
                                "Tuple[" + ", ".join(return_values) + "]"
                            )
                        del return_values
                    else:
                        return_values_str = "TransactionReceipt"

                    # endregion return_values

                    # region create method
                    sub = f"    def {function_name}({params_str}) -> {return_values_str}:\n"
                    res += sub + " " * 8 + "..." + "\n" * 2
                    # endregion create method
            except:
                print(f"el failed: {el}")
                raise Exception()
        # ensure parents exist
        plib.Path.mkdir(target_path.parent, parents=True, exist_ok=True)
        target_path.write_text(res)
