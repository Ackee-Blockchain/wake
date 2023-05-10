from collections import defaultdict


# https://stackoverflow.com/a/2912455
class KeyedDefaultDict(defaultdict):
    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        else:
            ret = self[key] = self.default_factory(
                key  # pyright: ignore reportGeneralTypeIssues
            )
            return ret
