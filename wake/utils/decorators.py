import weakref
from functools import lru_cache, wraps

from .context_managers import recursion_guard


def weak_self_lru_cache(maxsize=128, typed=False):
    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            weak_self = weakref.ref(self)

            @lru_cache(maxsize=maxsize, typed=typed)
            def cached_method(weak_self_ref, *args, **kwargs):
                self = weak_self_ref()
                if self is None:
                    raise ReferenceError("Weak reference to object no longer exists")
                return method(self, *args, **kwargs)

            return cached_method(weak_self, *args, **kwargs)

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
