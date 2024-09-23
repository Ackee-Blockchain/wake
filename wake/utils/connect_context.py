class ConnectContext:
    def __init__(self, chain, accounts, chain_id, fork, hardfork):
        self.chain = chain
        self.accounts = accounts
        self.chain_id = chain_id
        self.fork = fork
        self.hardfork = hardfork

    def __enter__(self):
        self.chain._connect(self.accounts, self.chain_id, self.fork, self.hardfork)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.chain._disconnect()

    def __call__(self, fn):
        def wrapper(*args, **kwargs):
            with self:
                return fn(*args, **kwargs)

        return wrapper
