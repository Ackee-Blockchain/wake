class AutomineContext:
    def __init__(self, chain, automine):
        self.chain = chain
        self.automine = automine

    def __enter__(self):
        self.old_automine = self.chain.automine
        self.chain.automine = self.automine
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.chain.automine = self.old_automine

    def __call__(self, fn):
        def wrapper(*args, **kwargs):
            with self:
                return fn(*args, **kwargs)

        return wrapper
