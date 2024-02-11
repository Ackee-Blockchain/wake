import dataclasses
import enum
import random
import string
from typing import Any, Callable, Dict, Optional, Type

from typing_extensions import Annotated, get_args, get_origin, get_type_hints

from wake.development.core import Account, Address, Chain, Wei, detect_default_chain
from wake.development.primitive_types import FixedSizeBytes, Integer


def random_account(
    *,
    lower_bound: int = 0,
    upper_bound: Optional[int] = None,
    predicate: Optional[Callable[[Account], bool]] = None,
    chain: Optional[Chain] = None,
) -> Account:
    if chain is None:
        chain = detect_default_chain()

    accounts = chain.accounts
    if upper_bound is None:
        upper_bound = len(accounts)
    accounts = accounts[lower_bound:upper_bound]
    if predicate is not None:
        accounts = [acc for acc in accounts if predicate(acc)]
    return random.choice(accounts)


def random_address(*, zero_address_prob: float = 0) -> Address:
    if zero_address_prob is not None and random.random() < zero_address_prob:
        return Address(0)
    ret = Address("0x" + random_bytes(20).hex())
    while ret == Address(0):
        ret = Address("0x" + random_bytes(20).hex())
    return ret


def random_int(
    min: int,
    max: int,
    *,
    min_prob: Optional[float] = None,
    zero_prob: Optional[float] = None,
    max_prob: Optional[float] = None,
    edge_values_prob: Optional[float] = None,
) -> int:
    p = random.random()

    if min_prob is None:
        if edge_values_prob is not None:
            min_prob = edge_values_prob

    if min_prob is not None:
        if p < min_prob:
            return min
        p -= min_prob
        min += 1

    if min < 0 < max:
        if zero_prob is None:
            if edge_values_prob is not None:
                zero_prob = edge_values_prob
    else:
        zero_prob = None

    if zero_prob is not None:
        if p < zero_prob:
            return 0
        p -= zero_prob

    if max_prob is None:
        if edge_values_prob is not None:
            max_prob = edge_values_prob

    if max_prob is not None:
        if p < max_prob:
            return max
        max -= 1

    ret = random.randint(min, max)
    while zero_prob is not None and ret == 0:
        ret = random.randint(min, max)
    return ret


def random_bool(
    *,
    true_prob: float = 0.5,
) -> bool:
    return random.random() < true_prob


def random_string(
    min: int,
    max: int,
    *,
    alphabet: str = string.printable,
    predicate: Optional[Callable[[str], bool]] = None,
) -> str:
    def gen() -> str:
        len = random.randint(min, max)
        return "".join(random.choice(alphabet) for _ in range(len))

    ret = gen()
    if predicate is None:
        return ret

    while not predicate(ret):
        ret = gen()
    return ret


def random_bytes(
    min: int,
    max: Optional[int] = None,
    *,
    predicate: Optional[Callable[[bytes], bool]] = None,
) -> bytearray:
    """
    Generates a random bytearray of length between min and max.
    If max is None, the length is exactly min.
    """

    def gen() -> bytearray:
        if max is None:
            len = min
        else:
            len = random.randint(min, max)
        return bytearray(random.getrandbits(8 * len).to_bytes(len, "little"))

    ret = gen()
    if predicate is None:
        return ret

    while not predicate(ret):
        ret = gen()
    return ret


generators_map = {
    bool: lambda: random.choice([True, False]),
    Address: lambda: random_address(),
    Wei: lambda: Wei(random.randint(0, 10000000000000000000)),
}


def generate(t: Type):
    min_len = 0
    max_len = 64

    try:
        return generators_map[t]()
    except KeyError:
        origin = get_origin(t)
        if isinstance(origin, type) and issubclass(origin, list):
            if hasattr(origin, "length"):
                length = getattr(origin, "length")
                return [generate(get_args(t)[0]) for _ in range(length)]
            else:
                return [
                    generate(get_args(t)[0])
                    for _ in range(random.randint(min_len, max_len))
                ]
        elif isinstance(t, type) and issubclass(t, Integer):
            return random.randint(t.min, t.max)
        elif isinstance(t, type) and issubclass(t, FixedSizeBytes):
            return random_bytes(t.length, t.length)
        elif t is int:
            # fallback for int used directly
            return random.randint(-(2**255), 2**255 - 1)
        elif t is bytes:
            return bytes(random_bytes(min_len, max_len))
        elif t is bytearray:
            return random_bytes(min_len, max_len)
        elif t is str:
            return random_string(min_len, max_len)
        elif issubclass(t, enum.Enum):
            return random.choice(list(t))
        elif dataclasses.is_dataclass(t):
            return t(
                *[
                    generate(h)
                    for h in get_type_hints(
                        t,  # pyright: ignore reportGeneralTypeIssues
                        include_extras=True,
                    ).values()
                ]
            )
        else:
            raise ValueError(f"No fuzz generator found for type {t}")
