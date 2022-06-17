import keyword
import pathlib as plib
from typing import Union

import brownie.project
from brownie.network.account import Account
from brownie.network.contract import ProjectContract
from typing_extensions import TypedDict

from woke.config import WokeConfig

EvmAccount = Union[Account, ProjectContract]
TxnConfig = TypedDict("TxnConfig", {"from": EvmAccount, "amount": int})

_typed_dict_counter = 0


def _sol_to_py(sol: dict, input: bool) -> str:
    global _typed_dict_counter, template
    primitive = None

    t = sol["type"]

    if t.startswith("int") or t.startswith("uint"):
        if input:
            primitive = "Union[int, float, Decimal]"
        else:
            primitive = "int"

    if t.startswith("contract") or t.startswith("address"):
        primitive = "EvmAccount"

    if t.startswith("bool"):
        primitive = "bool"

    if t.startswith("string"):
        primitive = "str"

    if t.startswith("bytes"):
        primitive = "bytes"

    if t.startswith("tuple"):
        type_name = f"TypedDict_{_typed_dict_counter}"
        _typed_dict_counter += 1
        decl = f'{type_name} = TypedDict("{type_name}", '
        decl += "{\n"
        for component in sol["components"]:
            decl += f"    \"{component['name']}\": {_sol_to_py(component, input)},\n"
        decl += "})\n\n\n"
        template += decl
        primitive = type_name

    assert primitive, f"Unexpected type: {t}"

    while t.endswith("[]"):
        primitive = f"List[{primitive}]"
        t = t[:-2]
    return primitive


template = """from typing import Tuple, Union, List
from typing_extensions import TypedDict

from brownie.network.contract import ProjectContract
from brownie.network.transaction import TransactionReceipt

from woke.fuzzer.abi_to_type import EvmAccount, TxnConfig

from decimal import Decimal


"""


def generate_types(config: WokeConfig, overwrite: bool = False) -> None:
    pytypes_dir = config.project_root_path / "pytypes"
    pytypes_dir.mkdir(exist_ok=True)
    if any(pytypes_dir.iterdir()) and not overwrite:
        raise ValueError("'pytypes' directory is not empty.")

    init_content = ""

    project = brownie.project.load()
    for contract in project:
        contract_name = contract._name
        abi = contract.abi
        target_path = pytypes_dir / f"{contract_name}.py"
        class_name = f"{contract_name}Type"
        res = f"class {class_name}(ProjectContract):\n"
        init_content += f"from .{contract_name} import {class_name}\n"

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
                        params.append((param_name, _sol_to_py(input, input=True)))
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
                            _sol_to_py(output, input=False) for output in el["outputs"]
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
        target_path.write_text(template + res)

    (pytypes_dir / "__init__.py").write_text(init_content)
