class SnapshotRevertContext:
    def __init__(self, chain):
        self.chain = chain

    def __enter__(self):
        self.snapshot_id = self.chain.snapshot()
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
            self.chain.revert(self.snapshot_id)
