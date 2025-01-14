# Cross-Chain Message Passing

Example of testing cross-chain message passing between two chains.

```python
class CrossChainFuzzTest(FuzzTest):
    def pre_sequence(self) -> None:
        self.chain1 = Chain()
        self.chain2 = Chain()
        self.service1 = Service.deploy(chain=self.chain1)
        self.service2 = Service.deploy(chain=self.chain2)

    @flow()
    def flow_cross_chain_send(self) -> None:
        amount = random_int(0, 2**256 - 1)
        sender = random_account(chain=self.chain1)
        recipient = random_account(chain=self.chain2)

        # Send on source chain
        tx1 = self.service1.sendMessage(
            "chain2",
            recipient.address,
            amount,
            from_=sender
        )

        # Execute on destination chain
        self.service2.executeMessage(
            "chain1",
            sender.address,
            amount,
            tx1.events[0].messageHash,
            from_=random_account(chain=self.chain2)
        )
```