use std::collections::HashMap;

use alloy::{
    eips::eip7702::SignedAuthorization,
    hex::FromHexError,
    rpc::types::{AccessList, Authorization},
};
use num_bigint::BigUint;
use pyo3::{
    exceptions::{PyRuntimeError, PyValueError},
    intern,
    prelude::*,
    types::{PyBytes, PyDict, PyList, PyString}, IntoPyObjectExt,
};
use revm::{
    context::{
        transaction::AccessListItem,
        TxEnv,
    },
    primitives::{Address, TxKind, B256, U256},
};

use crate::{
    enums::{AccessListEnum, AddressEnum, GasLimitEnum, ValueEnum},
    utils::big_uint_to_u256,
};

pub(crate) fn prepare_tx_env(
    py: Python,
    tx_env: &mut TxEnv,
    block_gas_limit: u64,
    data: Vec<u8>,
    to: Option<Address>,
    value: U256,
    from: AddressEnum,
    gas_limit: Option<GasLimitEnum>,
    gas_price: Option<u128>,
    max_fee_per_gas: Option<U256>,
    max_priority_fee_per_gas: Option<U256>,
    access_list: Option<AccessListEnum>,
    authorization_list: Option<Vec<Bound<'_, PyDict>>>,
) -> PyResult<()> {
    tx_env.caller = from.try_into()?;

    tx_env.gas_limit = match gas_limit {
        Some(GasLimitEnum::Int(v)) => v.try_into().unwrap(),
        Some(GasLimitEnum::Max) => block_gas_limit, // TODO use max block gas limit or current block gas limit?
        Some(GasLimitEnum::Auto) => todo!(),
        None => block_gas_limit,
    };

    tx_env.gas_price = gas_price.unwrap_or(0);
    tx_env.kind = to.map(TxKind::Call).unwrap_or(TxKind::Create);
    tx_env.value = value;
    tx_env.data = data.into();

    if let Some(_) = max_fee_per_gas {
        todo!()
    }

    if let Some(_) = max_priority_fee_per_gas {
        todo!()
    }

    tx_env.access_list = match access_list {
        Some(AccessListEnum::Dictionary(dict)) => {
            let mut access_list = Vec::with_capacity(dict.len());
            for (address, storage_keys) in dict {
                access_list.push(AccessListItem {
                    address: address.try_into()?,
                    storage_keys: storage_keys
                        .into_iter()
                        .map(|key| B256::left_padding_from(&key.to_bytes_be()))
                        .collect(),
                });
            }
            access_list.into()
        }
        Some(AccessListEnum::Auto) => todo!(),
        None => AccessList::default(),
    };

    tx_env.authorization_list =
        Vec::with_capacity(authorization_list.as_ref().map_or(0, |l| l.len()));
    if let Some(authorization_list) = authorization_list {
        for auth in authorization_list {
            let address = match auth.get_item("address")? {
                Some(address) => address.extract::<String>()?,
                None => return Err(PyValueError::new_err("address is required")),
            };
            let chain_id = match auth.get_item(intern!(py, "chainId"))? {
                Some(chain_id) => chain_id.extract::<BigUint>()?,
                None => return Err(PyValueError::new_err("chainId is required")),
            };
            let nonce = match auth.get_item(intern!(py, "nonce"))? {
                Some(nonce) => nonce.extract::<u64>()?,
                None => return Err(PyValueError::new_err("nonce is required")),
            };
            let r = match auth.get_item(intern!(py, "r"))? {
                Some(r) => r.extract::<BigUint>()?,
                None => return Err(PyValueError::new_err("r is required")),
            };
            let s = match auth.get_item(intern!(py, "s"))? {
                Some(s) => s.extract::<BigUint>()?,
                None => return Err(PyValueError::new_err("s is required")),
            };
            let y_parity = match auth.get_item(intern!(py, "yParity"))? {
                Some(y_parity) => y_parity.extract::<u8>()?,
                None => return Err(PyValueError::new_err("yParity is required")),
            };

            tx_env
                .authorization_list
                .push(SignedAuthorization::new_unchecked(
                    Authorization {
                        chain_id: big_uint_to_u256(chain_id),
                        address: address
                            .parse()
                            .map_err(|e: FromHexError| PyValueError::new_err(e.to_string()))?,
                        nonce,
                    },
                    y_parity,
                    big_uint_to_u256(r),
                    big_uint_to_u256(s),
                ));
        }
    }

    tx_env
        .derive_tx_type()
        .map_err(|e| PyErr::new::<PyRuntimeError, _>(format!("{:?}", e)))?;

    Ok(())
}

pub(crate) fn prepare_tx_params<'py, 'a>(
    py: Python<'py>,
    chain: Py<PyAny>,
    data: &[u8],
    from_: Option<AddressEnum>,
    to: Option<AddressEnum>,
    value: ValueEnum,
    gas_limit: Option<GasLimitEnum>,
    gas_price: Option<ValueEnum>,
    max_fee_per_gas: Option<ValueEnum>,
    max_priority_fee_per_gas: Option<ValueEnum>,
    access_list: Option<AccessListEnum>,
    authorization_list: Option<Vec<Bound<'py, PyDict>>>,
) -> PyResult<HashMap<&'a str, Bound<'py, PyAny>>> {
    let mut params = HashMap::new();
    if let Some(from) = from_ {
        match from {
            AddressEnum::Account(ref from) => {
                if !from.bind(py).borrow().chain.inner().is(&chain) {
                    return Err(PyValueError::new_err(format!(
                        "Account 'from' {} is not on the same chain as the contract",
                        from.borrow(py).address.borrow(py).0
                    )));
                }
            }
            _ => {}
        };
        params.insert(
            "from",
            PyString::new(py, &TryInto::<Address>::try_into(from)?.to_string()).into_any(),
        );
    }

    params.insert(
        "value",
        TryInto::<BigUint>::try_into(value)?.into_bound_py_any(py)?,
    );
    params.insert("data", PyBytes::new(py, data).into_any());

    if let Some(gas_limit) = gas_limit {
        match gas_limit {
            GasLimitEnum::Max => params.insert(
                "gas",
                chain.bind(py).getattr(intern!(py, "block_gas_limit"))?,
            ),
            GasLimitEnum::Auto => params.insert("gas", PyString::new(py, "auto").into_any()),
            GasLimitEnum::Int(gas_limit) => {
                params.insert("gas", gas_limit.into_bound_py_any(py)?)
            }
        };
    }

    if let Some(to) = to {
        match to {
            AddressEnum::Account(ref to) => {
                if !to.bind(py).borrow().chain.inner().is(&chain) {
                    return Err(PyValueError::new_err(format!(
                        "Account 'to' {} is not on the same chain as the contract",
                        to.borrow(py).address.borrow(py).0
                    )));
                }
            }
            _ => {}
        };
        params.insert(
            "to",
            PyString::new(py, &TryInto::<Address>::try_into(to)?.to_string()).into_any(),
        );
    }

    if let Some(gas_price) = gas_price {
        params.insert(
            "gasPrice",
            TryInto::<BigUint>::try_into(gas_price)?.into_bound_py_any(py)?,
        );
    }

    if let Some(access_list) = access_list {
        match access_list {
            AccessListEnum::Auto => {
                params.insert("accessList", PyString::new(py, "auto").into_any());
            }
            AccessListEnum::Dictionary(dict) => {
                let access_list = PyList::new(
                    py,
                    dict.into_iter()
                        .map(|(key, value)| {
                            let key: Address = key.try_into()?;
                            let entry = PyDict::new(py);
                            entry.set_item("address", key.to_string())?;
                            entry.set_item("storageKeys", value)?;
                            Ok(entry)
                        })
                        .collect::<PyResult<Vec<_>>>()?,
                )?;
                params.insert("accessList", access_list.into_any());
            }
        };
    }

    if let Some(max_fee_per_gas) = max_fee_per_gas {
        params.insert(
            "maxFeePerGas",
            TryInto::<BigUint>::try_into(max_fee_per_gas)?
                .into_bound_py_any(py)?,
        );
    }

    if let Some(max_priority_fee_per_gas) = max_priority_fee_per_gas {
        params.insert(
            "maxPriorityFeePerGas",
            TryInto::<BigUint>::try_into(max_priority_fee_per_gas)?
                .into_bound_py_any(py)?,
        );
    }

    if let Some(authorization_list) = authorization_list {
        let list = PyList::new(py, authorization_list.into_iter())?;
        params.insert("authorizationList", list.into_any());
    }

    Ok(params)
}
