import inspect
from typing import Callable, Optional, Tuple, TypeVar

from .campaign import logger

ModelUpdater = Callable[..., Optional[Tuple]]
TxnReturn = TypeVar("TxnReturn")
Txn = Callable[..., TxnReturn]
TxnEnhanced = Callable[..., TxnReturn]
Decorator = Callable[..., Txn]


def model(model_updater: ModelUpdater) -> Decorator:
    def decorator(txn_enhanced: TxnEnhanced) -> Txn:
        def txn(*args, **kwars) -> TxnReturn:  # type: ignore
            m_res = model_updater(*args)
            if m_res is None:
                return txn_enhanced(*args)  # type: ignore
            else:
                t_names = inspect.signature(txn_enhanced).parameters.keys()
                m_names = inspect.signature(model_updater).parameters.keys()
                # Sanity check
                assert len(m_res) == len(t_names) - len(m_names)
                for m, t in zip(m_names, t_names):
                    assert m == t
                for idx, p in enumerate(tuple(t_names)[len(m_names) :]):
                    logger.debug(f"{p} = {m_res[idx]}")
                return txn_enhanced(*args, *m_res)  # type: ignore

        return txn  # type:ignore

    return decorator


def ignore(fn):
    fn.ignore = True
    return fn


def flow(fn):
    fn.flow = True
    return fn


def invariant(fn):
    fn.invariant = True
    return fn


def precondition(_precondition):
    def decorator(fn):
        fn.precondition = _precondition
        return fn

    return decorator


def max_times(x: int):
    def decorator(fn):
        fn.max_times = x
        return fn

    return decorator


def weight(w: int):
    def decorator(fn):
        fn.weight = w
        return fn

    return decorator
