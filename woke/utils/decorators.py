from functools import wraps
from .context_managers import recursion_guard


def return_on_recursion(default):
    arguments = set()

    def decorator(func):

        @wraps(func)
        def wrapper(*args, **kwargs):
            if len(kwargs) > 0:
                raise ValueError("kwargs not supported")
            if args in arguments:
                return default
            with recursion_guard(arguments, *args):
                return func(*args, **kwargs)
        return wrapper
    return decorator
