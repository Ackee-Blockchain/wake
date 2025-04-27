from wake.utils import StrEnum


class EvmVersionEnum(StrEnum):
    HOMESTEAD = "homestead"
    TANGERINE_WHISTLE = "tangerineWhistle"
    SPURIOUS_DRAGON = "spuriousDragon"
    BYZANTIUM = "byzantium"
    CONSTANTINOPLE = "constantinople"
    PETERSBURG = "petersburg"
    ISTANBUL = "istanbul"
    BERLIN = "berlin"
    LONDON = "london"
    PARIS = "paris"
    SHANGHAI = "shanghai"
    CANCUN = "cancun"
    PRAGUE = "prague"
    OSAKA = "osaka"

    def __lt__(self, other: "EvmVersionEnum") -> bool:
        if not isinstance(other, EvmVersionEnum):
            return NotImplemented
        return _order.index(self) < _order.index(other)

    def __le__(self, other: "EvmVersionEnum") -> bool:
        if not isinstance(other, EvmVersionEnum):
            return NotImplemented
        return _order.index(self) <= _order.index(other)

    def __gt__(self, other: "EvmVersionEnum") -> bool:
        if not isinstance(other, EvmVersionEnum):
            return NotImplemented
        return _order.index(self) > _order.index(other)

    def __ge__(self, other: "EvmVersionEnum") -> bool:
        if not isinstance(other, EvmVersionEnum):
            return NotImplemented
        return _order.index(self) >= _order.index(other)


# Define order of versions
_order = [
    EvmVersionEnum.HOMESTEAD,
    EvmVersionEnum.TANGERINE_WHISTLE,
    EvmVersionEnum.SPURIOUS_DRAGON,
    EvmVersionEnum.BYZANTIUM,
    EvmVersionEnum.CONSTANTINOPLE,
    EvmVersionEnum.PETERSBURG,
    EvmVersionEnum.ISTANBUL,
    EvmVersionEnum.BERLIN,
    EvmVersionEnum.LONDON,
    EvmVersionEnum.PARIS,
    EvmVersionEnum.SHANGHAI,
    EvmVersionEnum.CANCUN,
    EvmVersionEnum.PRAGUE,
    EvmVersionEnum.OSAKA,
]
