import functools

# inspired by https://stackoverflow.com/a/6849299


class lazy_property(object):
    """
    Lazy property decorator to be used on computational expensive properties.
    Works only on read-only properties.
    """

    def __init__(self, fget):
        self.fget = fget

        # copy the getter function's docstring and other attributes
        functools.update_wrapper(self, fget)

    def __get__(self, obj, cls):
        if obj is None:
            return self

        value = self.fget(obj)
        setattr(obj, self.fget.__name__, value)
        return value
