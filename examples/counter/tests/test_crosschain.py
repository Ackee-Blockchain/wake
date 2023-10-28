import logging
from typing import Callable

from wake.testing import *
from wake.testing.fuzzing import *

from pytypes.contracts.Counter import Counter
from pytypes.contracts.Gateway import Gateway


chain1 = Chain()
chain2 = Chain()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CrosschainTest(FuzzTest):
    gw1: Gateway
    gw2: Gateway
    c1: Counter
    c2: Counter
    # perform an operation on the counter on the first chain
    first_chain: bool

    def pre_sequence(self) -> None:
        # it is needed to specify the chain when deploying contracts
        # accounts must always belong to the chain that is being used
        self.gw1 = Gateway.deploy(from_=random_account(chain=chain1), chain=chain1)
        self.gw2 = Gateway.deploy(from_=random_account(chain=chain2), chain=chain2)
        self.c1 = Counter.deploy(from_=random_account(chain=chain1), chain=chain1)
        self.c2 = Counter.deploy(from_=random_account(chain=chain2), chain=chain2)

        # allow setting the count from gateways
        self.c1.addToWhitelist(self.gw1, from_=self.c1.owner())
        self.c2.addToWhitelist(self.gw2, from_=self.c2.owner())

    @flow()
    def flow_increment(self):
        c = self.c1 if self.first_chain else self.c2
        c.increment(from_=random_account(chain=c.chain))

    @flow()
    def flow_decrement(self):
        c = self.c1 if self.first_chain else self.c2
        with may_revert(Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW)) as e:
            c.decrement(from_=random_account(chain=c.chain))

        if e.value is not None:
            assert c.count() == 0

    @flow()
    def flow_set_count(self, count: uint):
        c = self.c1 if self.first_chain else self.c2
        c.setCount(count, from_=c.owner())
        self.count = count

    def pre_flow(self, flow: Callable) -> None:
        # perform the next flow on chain1 or chain2?
        self.first_chain = random_bool()

    def post_flow(self, flow: Callable) -> None:
        # set variables based on the chain that was used
        if self.first_chain:
            gw = self.gw1
            other_gw = self.gw2
            counter = self.c1
            other_counter = self.c2
            dest_chain = "chain2"
            logger.info(f"Relaying count after flow {flow.__name__}: {counter.count()} from chain 1 to chain 2")
        else:
            gw = self.gw2
            other_gw = self.gw1
            counter = self.c2
            other_counter = self.c1
            dest_chain = "chain1"
            logger.info(f"Relaying count after flow {flow.__name__}: {counter.count()} from chain 2 to chain 1")

        # encode the call to set the count on the other chain
        payload = Abi.encode_call(Counter.setCount, [counter.count()])
        tx = gw.relay(other_counter.address, payload, dest_chain, from_=random_account(chain=gw.chain))

        # relay the data (command) based on the events emitted by the gateway
        for event in tx.events:
            if isinstance(event, Gateway.Relay):
                other_gw.execute(event.target, event.data, from_=other_gw.owner())

    @invariant(period=10)
    def invariant_count(self):
        # check that the count is the same on both chains
        assert self.c1.count() == self.c2.count()


@chain1.connect()
@chain2.connect()
def test_crosschain():
    CrosschainTest().run(sequences_count=10, flows_count=100)
