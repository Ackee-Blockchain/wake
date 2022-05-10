import logging
import random
from datetime import datetime, timedelta
from typing import Counter, List, Tuple, Callable, Optional

import brownie

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
        rules_count: int,
        run_for_seconds: Optional[int] = None,
        dry_run: bool = False,
    ):
        init_timestamp = datetime.now()

        for i in range(sequences_count):
            if (
                run_for_seconds is not None
                and datetime.now()
                >= init_timestamp + timedelta(seconds=run_for_seconds)
            ):
                break
            logger.info(self.__format_heading(f"SEQUENCE {i}"))
            brownie.chain.reset()
            seq = self.__sequence_constructor()

            rules, _ = self.__get_methods(seq, attr="rule")
            invs, _ = self.__get_methods(seq, attr="invariant")

            called = Counter[str]()
            point_coverage = Counter[str]()

            for j in range(rules_count):
                if rules:

                    def meets_preconditions(rule):
                        rule = rule[0]
                        meets_precondition = not hasattr(
                            rule, "precondition"
                        ) or rule.precondition(seq)
                        meets_max_times = (
                            not hasattr(rule, "max_times")
                            or called[rule] < rule.max_times
                        )
                        return meets_precondition and meets_max_times

                    rules_p, rules_not_p = partition(rules, meets_preconditions)
                    if rules_not_p:
                        logger.info(f"\nThe following rules' preconditions are falsy:")
                        for rule_not_p in rules_not_p:
                            logger.info(f"    {rule_not_p[1]}")
                    else:
                        logger.info(f"\n")

                    rules_weights = []

                    for rule in rules_p:
                        if hasattr(rule[0], "weight"):
                            rules_weights.append(rule[0].weight)
                        else:
                            rules_weights.append(100)

                    logger.info("Weights:")
                    for idx in range(len(rules_p)):
                        logger.info(f"    {rules_p[idx][1]}: {rules_weights[idx]}")
                    rule = random.choices(rules_p, weights=rules_weights, k=1)[0]
                    called.update((rule[0],))  # type: ignore

                    logger.info(
                        f'\n{f"RULE...":<9} {j:>4} IN SEQUENCE {i:>5} {rule[1]}:'
                    )
                    rule[0]()

                if not dry_run and invs:
                    for idx, inv in enumerate(invs):
                        logger.info(f'{"inv...":<33}{inv[1]}')
                        inv[0]()
                        del inv

            del invs, rules
            point_coverage += seq.point_coverage
            logger.info(self.__format_heading("Sequence point coverage:"))
            self.__log_point_coverage(seq.point_coverage)
            logger.info(self.__format_heading("Campaign point coverage:"))
            self.__log_point_coverage(point_coverage)
            del seq
        logger.info(f"\nRan {rules_count} rules. All rules and invariants passed.")

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
