from woke.testing import *


@default_chain.connect()
def test_default():
    default_chain.default_tx_account = default_chain.accounts[0]
