# Permit Functions with EIP712 Signatures

Example of testing a permit function with EIP712 signatures.
```python
@dataclass
class Permit:
    owner: Address
    spender: Address
    value: uint256
    nonce: uint256
    deadline: uint256

@flow()
def flow_permit(self) -> None:
    owner = random_account()
    spender = random_account()
    value = random_int(0, 2**256 - 1)

    permit = Permit(
        owner.address,
        spender.address,
        value,
        self.token.nonces(owner),
        self.token.chain.blocks["latest"].timestamp + 100_000
    )

    signature = owner.sign_structured(permit, Eip712Domain(
        name=self.token.name(),
        version="1",
        chainId=self.token.chain.chain_id,
        verifyingContract=self.token.address,
    ))

    with may_revert() as e:
        self.token.permit(
            permit.owner,
            permit.spender,
            permit.value,
            permit.deadline,
            signature[64],  # v
            signature[:32], # r
            signature[32:64], # s
            from_=random_account()
        )
```