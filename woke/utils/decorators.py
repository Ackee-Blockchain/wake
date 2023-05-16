from functools import wraps

from .context_managers import recursion_guard


def return_on_recursion(default):
    arguments = set()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if (args, tuple(sorted(kwargs.items()))) in arguments:
                return default
            with recursion_guard(arguments, *args, **kwargs):
                return func(*args, **kwargs)

        return wrapper

    return decorator
