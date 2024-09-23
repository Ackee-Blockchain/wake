class SnapshotRevertContext:
    def __init__(self, chain):
        self.chain = chain

    def __enter__(self):
        self.snapshot_id = self.chain.snapshot()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.chain.revert(self.snapshot_id)
