# Migrating from Wake 4.x

In version 5.0.0, a new testing EVM execution engine based on [revm](https://github.com/bluealloy/revm) was introduced. This brings several breaking changes as well as new features.

## Breaking changes

### Renamed symbols

- The `default_chain` alias no longer exists, use `chain` instead
- `TransactionRevertedError` was renamed to `RevertError`
- `UnknownTransactionRevertedError` was renamed to `UnknownRevertError`

### Dropped development chain support

[Ganache](https://archive.trufflesuite.com/ganache/) is no longer supported. Hardhat's development chain support is considered deprecated.

### `bytearray` replaced with `bytes`

All pytypes functions and dataclass attributes that represent Solidity `bytes` are now represented by Python `bytes` instead of `bytearray`. This affects:

- Low-level `Account.call` function
- Return value of `Account.transact`
- `random_bytes` function
- Other similar API functions

### Configured accounts must be re-imported

All accounts configured through `wake accounts` CLI commands must be manually deleted and imported again:

1. Remove existing accounts: `wake accounts remove <alias>`
2. Import accounts again: `wake accounts import <alias>`

### Removed `type` kwarg from functions interacting with contracts

Transaction type can no longer be specified through the `type` keyword argument. Instead, the transaction type is derived automatically from the passed arguments.

## New features

### [revm](https://github.com/bluealloy/revm)-based execution backend

The new execution backend with amazing performance can be used by setting the following in wake.toml:

```toml
[testing]
cmd = "revm"
```

**Note:** There is no JSON-RPC available for this testing backend.

### Support for [EIP-7702](https://eips.ethereum.org/EIPS/eip-7702) transactions

A new function was implemented to sign [EIP-7702](https://eips.ethereum.org/EIPS/eip-7702) authorizations:

```python
Account.sign_authorization(
    address: Account | Address | int | str,
    chain_id: int | None = None,
    nonce: int | None = None
) -> SignedAuthorization
```

All contract interaction functions now support an `authorization_list: Optional[List[SignedAuthorization]]` keyword argument accepting an optional list of such signed authorizations.

### `ExternalEvent` and `ExternalError` API

Events and errors originating in forked contracts are now resolved into specialized class instances when possible (i.e., when ABI is available either on Sourcify or Etherscan with an API key set).

This feature is currently only supported with `revm` testing chain.

**`ExternalEvent` class:**

- Provides `_event_full_name` attribute with the canonical name of the event
- Other attributes named according to the event parameters in ABI

**`ExternalError` class:**

- Provides `_error_full_name` attribute with the canonical name of the error
- Other attributes named according to the error parameters in ABI

### Support for Trezor hardware wallets

An `Account` instance may be created using a new function:

```python
Account.from_trezor(
    path: str = "m/44'/60'/0'/0/0",
    chain: Optional[Chain] = None
) -> Account
```

### Request access list for reverting transactions

API calls requesting [EIP-2930](https://eips.ethereum.org/EIPS/eip-2930) access lists now support:

- New `revert_on_failure` keyword argument (set to `True` by default)
- Setting it to `False` allows requesting an access list even for failing transactions

### Support for Linux ARM

ARM Linux is now supported through 3rd party [nikitastupin/solc](https://github.com/nikitastupin/solc) repository containing solc binaries for this platform.

### `pytypes_resolver` for enforcing event and error resolution

It is possible to override the resolution of events and errors for any Account using `pytypes_resolver`.

```python
usdt = Account("0xdAC17F958D2ee523a2206206994597C13D831ec7")
usdt.pytypes_resolver = IUSDT
```

where `IUSDT` is a Solidity interface generated into pytypes.

This feature can be used to enforce user-friendly resolution of "external contracts" (e.g. forked contracts, low-level deployed contracts with init code) and in cases when implicit resolution doesn't work correctly.

`pytypes_resolver` must always be assigned to the Account that performs the event emit (LOGn instruction) or performs the revert. In a proxy-implementation setup, `pytypes_resolver` must be set on the implementation contract to correctly resolve events and errors originating from the code of the implementation contract. It may be set for the proxy as well if it defines its own events or errors.

This feature is currently only supported with `revm` testing chain.

### [EIP-712](https://eips.ethereum.org/EIPS/eip-712) encoded data for all structs

All instances of structs generated in pytypes now offer two helper functions for easier debugging of signatures provided by `Account.sign_structured`:

- `.encode_eip712_type()` returning the [EIP-712](https://eips.ethereum.org/EIPS/eip-712) encoded type of the struct as a string
- `.encode_eip712_data()` returning the [EIP-712](https://eips.ethereum.org/EIPS/eip-712) encoded data of the struct as bytes
