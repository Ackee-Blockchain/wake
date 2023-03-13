from woke.testing import *


@default_chain.connect()
def test_default():
    default_chain.set_default_accounts(default_chain.accounts[0])
