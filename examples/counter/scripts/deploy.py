from wake.deployment import *
from pytypes.contracts.Counter import Counter

# Use any node provider (Infura, Alchemy, etc.) or a local Geth node
NODE_URL = "YOUR_NODE_URL"


@default_chain.connect(NODE_URL)
def main():
    default_chain.set_default_accounts(Account.from_alias("deployment"))

    counter = Counter.deploy()
    counter.setCount(10)
