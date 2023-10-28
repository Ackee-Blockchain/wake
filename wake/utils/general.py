import functools
import inspect


# credits: https://stackoverflow.com/questions/3589311/get-defining-class-of-unbound-method-object-in-python-3/25959545#25959545
def get_class_that_defined_method(meth):
    if isinstance(meth, functools.partial):
        return get_class_that_defined_method(meth.func)
    if inspect.ismethod(meth):
        for c in inspect.getmro(meth.__self__.__class__):
            if meth.__name__ in c.__dict__:
                return c
        meth = getattr(meth, "__func__", meth)  # fallback to __qualname__ parsing
    if inspect.isfunction(meth):
        c = getattr(
            inspect.getmodule(meth),
            meth.__qualname__.split(".<locals>", 1)[0].rsplit(".", 1)[0],
            None,
        )
        if isinstance(c, type):
            return c
    return getattr(meth, "__objclass__", None)  # handle special descriptor objects
