from typing import Dict, Iterable, Optional, Union

import wake.ir as ir


def find_interface(
    contract: ir.ContractDefinition,
    functions: Iterable[bytes],
    events: Optional[Iterable[bytes]] = None,
    errors: Optional[Iterable[bytes]] = None,
) -> Dict[
    bytes,
    Union[
        ir.FunctionDefinition,
        ir.EventDefinition,
        ir.ErrorDefinition,
        ir.VariableDeclaration,
    ],
]:
    functions = list(functions)
    if events is None:
        events = set()
    else:
        events = set(events)
    if errors is None:
        errors = set()
    else:
        errors = set(errors)

    interface = {}

    for event in contract.used_events:
        if event.event_selector in events:
            interface[event.event_selector] = event
            events.remove(event.event_selector)

    for error in contract.used_errors:
        if error.error_selector in errors:
            interface[error.error_selector] = error
            errors.remove(error.error_selector)

    for c in contract.linearized_base_contracts:
        for func in c.functions:
            if not func.implemented:
                continue
            if func.function_selector in functions:
                interface[func.function_selector] = func
                functions.remove(func.function_selector)

        for var in c.declared_variables:
            if var.function_selector in functions:
                interface[var.function_selector] = var
                functions.remove(var.function_selector)

    return interface
