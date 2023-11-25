from functools import lru_cache, wraps

from .context_managers import recursion_guard


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
