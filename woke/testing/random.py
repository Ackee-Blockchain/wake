import random
import string
from typing import Callable, Optional

from .contract import Account, Address, ChainInterface, dev_interface


def random_account(
    lower_bound: int = 0,
    length: Optional[int] = None,
    predicate: Optional[Callable[[Account], bool]] = None,
    chain: Optional[ChainInterface] = None,
) -> Account:
    if chain is None:
        chain = dev_interface
    accounts = chain.accounts
    if length is None:
        length = len(accounts)
    accounts = accounts[lower_bound:length]
    if predicate is not None:
        accounts = [acc for acc in accounts if predicate(acc)]
    return random.choice(accounts)


def random_address() -> Address:
    return Address("0x" + random_bytes(20, 20).hex())


def random_int(min: int, max: int) -> int:
    """like random.randint, but with the following probability distribution:
    if min < 0 and max > 0:
        20%: min
        20%:   0
        20%: max
        40%: random.randint(min, max)
    else:
        20%: min
        20%: max
        60%: random.randint(min, max)"""
    if min < 0 and max > 0:
        p = random.random()
        if p < 0.2:
            res = min
        elif p < 0.4:
            res = 0
        elif p < 0.6:
            res = max
        else:
            res = random.randint(min, max)
    else:
        p = random.random()
        if p < 0.2:
            res = min
        elif p < 0.4:
            res = max
        else:
            res = random.randint(min, max)
    return res


def random_bool() -> bool:
    return random.choice([True, False])


def random_string(
    min: int,
    max: int,
    alphabet: str = string.ascii_letters,
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
    min: int, max: int, predicate: Optional[Callable[[bytes], bool]] = None
) -> bytes:
    def gen() -> bytes:
        len = random.randint(min, max)
        return bytes(random.getrandbits(8) for _ in range(len))

    ret = gen()
    if predicate is None:
        return ret

    while not predicate(ret):
        ret = gen()
    return ret
