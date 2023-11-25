from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Set, Union

from rich_click import Context, Parameter, ParamType

if TYPE_CHECKING:
    from click.shell_completion import CompletionItem
    from typing_extensions import Literal

    SupportedTypes = Literal[
        "contract",
        "enum",
        "error",
        "event",
        "function",
        "modifier",
        "struct",
        "user_defined_value_type",
        "variable",
    ]


class SolidityName(ParamType):
    case_sensitive: bool
    types: Set[SupportedTypes]

    name = "solidity name"

    def __init__(
        self,
        *types: SupportedTypes,
        case_sensitive: bool = True,
        canonical: bool = True,
        non_canonical: bool = True,
    ) -> None:
        self.types = set(types)
        self.case_sensitive = case_sensitive
        self.canonical = canonical
        self.non_canonical = non_canonical

    def shell_complete(
        self, ctx: Context, param: Parameter, incomplete: str
    ) -> List[CompletionItem]:
        import json
        from itertools import chain

        from click.shell_completion import CompletionItem

        try:
            symbols_index = json.loads(
                Path.cwd().joinpath(".wake/build/symbols.json").read_text()
            )

            symbols = []
            if "contract" in self.types:
                if self.non_canonical or self.canonical:
                    symbols.append(symbols_index["contracts"])
            if "enum" in self.types:
                if self.non_canonical:
                    symbols.append(symbols_index["enums"])
                if self.canonical:
                    symbols.append(symbols_index["canonical_enums"])
            if "error" in self.types:
                if self.non_canonical:
                    symbols.append(symbols_index["errors"])
                if self.canonical:
                    symbols.append(symbols_index["canonical_errors"])
            if "event" in self.types:
                if self.non_canonical:
                    symbols.append(symbols_index["events"])
                if self.canonical:
                    symbols.append(symbols_index["canonical_events"])
            if "function" in self.types:
                if self.non_canonical:
                    symbols.append(symbols_index["functions"])
                if self.canonical:
                    symbols.append(symbols_index["canonical_functions"])
            if "modifier" in self.types:
                if self.non_canonical:
                    symbols.append(symbols_index["modifiers"])
                if self.canonical:
                    symbols.append(symbols_index["canonical_modifiers"])
            if "struct" in self.types:
                if self.non_canonical:
                    symbols.append(symbols_index["structs"])
                if self.canonical:
                    symbols.append(symbols_index["canonical_structs"])
            if "user_defined_value_type" in self.types:
                if self.non_canonical:
                    symbols.append(symbols_index["user_defined_value_types"])
                if self.canonical:
                    symbols.append(symbols_index["canonical_user_defined_value_types"])
            if "variable" in self.types:
                if self.non_canonical:
                    symbols.append(symbols_index["variables"])
                if self.canonical:
                    symbols.append(symbols_index["canonical_variables"])

            if self.case_sensitive:
                ret = [
                    CompletionItem(f)
                    for f in chain.from_iterable(symbols)
                    if f.startswith(incomplete)
                ]
            else:
                incomplete = incomplete.lower()

                ret = [
                    CompletionItem(f)
                    for f in chain.from_iterable(symbols)
                    if f.lower().startswith(incomplete)
                ]
            ret.sort(key=lambda x: x.value)
            return ret
        except Exception:
            return []
