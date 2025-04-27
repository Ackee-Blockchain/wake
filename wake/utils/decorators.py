import weakref
from functools import lru_cache, wraps
from typing import Any, Callable, Optional, Tuple, TypeVar

from typing_extensions import ParamSpec

from .context_managers import recursion_guard

T = TypeVar("T")
P = ParamSpec("P")


def get_full_qualified_name(func: Callable) -> str:
    return f"{func.__module__}.{func.__qualname__}"


def weak_self_lru_cache(maxsize=128, typed=False):
    def decorator(method):
        cache = weakref.WeakKeyDictionary()

        @wraps(method)
        def cached_method(self, *args, **kwargs):
            bound_cache_method = cache.get(self)
            if bound_cache_method is None:
                wself = weakref.ref(self)

                @wraps(method)
                @lru_cache(maxsize=maxsize, typed=typed)
                def bound_cache_method(*args, **kwargs):
                    self = wself()
                    if self is None:
                        raise RuntimeError("Method called on freed weakref")
                    return method(self, *args, **kwargs)

                cache[self] = bound_cache_method

            return bound_cache_method(*args, **kwargs)

        return cached_method

    return decorator


def dict_cache(
    cache: Optional[dict] = None, cache_keys: Optional[Tuple[Any, ...]] = None
):
    if cache is None:
        from wake.core.visitor import get_extra

        cache = get_extra()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            if cache_keys is None:
                keys = ("_cache", get_full_qualified_name(func))
            else:
                keys = cache_keys

            current = cache
            for key in keys:
                if key not in current:
                    current[key] = {}
                current = current[key]

            cache_key = (args, tuple(sorted(kwargs.items())))
            if cache_key in current:
                return current[cache_key]

            ret = func(*args, **kwargs)

            current[cache_key] = ret
            return ret

        return wrapper

    return decorator


def return_on_recursion(default: T) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Create guard set specific to this function instance
        arguments_guard = set()

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            if (args, tuple(sorted(kwargs.items()))) in arguments_guard:
                return default
            with recursion_guard(arguments_guard, *args, **kwargs):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def dict_cached_return_on_recursion(
    default: T,
    cache: Optional[dict] = None,
    cache_keys: Optional[Tuple[Any, ...]] = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    if cache is None:
        from wake.core.visitor import get_extra

        cache = get_extra()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Create guard set specific to this function instance
        arguments_guard = set()

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            if cache_keys is None:
                keys = ("_cache", get_full_qualified_name(func))
            else:
                keys = cache_keys

            current = cache
            for key in keys:
                if key not in current:
                    current[key] = {}
                current = current[key]

            cache_key = (args, tuple(sorted(kwargs.items())))
            if cache_key in current:
                return current[cache_key]

            if cache_key in arguments_guard:
                return default

            with recursion_guard(arguments_guard, *args, **kwargs):
                ret = func(*args, **kwargs)
            current[cache_key] = ret
            return ret

        return wrapper

    return decorator
