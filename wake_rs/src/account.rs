use alloy::consensus::SignableTransaction;
use alloy::dyn_abi::TypedData;
use alloy::primitives::keccak256;
use alloy::rpc::types::Authorization;
use alloy::signers::k256::ecdsa::SigningKey;
use alloy::signers::local::LocalSigner;
use num_bigint::BigUint;
use pyo3::basic::CompareOp;
use pyo3::exceptions::{PyNotImplementedError, PyValueError};
use pyo3::types::{PyByteArray, PyBytes, PyDict, PyNone, PyString, PyType};
use pyo3::{intern, prelude::*, IntoPyObjectExt, PyTypeInfo};
use revm::context::ContextTr;
use revm::primitives::{Address as RevmAddress, U256};
use revm::Database;
use std::hash::{DefaultHasher, Hash, Hasher};
use std::path::PathBuf;

use crate::address::Address;
use crate::chain::{Chain, CustomEvm};
use crate::core::signer::{Signer, SIGNERS};
use crate::eip712::py_to_eip712;
use crate::enums::{
    AccessListEnum, AddressEnum, BlockEnum, GasLimitEnum, ValueEnum,
};
use crate::evm::prepare_tx_params;
use crate::globals::TOKIO_RUNTIME;
use crate::utils::{get_py_objects, tx_params_to_typed_tx};

pub enum ChainWrapper {
    Native(Py<Chain>),
    Python(Py<PyAny>),
}

impl ChainWrapper {
    pub fn inner(&self) -> &Py<PyAny> {
        match self {
            ChainWrapper::Native(chain) => chain.as_any(),
            ChainWrapper::Python(chain) => chain,
        }
    }
}

#[pyclass(subclass)]
pub struct Account {
    #[pyo3(get)]
    pub address: Py<Address>,
    pub chain: ChainWrapper,
}

impl Account {
    /*
    fn with_evm<F, R>(&self, py: Python, f: F) -> R
    where
        F: FnOnce(&mut MutexGuard<'_, Evm<'static, (), DB>>) -> R + Send,
        R: Send,
    {
        let mut chain = self.chain.borrow_mut(py);
        let e = chain.evm.take().expect("Not connected");
        let e_locked = e.lock().unwrap();
        let mut wrapped = SendWrapper::new(e_locked);

        drop(chain);

        let result = py.allow_threads(move || {
            f(&mut *wrapped)
        });

        chain = self.chain.borrow_mut(py);
        chain.evm = Some(e);
        result
    }
    */

    fn with_evm_context<F, R>(&self, py: Python, chain: &Py<Chain>, f: F) -> PyResult<R>
    where
        F: FnOnce(&mut CustomEvm) -> R + Send,
        R: Send,
    {
        let mut chain = chain.borrow_mut(py);
        let evm = chain.get_evm_mut()?;

        Ok(py.allow_threads(|| f(evm)))
    }

    pub(crate) fn from_address(py: Python, address: Address, chain: Py<PyAny>) -> PyResult<Self> {
        Ok(Self {
            address: Py::new(py, address)?,
            chain: if let Ok(chain) = chain.downcast_bound::<Chain>(py) {
                ChainWrapper::Native(chain.clone().unbind())
            } else {
                ChainWrapper::Python(chain)
            },
        })
    }

    pub(crate) fn from_revm_address(
        py: Python,
        address: RevmAddress,
        chain: Py<PyAny>,
    ) -> PyResult<Self> {
        Ok(Self {
            address: Py::new(py, Address::from(address))?,
            chain: if let Ok(chain) = chain.downcast_bound::<Chain>(py) {
                ChainWrapper::Native(chain.clone().unbind())
            } else {
                ChainWrapper::Python(chain)
            },
        })
    }

    pub(crate) fn from_address_native(
        py: Python,
        address: RevmAddress,
        chain: Py<Chain>,
    ) -> PyResult<Self> {
        Ok(Self {
            address: Py::new(py, Address::from(address))?,
            chain: ChainWrapper::Native(chain),
        })
    }
}

#[pymethods]
impl Account {
    #[new]
    #[pyo3(signature = (address, chain=None))]
    pub(crate) fn new(
        py: Python,
        address: AddressEnum,
        chain: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };
        Ok(Self::from_revm_address(py, address.try_into()?, chain)?)
    }

    #[classmethod]
    #[pyo3(name = "new", signature = (chain=None, extra_entropy=None))]
    fn new_py<'py>(
        _cls: &Bound<'py, PyType>,
        py: Python<'py>,
        chain: Option<Py<PyAny>>,
        mut extra_entropy: Option<Bound<'py, PyBytes>>,
    ) -> PyResult<Self> {
        let py_objects = get_py_objects(py);
        let chain = match chain {
            Some(chain) => chain,
            None => py_objects.wake_detect_default_chain.call0(py)?,
        };
        let pk = if let Ok(_) = chain.downcast_bound::<Chain>(py) {
            let mut pk = py_objects
                .wake_random
                .call_method1(py, intern!(py, "getrandbits"), (256,))?
                .extract::<BigUint>(py)?
                .to_bytes_le();

            if let Some(extra_entropy) = extra_entropy {
                pk.extend_from_slice(&extra_entropy.as_bytes());
                pk = keccak256(&pk).to_vec();
            }
            pk
        } else {
            if extra_entropy.is_none() {
                extra_entropy = Some(PyBytes::new(py, &[]));
            }
            chain
                .call_method1(py, intern!(py, "_new_private_key"), (extra_entropy,))?
                .downcast_bound::<PyBytes>(py)?
                .as_bytes()
                .to_vec()
        };

        Self::from_private_key(py, &pk, Some(chain))
    }

    pub(crate) fn __str__<'py>(slf: &Bound<Self>, py: Python<'py>) -> PyResult<Bound<'py, PyString>> {
        match slf.borrow().get_label(py)? {
            Some(label) => Ok(label),
            None => Ok(PyString::new(
                py,
                format!("{}({})", slf.get_type().name()?, slf.borrow().address.borrow(py).__str__()).as_str(),
            )),
        }
    }

    fn __repr__<'py>(slf: &Bound<Self>, py: Python<'py>) -> PyResult<Bound<'py, PyString>> {
        Self::__str__(slf, py)
    }

    pub fn __richcmp__(&self, py: Python, other: &Self, op: CompareOp) -> PyResult<bool> {
        match op {
            CompareOp::Eq | CompareOp::Ne => Ok(self
                .address
                .borrow(py)
                .__richcmp__(&other.address.borrow(py), op)
                && self.chain.inner().is(other.chain.inner())),
            _ => {
                if !self.chain.inner().is(other.chain.inner()) {
                    return Err(PyValueError::new_err(
                        "Cannot compare accounts from different chains",
                    ));
                }

                Ok(self
                    .address
                    .borrow(py)
                    .__richcmp__(&other.address.borrow(py), op))
            }
        }
    }

    fn __hash__(&self, py: Python) -> PyResult<u64> {
        let mut hasher = DefaultHasher::new();

        self.address.borrow(py).0.hash(&mut hasher);
        hasher.write_isize(self.chain.inner().bind(py).hash()?);

        Ok(hasher.finish())
    }

    #[getter]
    fn get_private_key<'py>(&self, py: Python<'py>) -> Option<Bound<'py, PyBytes>> {
        self.address.borrow(py).get_private_key(py)
    }

    #[getter]
    fn get_chain(&self, py: Python) -> Py<PyAny> {
        match &self.chain {
            ChainWrapper::Native(chain) => chain.as_any().clone_ref(py),
            ChainWrapper::Python(chain) => chain.clone_ref(py),
        }
    }

    #[getter]
    pub(crate) fn get_label<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyString>>> {
        match &self.chain {
            ChainWrapper::Native(chain) => {
                let labels = &chain.borrow(py).labels;

                match labels.get(&self.address.borrow(py).0) {
                    Some(label) => Ok(Some(PyString::new(py, label))),
                    None => Ok(None),
                }
            }
            ChainWrapper::Python(chain) => {
                let labels = chain
                    .bind(py)
                    .getattr(intern!(py, "_labels"))?
                    .downcast_into::<PyDict>()?;
                match labels.get_item(self.address.clone_ref(py))? {
                    Some(label) => Ok(Some(label.downcast_into::<PyString>()?)),
                    None => Ok(None),
                }
            }
        }
    }

    #[setter]
    fn set_label<'py>(&self, py: Python<'py>, label: Option<&str>) -> PyResult<()> {
        match &self.chain {
            ChainWrapper::Native(chain) => {
                let labels = &mut chain.borrow_mut(py).labels;

                match label {
                    Some(label) => {
                        labels.insert(self.address.borrow(py).0, label.to_string());
                    }
                    None => {
                        labels.remove(&self.address.borrow(py).0);
                    }
                }
            }
            ChainWrapper::Python(chain) => {
                let labels = chain
                    .bind(py)
                    .getattr(intern!(py, "_labels"))?
                    .downcast_into::<PyDict>()?;
                if let Some(label) = label {
                    labels.set_item(self.address.clone_ref(py), PyString::new(py, label))?;
                } else {
                    labels.del_item(self.address.clone_ref(py))?;
                }
            }
        }
        Ok(())
    }

    #[getter]
    fn get_balance<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let balance = match &self.chain {
            ChainWrapper::Native(chain) => {
                let addr = self.address.borrow(py).0;
                self.with_evm_context(py, chain, |evm| -> PyResult<BigUint> {
                    Ok(evm.db().basic(addr)?.map_or(BigUint::ZERO, |a| {
                        BigUint::from_bytes_le(a.balance.as_le_slice())
                    }))
                })?
            }
            ChainWrapper::Python(chain) => chain
                .bind(py)
                .getattr(intern!(py, "chain_interface"))?
                .call_method1(
                    intern!(py, "get_balance"),
                    (self.address.borrow(py).__str__(),),
                )?
                .extract::<BigUint>(),
        }?;

        let py_objects = get_py_objects(py);
        py_objects.wake_wei.bind(py).call1((balance,))
    }

    #[setter]
    fn set_balance(&self, py: Python, value: ValueEnum) -> PyResult<()> {
        match &self.chain {
            ChainWrapper::Native(chain) => {
                let addr = self.address.borrow(py).0;
                let value: U256 = value.try_into()?;
                self.with_evm_context(py, chain, |evm| -> PyResult<()> {
                    evm.db().set_balance(addr, value)?;
                    Ok(())
                })?
            }
            ChainWrapper::Python(chain) => {
                let value: BigUint = value.try_into()?;
                chain
                    .bind(py)
                    .getattr(intern!(py, "chain_interface"))?
                    .call_method1(
                        intern!(py, "set_balance"),
                        (self.address.borrow(py).__str__(), value),
                    )?;
                Ok(())
            }
        }
    }

    #[getter]
    pub fn get_code<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        match &self.chain {
            ChainWrapper::Native(chain) => {
                let addr = self.address.borrow(py).0;
                let code = self.with_evm_context(py, chain, |evm| -> PyResult<Vec<u8>> {
                    Ok(evm.db().basic(addr)?.map_or(vec![], |a| {
                        a.code.map_or(vec![], |c| c.original_bytes().to_vec())
                    }))
                })??;
                Ok(PyBytes::new(py, &code))
            }
            ChainWrapper::Python(chain) => Ok(chain
                .bind(py)
                .getattr(intern!(py, "chain_interface"))?
                .call_method1(
                    intern!(py, "get_code"),
                    (self.address.borrow(py).__str__(),),
                )?
                .downcast_into::<PyBytes>()?),
        }
    }

    #[setter]
    fn set_code(&self, py: Python, value: Bound<PyAny>) -> PyResult<()> {
        match &self.chain {
            ChainWrapper::Native(chain) => {
                let addr = self.address.borrow(py).0;
                let code = value.extract::<Vec<u8>>()?;
                self.with_evm_context(py, chain, |evm| -> PyResult<()> {
                    evm.db().set_code(addr, code)?;
                    Ok(())
                })?
            }
            ChainWrapper::Python(chain) => {
                chain
                    .bind(py)
                    .getattr(intern!(py, "chain_interface"))?
                    .call_method1(
                        intern!(py, "set_code"),
                        (self.address.borrow(py).__str__(), value),
                    )?;
                Ok(())
            }
        }
    }

    #[getter]
    fn get_nonce(&self, py: Python) -> PyResult<u64> {
        match &self.chain {
            ChainWrapper::Native(chain) => {
                let addr = self.address.borrow(py).0;
                self.with_evm_context(py, chain, |evm| -> PyResult<u64> {
                    Ok(evm.db().basic(addr)?.map_or(0, |a| a.nonce))
                })?
            }
            ChainWrapper::Python(chain) => chain
                .bind(py)
                .getattr(intern!(py, "chain_interface"))?
                .call_method1(
                    intern!(py, "get_transaction_count"),
                    (self.address.borrow(py).__str__(),),
                )?
                .extract::<u64>(),
        }
    }

    #[setter]
    fn set_nonce(&self, py: Python, value: u64) -> PyResult<()> {
        match &self.chain {
            ChainWrapper::Native(chain) => {
                let addr = self.address.borrow(py).0;
                self.with_evm_context(py, chain, |evm| -> PyResult<()> {
                    evm.db().set_nonce(addr, value)?;
                    Ok(())
                })?
            }
            ChainWrapper::Python(chain) => {
                let chain = chain.bind(py);
                chain
                    .getattr(intern!(py, "chain_interface"))?
                    .call_method1(
                        intern!(py, "set_nonce"),
                        (self.address.borrow(py).__str__(), value),
                    )?;
                chain.call_method1(
                    intern!(py, "_update_nonce"),
                    (self.address.clone_ref(py), value),
                )?;
                Ok(())
            }
        }
    }

    #[classmethod]
    #[pyo3(signature = (private_key, chain=None))]
    fn from_key(
        _cls: &Bound<'_, PyType>,
        py: Python,
        private_key: &Bound<PyAny>,
        chain: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };
        let address = Address::from_key(&Address::type_object(py), private_key)?;
        Self::from_address(py, address, chain)
    }

    #[classmethod]
    #[pyo3(signature = (mnemonic, passphrase="", path="m/44'/60'/0'/0/0", chain=None))]
    pub fn from_mnemonic(
        _cls: &Bound<'_, PyType>,
        py: Python,
        mnemonic: &str,
        passphrase: &str,
        path: &str,
        chain: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };
        Self::from_address(
            py,
            Address::from_mnemonic(&Address::type_object(py), mnemonic, passphrase, path)?,
            chain,
        )
    }

    #[classmethod]
    #[pyo3(signature = (alias, password=None, keystore=None, chain=None))]
    fn from_alias<'py>(
        _cls: &Bound<'py, PyType>,
        py: Python<'py>,
        alias: &str,
        password: Option<Bound<'py, PyString>>,
        keystore: Option<PathBuf>,
        chain: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };
        Self::from_address(
            py,
            Address::from_alias(
                &Address::type_object(py),
                py,
                alias,
                password,
                keystore,
            )?,
            chain,
        )
    }

    #[classmethod]
    #[pyo3(signature = (path="m/44'/60'/0'/0/0", chain=None))]
    fn from_trezor<'py>(
        _cls: &Bound<'py, PyType>,
        py: Python<'py>,
        path: &str,
        chain: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };
        Self::from_address(
            py,
            Address::from_trezor(&Address::type_object(py), path)?,
            chain,
        )
    }

    #[pyo3(signature = (data=vec![], value=ValueEnum::Int(BigUint::ZERO), from_=None, gas_limit=None, gas_price=None, max_fee_per_gas=None, max_priority_fee_per_gas=None, access_list=None, authorization_list=None, block=BlockEnum::Latest))]
    fn call<'py>(
        slf: &Bound<Self>,
        py: Python<'py>,
        data: Vec<u8>,
        value: ValueEnum,
        from_: Option<AddressEnum>,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<ValueEnum>,
        max_fee_per_gas: Option<ValueEnum>,
        max_priority_fee_per_gas: Option<ValueEnum>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'py, PyDict>>>,
        block: BlockEnum,
    ) -> PyResult<PyObject> {
        let borrowed = slf.borrow();
        match &borrowed.chain {
            ChainWrapper::Native(chain) => Chain::call(
                chain.bind(py),
                py,
                data,
                Some(borrowed.address.borrow(py).0),
                value.try_into()?,
                from_,
                gas_limit,
                gas_price.map(|v| v.try_into()).transpose()?,
                max_fee_per_gas.map(|v| v.try_into()).transpose()?,
                max_priority_fee_per_gas.map(|v| v.try_into()).transpose()?,
                access_list,
                authorization_list,
                block,
                None,
                None,
            ),
            ChainWrapper::Python(chain) => {
                let params = prepare_tx_params(
                    py,
                    chain.clone_ref(py),
                    &data,
                    from_,
                    Some(AddressEnum::Account(slf.clone().unbind())),
                    value,
                    gas_limit,
                    gas_price,
                    max_fee_per_gas,
                    max_priority_fee_per_gas,
                    access_list,
                    authorization_list,
                )?;
                let args: Vec<PyObject> = vec![];
                chain.call_method1(
                    py,
                    intern!(py, "_call"),
                    (
                        PyNone::get(py),
                        args,
                        params,
                        PyBytes::type_object(py),
                        block,
                    ),
                )
            }
        }
    }

    #[pyo3(signature = (
        data=vec![], value=ValueEnum::Int(BigUint::ZERO), from_=None, gas_limit=None, gas_price=None, max_fee_per_gas=None, max_priority_fee_per_gas=None, access_list=None, authorization_list=None, block=BlockEnum::Pending, revert_on_failure=true))]
    fn estimate<'py>(
        slf: &Bound<Self>,
        py: Python<'py>,
        data: Vec<u8>,
        value: ValueEnum,
        from_: Option<AddressEnum>,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<ValueEnum>,
        max_fee_per_gas: Option<ValueEnum>,
        max_priority_fee_per_gas: Option<ValueEnum>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'py, PyDict>>>,
        block: BlockEnum,
        revert_on_failure: bool,
    ) -> PyResult<PyObject> {
        let borrowed = slf.borrow();
        match &borrowed.chain {
            ChainWrapper::Native(chain) => Chain::estimate(
                chain.bind(py),
                py,
                data,
                Some(borrowed.address.borrow(py).0),
                value.try_into()?,
                from_,
                gas_limit,
                gas_price.map(|v| v.try_into()).transpose()?,
                max_fee_per_gas.map(|v| v.try_into()).transpose()?,
                max_priority_fee_per_gas.map(|v| v.try_into()).transpose()?,
                access_list,
                authorization_list,
                block,
                revert_on_failure,
            )?.into_py_any(py),
            ChainWrapper::Python(chain) => {
                if !revert_on_failure {
                    return Err(PyNotImplementedError::new_err(
                        "revert_on_failure is not supported with non-revm chains",
                    ));
                }
                let params = prepare_tx_params(
                    py,
                    chain.clone_ref(py),
                    &data,
                    from_,
                    Some(AddressEnum::Account(slf.clone().unbind())),
                    value,
                    gas_limit,
                    gas_price,
                    max_fee_per_gas,
                    max_priority_fee_per_gas,
                    access_list,
                    authorization_list,
                )?;
                let args: Vec<PyObject> = vec![];
                chain.call_method1(
                    py,
                    intern!(py, "_estimate"),
                    (PyNone::get(py), args, params, block),
                )
            }
        }
    }

    #[pyo3(signature = (data=vec![], value=ValueEnum::Int(BigUint::ZERO), from_=None, gas_limit=None, gas_price=None, max_fee_per_gas=None, max_priority_fee_per_gas=None, authorization_list=None, block=BlockEnum::Pending, revert_on_failure=true))]
    fn access_list<'py>(
        slf: &Bound<Self>,
        py: Python<'py>,
        data: Vec<u8>,
        value: ValueEnum,
        from_: Option<AddressEnum>,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<ValueEnum>,
        max_fee_per_gas: Option<ValueEnum>,
        max_priority_fee_per_gas: Option<ValueEnum>,
        authorization_list: Option<Vec<Bound<'py, PyDict>>>,
        block: BlockEnum,
        revert_on_failure: bool,
    ) -> PyResult<PyObject> {
        let borrowed = slf.borrow();
        match &borrowed.chain {
            ChainWrapper::Native(chain) => Chain::access_list(
                chain.bind(py),
                py,
                data,
                Some(borrowed.address.borrow(py).0),
                value.try_into()?,
                from_,
                gas_limit,
                gas_price.map(|v| v.try_into()).transpose()?,
                max_fee_per_gas.map(|v| v.try_into()).transpose()?,
                max_priority_fee_per_gas.map(|v| v.try_into()).transpose()?,
                authorization_list,
                block,
                revert_on_failure,
            )?.into_py_any(py),
            ChainWrapper::Python(chain) => {
                if !revert_on_failure {
                    return Err(PyNotImplementedError::new_err(
                        "revert_on_failure is not supported with non-revm chains",
                    ));
                }
                let params = prepare_tx_params(
                    py,
                    chain.clone_ref(py),
                    &data,
                    from_,
                    Some(AddressEnum::Account(slf.clone().unbind())),
                    value,
                    gas_limit,
                    gas_price,
                    max_fee_per_gas,
                    max_priority_fee_per_gas,
                    None,
                    authorization_list,
                )?;
                let args: Vec<PyObject> = vec![];
                chain.call_method1(
                    py,
                    intern!(py, "_access_list"),
                    (PyNone::get(py), args, params, block),
                )
            }
        }
    }

    #[pyo3(signature = (data=vec![], value=ValueEnum::Int(BigUint::ZERO), from_=None, gas_limit=None, gas_price=None, max_fee_per_gas=None, max_priority_fee_per_gas=None, access_list=None, authorization_list=None, confirmations=None))]
    fn transact<'py>(
        slf: &Bound<Self>,
        py: Python<'py>,
        data: Vec<u8>,
        value: ValueEnum,
        from_: Option<AddressEnum>,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<ValueEnum>,
        max_fee_per_gas: Option<ValueEnum>,
        max_priority_fee_per_gas: Option<ValueEnum>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'py, PyDict>>>,
        confirmations: Option<u64>,
    ) -> PyResult<PyObject> {
        let borrowed = slf.borrow();
        match &borrowed.chain {
            ChainWrapper::Native(chain) => Chain::transact(
                chain.bind(py),
                py,
                data,
                Some(borrowed.address.borrow(py).0),
                value.try_into()?,
                from_,
                gas_limit,
                gas_price.map(|v| v.try_into()).transpose()?,
                max_fee_per_gas.map(|v| v.try_into()).transpose()?,
                max_priority_fee_per_gas.map(|v| v.try_into()).transpose()?,
                access_list,
                authorization_list,
                PyBytes::type_object(py).into_any(),
                None,
            )?.into_py_any(py),
            ChainWrapper::Python(chain) => {
                let params = prepare_tx_params(
                    py,
                    chain.clone_ref(py),
                    &data,
                    from_.clone(),
                    Some(AddressEnum::Account(slf.clone().unbind())),
                    value,
                    gas_limit,
                    gas_price,
                    max_fee_per_gas,
                    max_priority_fee_per_gas,
                    access_list,
                    authorization_list,
                )?;
                let args: Vec<PyObject> = vec![];
                chain.call_method1(
                    py,
                    intern!(py, "_transact"),
                    (
                        PyNone::get(py),
                        args,
                        params,
                        true,
                        PyBytes::type_object(py),
                        confirmations,
                        from_,
                    ),
                )
            }
        }
    }

    fn sign<'py>(&self, py: Python<'py>, data: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyBytes>> {
        let handle = TOKIO_RUNTIME.handle();
        let signers = SIGNERS.lock().unwrap();
        let signer = signers.get(&self.address.borrow(py).0);

        if let Some(signer) = signer {
            let bytes = if let Ok(bytes) = data.downcast::<PyBytes>() {
                let data = bytes.as_bytes();
                py.allow_threads(move || signer.sign_message(data, &handle))
            } else if let Ok(bytearray) = data.downcast::<PyByteArray>() {
                let data = bytearray.to_vec();
                py.allow_threads(move || signer.sign_message(&data, &handle))
            } else {
                let bytes = data
                    .call_method0(intern!(py, "__bytes__"))?
                    .downcast_into::<PyBytes>()?;
                let data = bytes.as_bytes();
                py.allow_threads(move || signer.sign_message(data, &handle))
            }
            .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?
            .as_bytes();

            Ok(PyBytes::new(py, &bytes))
        } else {
            match &self.chain {
                ChainWrapper::Native(_) => {
                    Err(PyErr::new::<PyValueError, _>("Account cannot sign"))
                }
                ChainWrapper::Python(chain) => Ok(chain
                    .bind(py)
                    .getattr(intern!(py, "chain_interface"))?
                    .call_method1(
                        intern!(py, "sign"),
                        (self.address.borrow(py).__str__(), data),
                    )?
                    .downcast_into::<PyBytes>()?),
            }
        }
    }

    fn sign_hash<'py>(
        &self,
        py: Python<'py>,
        data: Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let handle = TOKIO_RUNTIME.handle();
        let signers = SIGNERS.lock().unwrap();
        let signer = signers
            .get(&self.address.borrow(py).0)
            .expect("Account cannot sign");

        let bytes = if let Ok(bytes) = data.downcast::<PyBytes>() {
            let data: &[u8; 32] = bytes
                .as_bytes()
                .try_into()
                .expect("32 bytes must be provided");
            py.allow_threads(move || signer.sign_hash(data, &handle))
        } else if let Ok(bytearray) = data.downcast::<PyByteArray>() {
            let vec = bytearray.to_vec();
            let data: &[u8; 32] = vec
                .as_slice()
                .try_into()
                .expect("32 bytes must be provided");
            py.allow_threads(move || signer.sign_hash(data, &handle))
        } else {
            let bytes = data
                .call_method0(intern!(py, "__bytes__"))?
                .downcast_into::<PyBytes>()?;
            let data: &[u8; 32] = bytes
                .as_bytes()
                .try_into()
                .expect("32 bytes must be provided");
            py.allow_threads(move || signer.sign_hash(data, &handle))
        }
        .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?
        .as_bytes();

        Ok(PyBytes::new(py, &bytes))
    }

    fn sign_transaction<'py>(
        &self,
        py: Python<'py>,
        tx: &Bound<'py, PyDict>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let handle = TOKIO_RUNTIME.handle();
        let signers = SIGNERS.lock().unwrap();
        let signer = signers.get(&self.address.borrow(py).0);

        if let Some(signer) = signer {
            let mut typed_tx = tx_params_to_typed_tx(py, tx)?;
            let signature = py.allow_threads(|| signer.sign_transaction(&mut typed_tx, handle))
                .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?;

            let signed = typed_tx.into_signed(signature);
            let mut buffer = Vec::new();
            signed.network_encode(&mut buffer);
            Ok(PyBytes::new(py, &buffer))
        } else {
            match &self.chain {
                ChainWrapper::Native(_) => {
                    Err(PyErr::new::<PyValueError, _>("Account cannot sign"))
                }
                ChainWrapper::Python(chain) => Ok(chain
                    .bind(py)
                    .getattr(intern!(py, "chain_interface"))?
                    .call_method1(
                        intern!(py, "sign_transaction"),
                        (tx,),
                    )?
                    .downcast_into::<PyBytes>()?),
            }
        }
    }

    #[pyo3(signature = (message, domain=None))]
    fn sign_structured<'py>(
        &self,
        py: Python<'py>,
        message: &Bound<'py, PyAny>,
        domain: Option<&Bound<'py, PyDict>>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let handle = TOKIO_RUNTIME.handle();
        let signers = SIGNERS.lock().unwrap();
        let signer = signers.get(&self.address.borrow(py).0);

        if let Some(signer) = signer {
            let typed = if let Ok(dict) = message.downcast::<PyDict>() {
                // raw dict
                let json = PyModule::import(py, "json")?
                    .call_method1(intern!(py, "dumps"), (dict,))?
                    .downcast::<PyString>()?
                    .to_string();
                serde_json::from_str::<TypedData>(&json)
                    .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?
            } else {
                let py_objects = get_py_objects(py);
                py_to_eip712(
                    py,
                    message,
                    domain.ok_or_else(|| {
                        PyErr::new::<PyValueError, _>("domain is required for EIP712 signing")
                    })?,
                    py_objects,
                )?
            };
            let signature = signer
                .sign_typed(&typed, &handle)
                .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?
                .as_bytes();
            Ok(PyBytes::new(py, &signature))
        } else {
            match &self.chain {
                ChainWrapper::Native(_) => {
                    Err(PyErr::new::<PyValueError, _>("Account cannot sign"))
                }
                ChainWrapper::Python(chain) => Ok(chain
                    .bind(py)
                    .getattr(intern!(py, "chain_interface"))?
                    .call_method1(
                        intern!(py, "sign_typed"),
                        (self.address.borrow(py).__str__(), message),
                    )?
                    .downcast_into::<PyBytes>()?),
            }
        }
    }

    #[pyo3(signature = (address, chain_id=None, nonce=None))]
    fn sign_authorization<'py>(&self, py: Python<'py>, address: AddressEnum, chain_id: Option<u64>, nonce: Option<u64>) -> PyResult<Bound<'py, PyDict>> {
        let handle = TOKIO_RUNTIME.handle();
        let signers = SIGNERS.lock().unwrap();
        let signer = signers
            .get(&self.address.borrow(py).0)
            .expect("Account cannot sign");

        let chain_id = match chain_id {
            Some(chain_id) => chain_id,
            None => match &self.chain {
                ChainWrapper::Native(chain) => chain.borrow(py).get_evm()?.cfg.chain_id,
                ChainWrapper::Python(chain) => {
                    chain.bind_borrowed(py).getattr(intern!(py, "chain_id"))?.extract::<u64>()?
                }
            }
        };
        let address = address.try_into()?;
        let nonce = nonce.unwrap_or(self.get_nonce(py)?);

        let authorization = Authorization {
            chain_id: U256::from(chain_id),
            address,
            nonce,
        };

        let signature = py.allow_threads(move || signer.sign_hash(&authorization.signature_hash().0, &handle))
            .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?;

        let signed_authorization = PyDict::new(py);
        signed_authorization.set_item(intern!(py, "address"), PyString::new(py, &address.to_checksum(Some(chain_id))))?;
        signed_authorization.set_item(intern!(py, "chainId"), chain_id)?;
        signed_authorization.set_item(intern!(py, "nonce"), nonce)?;
        signed_authorization.set_item(intern!(py, "r"), BigUint::from_bytes_le(signature.r().as_le_slice()))?;
        signed_authorization.set_item(intern!(py, "s"), BigUint::from_bytes_le(signature.s().as_le_slice()))?;
        signed_authorization.set_item(intern!(py, "yParity"), signature.v() as u8)?;

        Ok(signed_authorization)
    }
}

impl Account {
    pub fn from_private_key(py: Python, pk: &[u8], chain: Option<Py<PyAny>>) -> PyResult<Self> {
        let signer = LocalSigner::from_signing_key(SigningKey::from_slice(pk).unwrap());
        let address = signer.address();

        SIGNERS
            .lock()
            .unwrap()
            .insert(address, Signer::SigningKey(signer));

        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };

        Ok(Self::from_revm_address(py, address, chain)?)
    }

    pub fn from_random(py: Python, chain: Option<Py<PyAny>>) -> PyResult<Self> {
        let signer = LocalSigner::random();
        let address = signer.address();

        SIGNERS
            .lock()
            .unwrap()
            .insert(address, Signer::SigningKey(signer));

        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };
        Ok(Self::from_revm_address(py, address, chain)?)
    }
}
