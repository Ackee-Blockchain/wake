from wake.testing import *
from wake.testing.fuzzing import *

from pytypes.contracts.Counter import Counter


class CounterTest(FuzzTest):
    _counter: Counter
    _count: int
    _owner: Account

    # executed before each sequence
    def pre_sequence(self) -> None:
        self._owner = random_account()
        self._counter = Counter.deploy(from_=self._owner)
        self._count = 0
        assert self._counter.owner() == self._owner.address
        assert self._counter.count() == 0

    @flow()
    def flow_increment(self):
        self._counter.increment(from_=random_account())
        self._count += 1

    @flow()
    def flow_decrement(self):
        # fails if count is 0
        self._counter.decrement(from_=random_account())
        self._count -= 1

    # check the invariant every 10 flows (starting after the 1st flow)
    @invariant(period=10)
    def invariant_count(self):
        assert self._counter.count() == self._count


@default_chain.connect()
def test_counter_fuzz():
    # run 10 independent test sequences (the chain is reset between each sequence) with 100 flows in each
    CounterTest().run(sequences_count=20, flows_count=100)
