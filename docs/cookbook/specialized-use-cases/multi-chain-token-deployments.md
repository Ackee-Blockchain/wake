# Multi-Chain Token Deployments

Example of deploying contracts on multiple chains.

```python
@flow()
def flow_deploy_remote_tokens(self) -> None:
    num_chains = random_int(1, 5)
    chains = [f"chain{i}" for i in range(num_chains)]
    gas_values = [random_int(1000, 10000) for _ in range(num_chains)]
    mgr_types = [random_int(0, 3) for _ in range(num_chains)]

    params = []
    for i in range(num_chains):
        if mgr_types[i] == 2:  # Canonical
            params.append(self._get_canonical_params())
        else:
            params.append(self._get_standard_params())

    with may_revert() as e:
        self.service.deployRemoteCustomTokenManagers(
            random_bytes(32),  # salt
            chains,
            mgr_types,
            params,
            gas_values,
            value=sum(gas_values),
            from_=random_account()
        )

    if len(set(chains)) != len(chains):
        assert e.value == self.service.DuplicateChain()
```