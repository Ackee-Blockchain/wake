use std::borrow::Borrow;
use std::collections::HashMap;

use lazy_static::lazy_static;
use pyo3::exceptions::PyNotImplementedError;
use pyo3::prelude::PyAnyMethods;
use pyo3::types::{PyBytes, PyDict, PyNone, PyString, PyTuple, PyType};
use pyo3::{exceptions::PyValueError, intern, IntoPyObjectExt};
use pyo3::prelude::*;
use regex::Regex;
use revm::primitives::Address as RevmAddress;

use crate::evm::prepare_tx_params;
use crate::pytypes::extract_abi_types;
use crate::tx::TransactionAbc;
use crate::utils::get_py_objects;
use crate::{
    account::Account,
    chain::Chain,
    enums::{AccessListEnum, AddressEnum, BlockEnum, GasLimitEnum, RequestTypeEnum, ValueEnum},
};

use crate::abi_old::Abi;

lazy_static! {
    static ref LIBRARY_PLACEHOLDER_REGEX: Regex = Regex::new(r"__\$[0-9a-fA-F]{34}\$__").unwrap();
}

#[pyclass(extends=Account, subclass)]
pub struct Contract {}

#[pymethods]
impl Contract {
    #[pyo3(signature = (address, chain=None))]
    #[new]
    pub(crate) fn new(
        py: Python,
        address: AddressEnum,
        chain: Option<Py<PyAny>>,
    ) -> PyResult<(Self, Account)> {
        let (final_address, final_chain) = match &address {
            AddressEnum::Account(account) => {
                let account_borrowed = account.borrow(py);
                let account_chain_py = account_borrowed.get_chain(py);
                let account_address = account_borrowed.address.borrow(py).0;
                match chain {
                    None => {
                        (account_address, account_chain_py)
                    }
                    Some(provided_chain) => {
                        if account_borrowed.chain.inner().is(&provided_chain) {
                            (account_address, provided_chain)
                        } else {
                            return Err(PyValueError::new_err(
                                "Account and chain must be from the same chain"
                            ));
                        }
                    }
                }
            }
            _ => {
                let resolved_chain = match chain {
                    Some(chain) => chain,
                    None => {
                        let py_objects = get_py_objects(py);
                        py_objects.wake_detect_default_chain.call0(py)?
                    }
                };
                (address.try_into()?, resolved_chain)
            }
        };

        let account = Account::from_revm_address(py, final_address, final_chain)?;
        Ok((Contract {}, account))
    }

    fn __str__<'py>(self_: PyRef<'_, Self>, py: Python<'py>) -> PyResult<Bound<'py, PyString>> {
        if let Some(label) = self_.as_ref().get_label(py)? {
            Ok(label)
        } else {
            let class_name = self_
                .borrow()
                .into_pyobject(py)?
                .getattr("__class__")?
                .getattr("__name__")?
                .extract::<String>()?;
            Ok(PyString::new(
                py,
                format!(
                    "{}({})",
                    class_name,
                    self_.as_ref().address.borrow(py).__str__()
                )
                .as_str(),
            ))
        }
    }

    #[pyo3(signature = (request_type, arguments, return_tx, return_type, from_, value, gas_limit, libraries, chain, gas_price, max_fee_per_gas, max_priority_fee_per_gas, access_list, authorization_list, block, confirmations, revert))]
    #[classmethod]
    pub(crate) fn _deploy(
        cls: &Bound<PyType>,
        py: Python,
        request_type: RequestTypeEnum,
        arguments: Vec<Bound<'_, PyAny>>,
        return_tx: bool,
        return_type: Bound<PyAny>,
        from_: Option<AddressEnum>,
        value: ValueEnum,
        gas_limit: Option<GasLimitEnum>,
        libraries: HashMap<Vec<u8>, Py<PyAny>>,
        chain: Option<Py<PyAny>>,
        gas_price: Option<ValueEnum>,
        max_fee_per_gas: Option<ValueEnum>,
        max_priority_fee_per_gas: Option<ValueEnum>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'_, PyDict>>>,
        block: Option<BlockEnum>,
        confirmations: Option<u64>,
        revert: bool,
    ) -> PyResult<PyObject> {
        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };

        let creation_code = cls.getattr(intern!(py, "_creation_code"))?;
        let mut creation_code = creation_code.extract::<&str>()?;
        let mut new_creation_code;

        let mut matches = LIBRARY_PLACEHOLDER_REGEX
            .find_iter(creation_code)
            .peekable();
        if matches.peek().is_some() {
            new_creation_code = String::with_capacity(creation_code.len());
            let mut last_end = 0;

            let try_get_lib = |lib_id: &[u8]| -> PyResult<Option<String>> {
                match chain.downcast_bound::<Chain>(py) {
                    Ok(chain) => Ok(chain
                        .borrow()
                        .deployed_libraries
                        .get(lib_id)
                        .map(|addr| addr.0.to_string())),
                    Err(_) => {
                        let item = chain
                            .bind(py)
                            .getattr(intern!(py, "_deployed_libraries"))?
                            .downcast_into::<PyDict>()?
                            .get_item(PyBytes::new(py, lib_id))?;

                        if let Some(item) = item {
                            Ok(Some(
                                item.get_item(-1)?
                                    .downcast::<Account>()?
                                    .borrow()
                                    .address
                                    .borrow(py)
                                    .0
                                    .to_string(),
                            ))
                        } else {
                            Ok(None)
                        }
                    }
                }
            };

            for m in matches {
                new_creation_code.push_str(&creation_code[last_end..m.start()]);
                let mut lib_id = [0u8; 17];
                hex::decode_to_slice(&creation_code[m.start() + 3..m.end() - 3], &mut lib_id)
                    .unwrap();

                let lib = libraries
                    .get(lib_id.as_slice())
                    .unwrap()
                    .downcast_bound::<PyTuple>(py)
                    .unwrap();
                let lib_addr = lib.get_item(0).unwrap().extract::<AddressEnum>();

                let lib_addr_str = if let Ok(lib_addr) = lib_addr {
                    TryInto::<RevmAddress>::try_into(lib_addr)?.to_string()
                } else if let Some(lib_addr) = try_get_lib(&lib_id)? {
                    lib_addr
                } else {
                    let lib_name = lib.get_item(1)?;
                    let lib_name = lib_name.extract::<&str>()?;
                    return Err(PyValueError::new_err(format!(
                        "Library {} not deployed",
                        lib_name
                    )));
                };

                new_creation_code.push_str(&lib_addr_str[2..]);
                last_end = m.end();
            }

            new_creation_code.push_str(&creation_code[last_end..]);
            creation_code = &new_creation_code;
        }

        Contract::_execute(
            cls,
            py,
            chain,
            request_type,
            &creation_code,
            arguments,
            return_tx,
            return_type,
            from_,
            None,
            value,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            authorization_list,
            block,
            confirmations,
            revert,
        )
    }

    #[pyo3(signature = (chain, request_type, data, arguments, return_tx, return_type, from_, to, value, gas_limit, gas_price, max_fee_per_gas, max_priority_fee_per_gas, access_list, authorization_list, block, confirmations, revert))]
    #[classmethod]
    pub(crate) fn _execute(
        cls: &Bound<PyType>,
        py: Python,
        chain: Py<PyAny>,
        request_type: RequestTypeEnum,
        data: &str,
        arguments: Vec<Bound<'_, PyAny>>,
        return_tx: bool,
        return_type: Bound<PyAny>, // does not always need to be PyType, may also be list[int] which is types.GenericAlias
        from_: Option<AddressEnum>,
        to: Option<AddressEnum>,
        value: ValueEnum,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<ValueEnum>,
        max_fee_per_gas: Option<ValueEnum>,
        max_priority_fee_per_gas: Option<ValueEnum>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'_, PyDict>>>,
        block: Option<BlockEnum>,
        confirmations: Option<u64>,
        revert: bool,
    ) -> PyResult<PyObject> {
        if request_type == RequestTypeEnum::Tx && block.is_some() {
            return Err(PyValueError::new_err(
                "block cannot be specified for contract transactions",
            ));
        }
        if request_type != RequestTypeEnum::Tx && return_tx {
            return Err(PyValueError::new_err(
                "return_tx cannot be specified for non-tx requests",
            ));
        }
        if request_type != RequestTypeEnum::Tx && confirmations.is_some() {
            return Err(PyValueError::new_err(
                "confirmations cannot be specified for non-tx requests",
            ));
        }
        if request_type == RequestTypeEnum::AccessList && access_list.is_some() {
            return Err(PyValueError::new_err(
                "access_list cannot be specified for access list requests",
            ));
        }
        if request_type != RequestTypeEnum::AccessList && request_type != RequestTypeEnum::Estimate && !revert {
            return Err(PyValueError::new_err(
                "revert may only be changed for access list and estimate requests",
            ));
        }

        let selector = hex::decode(data).unwrap();

        if let Ok(chain) = chain.downcast_bound::<Chain>(py) {
            let abi = if to.is_some() {
                Some(
                    cls.getattr(intern!(py, "_abi"))?
                        .downcast_into::<PyDict>()?
                        .get_item(PyBytes::new(py, &selector))?
                        .unwrap()
                        .downcast_into::<PyDict>()?,
                )
            } else {
                if cls.hasattr(intern!(py, "_abi"))? {
                    cls.getattr(intern!(py, "_abi"))?
                        .downcast_into::<PyDict>()?
                        .get_item(intern!(py, "constructor"))?
                        .and_then(|item| item.downcast_into::<PyDict>().ok())
                        .or_else(|| None)
                } else {
                    None
                }
            };

            let data = if let Some(ref abi) = abi {
                Abi::encode_with_selector(
                    py,
                    selector,
                    extract_abi_types(py, abi, intern!(py, "inputs"))?,
                    arguments,
                    get_py_objects(py),
                )?
            } else {
                selector
            };

            match request_type {
                RequestTypeEnum::Tx => {
                    let tx = Chain::transact(
                        chain,
                        py,
                        data,
                        to.map(|t| t.try_into()).transpose()?,
                        value.try_into()?,
                        from_,
                        gas_limit,
                        gas_price.map(|v| v.try_into()).transpose()?,
                        max_fee_per_gas.map(|v| v.try_into()).transpose()?,
                        max_priority_fee_per_gas.map(|v| v.try_into()).transpose()?,
                        access_list,
                        authorization_list,
                        return_type,
                        abi,
                    )?;

                    if return_tx {
                        Ok(tx.into_any())
                    } else {
                        TransactionAbc::return_value(tx.bind(py), py)
                    }
                }
                RequestTypeEnum::Call => Chain::call(
                    chain,
                    py,
                    data,
                    to.map(|t| t.try_into()).transpose()?,
                    value.try_into()?,
                    from_,
                    gas_limit,
                    gas_price.map(|v| v.try_into()).transpose()?,
                    max_fee_per_gas.map(|v| v.try_into()).transpose()?,
                    max_priority_fee_per_gas.map(|v| v.try_into()).transpose()?,
                    access_list,
                    authorization_list,
                    block.unwrap_or(BlockEnum::Latest),
                    Some(return_type),
                    abi,
                ),
                RequestTypeEnum::Estimate => Chain::estimate(
                    chain,
                    py,
                    data,
                    to.map(|t| t.try_into()).transpose()?,
                    value.try_into()?,
                    from_,
                    gas_limit,
                    gas_price.map(|v| v.try_into()).transpose()?,
                    max_fee_per_gas.map(|v| v.try_into()).transpose()?,
                    max_priority_fee_per_gas.map(|v| v.try_into()).transpose()?,
                    access_list,
                    authorization_list,
                    block.unwrap_or(BlockEnum::Pending),
                    revert,
                )?.into_py_any(py),
                RequestTypeEnum::AccessList => Chain::access_list(
                    chain,
                    py,
                    data,
                    to.map(|t| t.try_into()).transpose()?,
                    value.try_into()?,
                    from_,
                    gas_limit,
                    gas_price.map(|v| v.try_into()).transpose()?,
                    max_fee_per_gas.map(|v| v.try_into()).transpose()?,
                    max_priority_fee_per_gas.map(|v| v.try_into()).transpose()?,
                    authorization_list,
                    block.unwrap_or(BlockEnum::Pending),
                    revert,
                )?.into_py_any(py),
            }
        } else {
            if !revert {
                return Err(PyNotImplementedError::new_err(
                    "revert is not supported with non-revm chains",
                ));
            }

            let abi;
            if let Some(_) = &to {
                abi = cls
                    .getattr(intern!(py, "_abi"))?
                    .get_item(PyBytes::new(py, &selector))?;
            } else {
                abi = if let Ok(abi) = cls.getattr(intern!(py, "_abi")) {
                    abi.get_item(intern!(py, "constructor"))
                        .unwrap_or(PyNone::get(py).as_any().clone())
                } else {
                    PyNone::get(py).as_any().clone()
                };
            }

            let params = prepare_tx_params(
                py,
                chain.clone_ref(py),
                &selector,
                from_.clone(),
                to,
                value,
                gas_limit,
                gas_price,
                max_fee_per_gas,
                max_priority_fee_per_gas,
                access_list,
                authorization_list,
            )?;

            match request_type {
                RequestTypeEnum::Tx => chain.call_method(
                    py,
                    intern!(py, "_transact"),
                    (
                        abi,
                        arguments,
                        params,
                        return_tx,
                        return_type,
                        confirmations,
                        from_,
                    ),
                    None,
                ),
                RequestTypeEnum::Call => chain.call_method(
                    py,
                    intern!(py, "_call"),
                    (
                        abi,
                        arguments,
                        params,
                        return_type,
                        block.unwrap_or(BlockEnum::Latest),
                    ),
                    None,
                ),
                RequestTypeEnum::Estimate => chain.call_method(
                    py,
                    intern!(py, "_estimate"),
                    (abi, arguments, params, block.unwrap_or(BlockEnum::Pending)),
                    None,
                ),
                RequestTypeEnum::AccessList => chain.call_method(
                    py,
                    intern!(py, "_access_list"),
                    (abi, arguments, params, block.unwrap_or(BlockEnum::Pending)),
                    None,
                ),
            }
        }
    }

    #[classmethod]
    pub(crate) fn _get_creation_code<'py>(
        cls: &Bound<'py, PyType>,
        py: Python<'py>,
        libraries: HashMap<Vec<u8>, Py<PyAny>>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let creation_code = cls.getattr(intern!(py, "_creation_code"))?;
        let mut creation_code = creation_code.extract::<&str>()?;
        let mut new_creation_code;

        let mut matches = LIBRARY_PLACEHOLDER_REGEX
            .find_iter(creation_code)
            .peekable();
        if matches.peek().is_some() {
            new_creation_code = String::with_capacity(creation_code.len());
            let mut last_end = 0;

            for m in matches {
                new_creation_code.push_str(&creation_code[last_end..m.start()]);
                let mut lib_id = [0u8; 17];
                hex::decode_to_slice(&creation_code[m.start() + 3..m.end() - 3], &mut lib_id)
                    .unwrap();

                let lib = libraries
                    .get(lib_id.as_slice())
                    .unwrap()
                    .downcast_bound::<PyTuple>(py)
                    .unwrap();
                let lib_addr = lib.get_item(0).unwrap().extract::<AddressEnum>();

                let lib_addr_str = if let Ok(lib_addr) = lib_addr {
                    TryInto::<RevmAddress>::try_into(lib_addr)?.to_string()
                } else {
                    let lib_name = lib.get_item(1)?;
                    let lib_name = lib_name.extract::<&str>()?;
                    return Err(PyValueError::new_err(format!(
                        "Address of library {} required to generate creation code",
                        lib_name
                    )));
                };

                new_creation_code.push_str(&lib_addr_str[2..]);
                last_end = m.end();
            }

            new_creation_code.push_str(&creation_code[last_end..]);
            creation_code = &new_creation_code;
        }

        Ok(PyBytes::new(py, &hex::decode(creation_code).unwrap()))
    }
}
