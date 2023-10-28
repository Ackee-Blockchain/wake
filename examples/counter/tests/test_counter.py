from wake.testing import *
from wake.testing.fuzzing import *

from pytypes.contracts.Counter import Counter
from pytypes.contracts.Gateway import Gateway


def tx_callback(tx: TransactionAbc):
    print(tx.tx_hash)
    # console logs are not currently supported with Ganache and Hardhat
    print(tx.console_logs)
    print(tx.call_trace)

    # accessing tx.events may be expensive in some cases (when the transaction contains ambiguous events)
    # ambiguous events are events with the same selector (ABI signature) declared multiple times in the same project
    # it is recommended to use tx.events only when needed
    print(tx.events)

    # alternatively, it is possible to use tx.raw_events and parse the events manually
    # this requires deeper knowledge of how Solidity events are encoded
    print(tx.raw_events)

    for event in tx.raw_events:
        if len(event.topics) > 0 and event.topics[0] == Gateway.Relay.selector:
            # indexed arguments are stored in event.topics
            # non-indexed arguments are stored in event.data
            target = Abi.decode(["address"], event.topics[1])
            data, destination_chain = Abi.decode(["bytes", "string"], event.data)
            print(target, data, destination_chain)


# launch a development chain (Anvil, Hardhat or Ganache - depending on the configuration)
@default_chain.connect()
# or connect to a running chain
# @default_chain.connect("ws://localhost:8545")
def test_counter():
    # calls (pure and view functions) are executed using default_call_account
    # default_tx_account, default_estimate_account and default_access_list_account is unset by default
    default_chain.set_default_accounts(default_chain.accounts[0])

    # tx_callback is called after each transaction which is not configured with confirmations=0
    default_chain.tx_callback = tx_callback

    c = Counter.deploy(from_=random_account())
    print(c.address)

    # tx_callback will not be called for this transaction!!
    tx = c.increment(confirmations=0)
    # -1 = pending, 0 = failed, 1 = success
    print(tx.status)

    # performs implicit tx.wait()
    # raises tx.error if tx.status == 0
    print(tx.return_value)

    # execute multiple transactions in the same block
    # temporarily disable chain automine to achieve this
    # Ganache does not support disabling automine
    with default_chain.change_automine(False):
        # for each transaction, gas_limit can be specified with "max" as the default value
        # "max" uses default_chain.block_gas_limit as the gas limit
        # "auto" uses the estimated gas limit returned by the node
        # it is also possible to specify a custom gas limit in wei

        # applies to Hardhat only:
        #   gas_limit="auto" is needed in this case, otherwise tx1 would consume whole block gas limit

        # calling these functions without return_tx=True will cause a timeout error
        tx1 = c.increment(gas_limit="auto", confirmations=0)
        tx2 = c.decrement(gas_limit="auto", confirmations=0)

    # hardhat does not mine blocks automatically after automine re-enables
    default_chain.mine()
    tx1.wait()
    tx2.wait()

    assert tx1.status == tx2.status == 1
    assert tx1.block == tx2.block
    assert len(tx1.block.txs) == 2

    # it is possible to execute any function as a transaction (even pure and view functions)
    c.count(request_type="tx")

    # or as a call (does not modify the blockchain state)
    count = c.count()
    c.increment(request_type="call")
    assert c.count() == count
