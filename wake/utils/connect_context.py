class ConnectContext:
    def __init__(self, chain, accounts, chain_id, fork, hardfork):
        self.chain = chain
        self.accounts = accounts
        self.chain_id = chain_id
        self.fork = fork
        self.hardfork = hardfork

    def __enter__(self):
        self.chain._connect(self.accounts, self.chain_id, self.fork, self.hardfork)
        from wake.development.utils import reset_lru_cache
        reset_lru_cache()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        from bdb import BdbQuit

        from wake.development.globals import get_exception_handler

        try:
            if exc_type is not None and not isinstance(exc_value, BdbQuit):
                exception_handler = get_exception_handler()
                if exception_handler is not None:
                    exception_handler(exc_type, exc_value, traceback)
        finally:
            self.chain._disconnect()

    def __call__(self, fn):
        def wrapper(*args, **kwargs):
            with self:
                return fn(*args, **kwargs)

        return wrapper
