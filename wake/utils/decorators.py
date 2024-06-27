import weakref
from functools import lru_cache, wraps

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


def cached_return_on_recursion(default, max_size=128):
    arguments_guard = set()

    def decorator(func):
        func = lru_cache(max_size)(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if (args, tuple(sorted((kwargs.items())))) in arguments_guard:
                return default
            with recursion_guard(arguments_guard, *args, **kwargs):
                return func(*args, **kwargs)

        return wrapper

    return decorator
