import weakref
from functools import lru_cache, wraps
from typing import Any, Tuple

from .context_managers import recursion_guard


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


def dict_cache(cache: dict, cache_keys: Tuple[Any, ...]):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current = cache
            for key in cache_keys:
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


def return_on_recursion(default):
    arguments_guard = set()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if (args, tuple(sorted(kwargs.items()))) in arguments_guard:
                return default
            with recursion_guard(arguments_guard, *args, **kwargs):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def dict_cached_return_on_recursion(default, cache: dict, cache_keys: Tuple[Any, ...]):
    arguments_guard = set()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current = cache
            for key in cache_keys:
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
