from __future__ import annotations

import functools
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wake.ir import ContractDefinition, InlineAssembly


@functools.lru_cache(maxsize=256)
def contract_is_proxy(contract: ContractDefinition) -> bool:
    from wake.ir import InlineAssembly, YulFunctionCall
    from wake.ir.enums import FunctionKind

    fallback = None
    for c in contract.linearized_base_contracts:
        try:
            fallback = next(f for f in c.functions if f.kind == FunctionKind.FALLBACK)
            break
        except StopIteration:
            continue

    if fallback is None or fallback.body is None:
        return False

    for statement in fallback.body.statements_iter():
        # TODO also check for low-level Solidity delegatecall
        if isinstance(statement, InlineAssembly):
            for node in statement.yul_block:
                if (
                    isinstance(node, YulFunctionCall)
                    and node.function_name.name == "delegatecall"
                ):
                    return True

    return False
