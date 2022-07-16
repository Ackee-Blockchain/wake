import IPython

from woke.fuzzer import Campaign
from woke.fuzzer.decorators import (
    flow,
    ignore,
    invariant,
    max_times,
    precondition,
    weight,
)
from woke.fuzzer.random import (
    random_account,
    random_bool,
    random_bytes,
    random_int,
    random_string,
)


class TestingSequence:
    def __init__(self):
        pass
        # sequence setup code goes here
        # this setup is run at the beginning of each sequence

        # for example, contracts can be deployed here (in case they are not deployed in `test_example` function)

    @flow
    def flow_test_example(self):
        pass
        # flow code goes here
        # at least one transaction should be performed in this flow
        # assertions can be also made here

    @invariant
    def invariant_test_example(self):
        pass
        # invariant code goes here


# custom pytest fixtures are not supported
# but it is possible to use brownie's predefined fixtures (see https://eth-brownie.readthedocs.io/en/stable/tests-pytest-fixtures.html)
def test_example():
    # optional setup code goes here
    # any transactions performed here will be common to all testing sequences

    # typically, brownie contract objects will be passed to the `TestingSequence` constructor
    campaign = Campaign(lambda: TestingSequence())

    # the first argument specifies the number of sequences (i.e. the number of independent fuzzer runs)
    # the second argument specifies the number of flows applied in each sequence
    campaign.run(1000, 400)
