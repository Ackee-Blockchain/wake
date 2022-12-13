import logging
import multiprocessing.connection
import random
from datetime import datetime, timedelta
from typing import Callable, Counter, Iterable, List, Optional, Tuple

from woke.testing.core import ChainInterface, default_chain

from .coverage import CoverageProvider
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
            Tuple[CoverageProvider, multiprocessing.connection.Connection]
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
                    flow[0]()
                    if not dry_run and invs:
                        for idx, inv in enumerate(invs):
                            logger.info(f'{"inv...":<33}{inv[1]}')
                            inv[0]()
                            del inv

                    if j % 23 == 0 and coverage is not None:
                        coverage[0].update_coverage()
                        coverage[1].send(coverage[0].get_coverage())

                if coverage is not None:
                    coverage[0].update_coverage()
                    coverage[1].send(coverage[0].get_coverage())  # type: ignore

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
