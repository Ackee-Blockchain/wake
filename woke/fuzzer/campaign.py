import logging
import random
from datetime import datetime, timedelta
from typing import Callable, Counter, List, Optional, Tuple

import brownie
import IPython

from .utils import partition

Methods = List[Tuple[Callable, str]]


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
    ):
        init_timestamp = datetime.now()
        brownie.chain.snapshot()

        for i in range(sequences_count):
            if (
                run_for_seconds is not None
                and datetime.now()
                >= init_timestamp + timedelta(seconds=run_for_seconds)
            ):
                break
            logger.info(self.__format_heading(f"SEQUENCE {i}"))
            brownie.chain.revert()
            seq = self.__sequence_constructor()

            flows, _ = self.__get_methods(seq, attr="flow")
            invs, _ = self.__get_methods(seq, attr="invariant")

            called = Counter[str]()
            # point_coverage = Counter[str]()

            for j in range(flows_count):
                if flows:

                    def meets_preconditions(flow):
                        flow = flow[0]
                        meets_precondition = not hasattr(
                            flow, "precondition"
                        ) or flow.precondition(seq)
                        meets_max_times = (
                            not hasattr(flow, "max_times")
                            or called[flow] < flow.max_times
                        )
                        return meets_precondition and meets_max_times

                    flows_p, flows_not_p = partition(flows, meets_preconditions)
                    if flows_not_p:
                        logger.info(f"\nThe following flows' preconditions are falsy:")
                        for flow_not_p in flows_not_p:
                            logger.info(f"    {flow_not_p[1]}")
                    else:
                        logger.info(f"\n")

                    if len(flows_p) == 0:
                        logger.warning(
                            "There are no rules satisfying conditions. Terminating the sequence..."
                        )
                        break

                    flows_weights = []

                    for flow in flows_p:
                        if hasattr(flow[0], "weight"):
                            flows_weights.append(flow[0].weight)
                        else:
                            flows_weights.append(100)

                    logger.info("Weights:")
                    for idx in range(len(flows_p)):
                        logger.info(f"    {flows_p[idx][1]}: {flows_weights[idx]}")
                    flow = random.choices(flows_p, weights=flows_weights, k=1)[0]
                    called.update((flow[0],))  # type: ignore

                    logger.info(
                        f'\n{f"FLOW...":<9} {j:>4} IN SEQUENCE {i:>5} {flow[1]}:'
                    )
                    flow[0]()

                if not dry_run and invs:
                    for idx, inv in enumerate(invs):
                        logger.info(f'{"inv...":<33}{inv[1]}')
                        inv[0]()
                        del inv

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
