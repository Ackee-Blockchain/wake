import logging
import multiprocessing.queues
import random
from datetime import datetime, timedelta
from typing import Callable, Counter, List, Optional, Tuple

from typing_extensions import get_type_hints

from woke.testing.core import Address, Wei, default_chain

from .coverage import CoverageProvider
from .primitive_types import *
from .random import random_address, random_bytes, random_string
from .utils import partition

Methods = List[Tuple[Callable, str]]


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _generate_flows(flows: Methods, flows_count: int, seq) -> Methods:
    adjusted_weights = []

    min_times_sum = 0
    for i, flow in enumerate(flows):
        cf = flow[0]
        if hasattr(cf, "min_times"):
            min_times_sum += cf.min_times
            if hasattr(cf, "max_times") and cf.min_times > cf.max_times:
                raise ValueError(f"Flow {flow[1]} has min_times greater than max_times")

        if hasattr(cf, "weight"):
            adjusted_weights.append(cf.weight)
        else:
            raise ValueError(f"Flow {flow[1]} doesn't have valid weight")
    if min_times_sum > flows_count:
        raise ValueError("Current min_times can't be satisfied")
    generated_flows = []
    generated_cnt = Counter[str]()

    # weight needed for one flow call to be randomly generated, say a flow has
    # weight == 3 * weight_unit => flow will be 3 times in generated_flows on average
    weight_unit = sum(adjusted_weights) / flows_count
    for i, flow in enumerate(flows):
        cf, fname = flow
        if hasattr(cf, "min_times"):
            generated_flows += [flow] * cf.min_times
            generated_cnt[fname] += cf.min_times
            # this removes weight from a flow that was generated because of min_times
            weight = adjusted_weights[i] - (weight_unit * cf.min_times)
            adjusted_weights[i] = (
                weight
                if weight >= 0
                else (0 if hasattr(cf, "weight") and not cf.weight else 1)
            )

    indexed_flows = {k: v for k, v in enumerate(flows)}
    for _ in range(flows_count - len(generated_flows)):

        def meets_preconditions(indexed_flow: Tuple[int, Tuple[Callable, str]]):
            cf, fname = indexed_flow[1]
            meets_precondition = not hasattr(cf, "precondition") or cf.precondition(seq)
            meets_max_times = (
                not hasattr(cf, "max_times") or generated_cnt[fname] < cf.max_times
            )
            return meets_precondition and meets_max_times

        indexed_flows_p, _ = partition(indexed_flows.items(), meets_preconditions)
        if len(indexed_flows_p) == 0:
            raise ValueError("Conditions for flows could not be met")
        indexed_flow = random.choices(
            indexed_flows_p,
            weights=[adjusted_weights[k] for k, v in indexed_flows_p],
            k=1,
        )[0]
        generated_cnt.update((indexed_flow[1][1],))
        generated_flows.append(indexed_flow[1])

    random.shuffle(generated_flows)
    logger.debug(
        f"Generating following flow sequence {[flow[1] for flow in generated_flows]}"
    )
    return generated_flows


def _update_send_coverage(
    proc_cov: Tuple[CoverageProvider, multiprocessing.queues.Queue]
):
    proc_cov[0].update_coverage()
    if not proc_cov[1].empty():
        proc_cov[1].get()
    proc_cov[1].put(
        (
            proc_cov[0].get_coverage().get_contract_ide_coverage(False),
            proc_cov[0].get_coverage().get_contract_ide_coverage(True),
        )
    )


class Campaign:
    __sequence_constructor: Callable

    def __init__(self, sequence_constructor: Callable) -> None:
        self.__sequence_constructor = sequence_constructor

    def run(
        self,
        sequences_count: int,
        flows_count: int,
        run_for_seconds: Optional[int] = None,
        dry_run: bool = False,
        coverage: Optional[
            Tuple[CoverageProvider, multiprocessing.queues.Queue]
        ] = None,
    ):
        init_timestamp = datetime.now()

        for i in range(sequences_count):
            if (
                run_for_seconds is not None
                and datetime.now()
                >= init_timestamp + timedelta(seconds=run_for_seconds)
            ):
                break

            with default_chain.snapshot_and_revert():
                logger.info(self.__format_heading(f"SEQUENCE {i}"))
                seq = self.__sequence_constructor()

                flows, _ = self.__get_methods(seq, attr="flow")
                invs, _ = self.__get_methods(seq, attr="invariant")

                # point_coverage = Counter[str]()

                try:
                    generated_flows = _generate_flows(flows, flows_count, seq)
                    for f in flows:
                        logger.info(f"{f[1]} {f[0].weight}: {generated_flows.count(f)}")
                except ValueError as ex:
                    logger.exception("Exception caught while generating flows sequence")
                    raise ex

                for j, flow in enumerate(generated_flows):
                    logger.info(
                        f'\n{f"FLOW...":<9} {j:>4} IN SEQUENCE {i:>5} {flow[1]}:'
                    )
                    params = _generate_params_for_flow(flow[0])
                    flow[0](*params)
                    if not dry_run and invs:
                        for idx, inv in enumerate(invs):
                            logger.info(f'{"inv...":<33}{inv[1]}')
                            inv[0]()
                            del inv

                    if j % 23 == 0 and coverage is not None:
                        _update_send_coverage(coverage)

                if coverage is not None:
                    _update_send_coverage(coverage)

                del invs, flows
                # point_coverage += seq.point_coverage
                # logger.info(self.__format_heading("Sequence point coverage:"))
                # self.__log_point_coverage(seq.point_coverage)
                # logger.info(self.__format_heading("Campaign point coverage:"))
                # self.__log_point_coverage(point_coverage)
                del seq

        logger.info(f"\nRan {flows_count} flows. All flows and invariants passed.")

    @staticmethod
    def __is_ign(m: Callable) -> bool:
        return hasattr(m, "ignore") and m.ignore

    @staticmethod
    def __get_methods(o, attr: str) -> Tuple[Methods, Methods]:
        """get not ignored and ignored methods of object {o} beginning with {prefix} and having attribute a truthy attribute {attr}"""
        ms = []
        for m_str in dir(o):
            m = getattr(o, m_str)
            if hasattr(m, attr) and getattr(m, attr):
                # m_str_body = m_str.split(prefix)[1] if prefix else m_str
                # if m_str_body.startswith('_'):
                #     m_str_body = m_str_body[1:]
                ms.append((m, m_str))

        # invariant: at this point, ms contains all relevant methods
        # now find those that aren't and are ignored

        ms_ign, ms_not_ign = partition(ms, lambda m: Campaign.__is_ign(m[0]))

        if ms_ign:
            s = "Ignoring:\n" + "\n".join(m[1] for m in ms_ign)
            logger.info(s)
        del ms
        return ms_not_ign, ms_ign

    @staticmethod
    def __format_heading(s: str) -> str:
        res = ""
        res += "\n"
        res += "-" * len(s) + "\n"
        res += s
        res += "\n"
        res += "-" * len(s) + "\n"
        res += "\n"
        return res

    @staticmethod
    def __log_point_coverage(c: Counter):
        items = list(c.items())
        items.sort()
        for key, count in items:
            print(f"{key:.<80}{count:.>4}")


generators_map = {
    bool: lambda: random.choice([True, False]),
    Address: lambda: random_address(),
    Wei: lambda: Wei(random.randint(0, 10000000000000000000)),
    int: lambda: random.randint(-(2**255), 2**255 - 1),
    bytes: lambda: bytes(random_bytes(0, 64)),
    bytearray: lambda: random_bytes(0, 64),
    str: lambda: random_string(0, 64),
    bytes1: lambda: random_bytes(1),
    bytes2: lambda: random_bytes(2),
    bytes3: lambda: random_bytes(3),
    bytes4: lambda: random_bytes(4),
    bytes5: lambda: random_bytes(5),
    bytes6: lambda: random_bytes(6),
    bytes7: lambda: random_bytes(7),
    bytes8: lambda: random_bytes(8),
    bytes9: lambda: random_bytes(9),
    bytes10: lambda: random_bytes(10),
    bytes11: lambda: random_bytes(11),
    bytes12: lambda: random_bytes(12),
    bytes13: lambda: random_bytes(13),
    bytes14: lambda: random_bytes(14),
    bytes15: lambda: random_bytes(15),
    bytes16: lambda: random_bytes(16),
    bytes17: lambda: random_bytes(17),
    bytes18: lambda: random_bytes(18),
    bytes19: lambda: random_bytes(19),
    bytes20: lambda: random_bytes(20),
    bytes21: lambda: random_bytes(21),
    bytes22: lambda: random_bytes(22),
    bytes23: lambda: random_bytes(23),
    bytes24: lambda: random_bytes(24),
    bytes25: lambda: random_bytes(25),
    bytes26: lambda: random_bytes(26),
    bytes27: lambda: random_bytes(27),
    bytes28: lambda: random_bytes(28),
    bytes29: lambda: random_bytes(29),
    bytes30: lambda: random_bytes(30),
    bytes31: lambda: random_bytes(31),
    bytes32: lambda: random_bytes(32),
    uint8: lambda: random.randint(0, 2**8 - 1),
    uint16: lambda: random.randint(0, 2**16 - 1),
    uint24: lambda: random.randint(0, 2**24 - 1),
    uint32: lambda: random.randint(0, 2**32 - 1),
    uint40: lambda: random.randint(0, 2**40 - 1),
    uint48: lambda: random.randint(0, 2**48 - 1),
    uint56: lambda: random.randint(0, 2**56 - 1),
    uint64: lambda: random.randint(0, 2**64 - 1),
    uint72: lambda: random.randint(0, 2**72 - 1),
    uint80: lambda: random.randint(0, 2**80 - 1),
    uint88: lambda: random.randint(0, 2**88 - 1),
    uint96: lambda: random.randint(0, 2**96 - 1),
    uint104: lambda: random.randint(0, 2**104 - 1),
    uint112: lambda: random.randint(0, 2**112 - 1),
    uint120: lambda: random.randint(0, 2**120 - 1),
    uint128: lambda: random.randint(0, 2**128 - 1),
    uint136: lambda: random.randint(0, 2**136 - 1),
    uint144: lambda: random.randint(0, 2**144 - 1),
    uint152: lambda: random.randint(0, 2**152 - 1),
    uint160: lambda: random.randint(0, 2**160 - 1),
    uint168: lambda: random.randint(0, 2**168 - 1),
    uint176: lambda: random.randint(0, 2**176 - 1),
    uint184: lambda: random.randint(0, 2**184 - 1),
    uint192: lambda: random.randint(0, 2**192 - 1),
    uint200: lambda: random.randint(0, 2**200 - 1),
    uint208: lambda: random.randint(0, 2**208 - 1),
    uint216: lambda: random.randint(0, 2**216 - 1),
    uint224: lambda: random.randint(0, 2**224 - 1),
    uint232: lambda: random.randint(0, 2**232 - 1),
    uint240: lambda: random.randint(0, 2**240 - 1),
    uint248: lambda: random.randint(0, 2**248 - 1),
    uint256: lambda: random.randint(0, 2**256 - 1),
    int8: lambda: random.randint(-(2**7), 2**7 - 1),
    int16: lambda: random.randint(-(2**15), 2**15 - 1),
    int24: lambda: random.randint(-(2**23), 2**23 - 1),
    int32: lambda: random.randint(-(2**31), 2**31 - 1),
    int40: lambda: random.randint(-(2**39), 2**39 - 1),
    int48: lambda: random.randint(-(2**47), 2**47 - 1),
    int56: lambda: random.randint(-(2**55), 2**55 - 1),
    int64: lambda: random.randint(-(2**63), 2**63 - 1),
    int72: lambda: random.randint(-(2**71), 2**71 - 1),
    int80: lambda: random.randint(-(2**79), 2**79 - 1),
    int88: lambda: random.randint(-(2**87), 2**87 - 1),
    int96: lambda: random.randint(-(2**95), 2**95 - 1),
    int104: lambda: random.randint(-(2**103), 2**103 - 1),
    int112: lambda: random.randint(-(2**111), 2**111 - 1),
    int120: lambda: random.randint(-(2**119), 2**119 - 1),
    int128: lambda: random.randint(-(2**127), 2**127 - 1),
    int136: lambda: random.randint(-(2**135), 2**135 - 1),
    int144: lambda: random.randint(-(2**143), 2**143 - 1),
    int152: lambda: random.randint(-(2**151), 2**151 - 1),
    int160: lambda: random.randint(-(2**159), 2**159 - 1),
    int168: lambda: random.randint(-(2**167), 2**167 - 1),
    int176: lambda: random.randint(-(2**175), 2**175 - 1),
    int184: lambda: random.randint(-(2**183), 2**183 - 1),
    int192: lambda: random.randint(-(2**191), 2**191 - 1),
    int200: lambda: random.randint(-(2**199), 2**199 - 1),
    int208: lambda: random.randint(-(2**207), 2**207 - 1),
    int216: lambda: random.randint(-(2**215), 2**215 - 1),
    int224: lambda: random.randint(-(2**223), 2**223 - 1),
    int232: lambda: random.randint(-(2**231), 2**231 - 1),
    int240: lambda: random.randint(-(2**239), 2**239 - 1),
    int248: lambda: random.randint(-(2**247), 2**247 - 1),
    int256: lambda: random.randint(-(2**255), 2**255 - 1),
}


def _generate_params_for_flow(flow: Callable) -> List:
    hints = get_type_hints(flow)
    ret = []
    for type_ in hints.values():
        try:
            ret.append(generators_map[type_]())
        except KeyError:
            raise ValueError(f"No fuzz generator found for type {type_}")
    return ret
