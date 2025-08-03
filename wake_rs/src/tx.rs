use std::collections::HashMap;

use alloy::dyn_abi::DynSolType;
use pyo3::{
    intern, prelude::*, types::{PyBytes, PyDict, PyList, PyNone}, IntoPyObjectExt, PyTypeInfo
};
use revm::{
    context::{result::{ExecutionResult, Output}, BlockEnv, TxEnv}, primitives::{
        bytes::Buf, Log, TxKind, B256
    },
};

use crate::{
    abi_old::{alloy_to_py, AbiError}, account::Account, address::Address, blocks::Block, chain::Chain, inspectors::fqn_inspector::{ErrorMetadata, EventMetadata}, pytypes::{
        collapse_if_tuple, decode_and_normalize, new_unknown_error,
        resolve_error, resolve_event,
    }, utils::get_py_objects
};

pub enum BlockInfo {
    Mined(Py<Block>),
    Pending(BlockEnv),
}

#[pyclass(subclass)]
pub struct TransactionAbc {
    chain: Py<Chain>,
    pub(crate) block: BlockInfo,
    return_type: Py<PyAny>,
    result: ExecutionResult,
    abi: Option<Py<PyDict>>,
    errors_metadata: HashMap<[u8; 4], ErrorMetadata>,
    events_metadata: HashMap<Log, EventMetadata>,

    cached_error: Option<PyErr>,
    cached_return_value: Option<PyObject>,
    cached_call_trace: Option<PyObject>,
    pub(crate) journal_index: usize, // used for EVM DB journal rollbacks; index into DB journal before this tx happened
    tx_env: TxEnv,
    gas_limit_before: u64, // gas limit before this tx was executed
    tx_hash: B256,
    #[pyo3(get)]
    tx_index: u32,
}

impl TransactionAbc {
    pub fn new(
        chain: Py<Chain>,
        block: BlockInfo,
        return_type: Py<PyAny>,
        abi: Option<Py<PyDict>>,
        result: ExecutionResult,
        errors_metadata: HashMap<[u8; 4], ErrorMetadata>,
        events_metadata: HashMap<Log, EventMetadata>,
        journal_index: usize,
        tx_env: TxEnv,
        gas_limit_before: u64,
        tx_hash: B256,
        tx_index: u32,
    ) -> Self {
        Self {
            chain,
            block,
            return_type,
            result,
            abi,
            errors_metadata,
            events_metadata,
            cached_error: None,
            cached_return_value: None,
            cached_call_trace: None,
            journal_index,
            tx_env,
            gas_limit_before,
            tx_hash,
            tx_index,
        }
    }
}

#[pymethods]
impl TransactionAbc {
    #[getter]
    fn tx_hash(&self) -> String {
        self.tx_hash.to_string()
    }

    #[getter]
    fn chain(&self, py: Python) -> Py<Chain> {
        self.chain.clone_ref(py)
    }

    #[getter]
    fn block(&self, py: Python) -> PyResult<Py<Block>> {
        match &self.block {
            BlockInfo::Mined(block) => Ok(block.clone_ref(py)),
            BlockInfo::Pending(_) => {
                let borrowed_chain = self.chain.borrow(py);
                let mut block_env = borrowed_chain.get_evm()?.block.clone();
                let gas_used = borrowed_chain.pending_gas_used;

                // add pending gas used to the block gas limit
                block_env.gas_limit += gas_used;

                return Py::new(
                    py,
                    Block {
                        chain: self.chain.clone_ref(py),
                        block_hash: B256::ZERO,
                        block_env,
                        journal_index: None,
                        gas_used,
                    },
                );
            }
        }
    }

    #[getter]
    fn block_number(&self, py: Python) -> PyResult<u64> {
        match &self.block {
            BlockInfo::Mined(block) => Ok(block.borrow(py).block_env.number),
            BlockInfo::Pending(block_env) => {
                Ok(block_env.number)
            }
        }
    }

    #[getter]
    fn data<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, self.tx_env.data.0.chunk())
    }

    #[getter]
    fn from_(&self, py: Python) -> PyResult<Py<Account>> {
        Py::new(py, Account::from_address_native(py, self.tx_env.caller, self.chain.clone_ref(py))?)
    }

    #[getter]
    fn to(&self, py: Python) -> PyResult<Option<Py<Account>>> {
        match self.tx_env.kind {
            TxKind::Call(to) => Ok(Some(Py::new(py, Account::from_address_native(py, to, self.chain.clone_ref(py))?)?)),
            TxKind::Create => Ok(None),
        }
    }

    #[getter]
    fn gas_used(&self) -> u64 {
        self.result.gas_used()
    }

    #[getter]
    fn cumulative_gas_used(&self, py: Python) -> PyResult<u64> {
        Ok(self.block(py)?.borrow(py).block_env.gas_limit - self.gas_limit_before + self.result.gas_used())
    }

    #[getter]
    fn status<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let py_objects = get_py_objects(py);

        match &self.result {
            ExecutionResult::Success { .. } => py_objects.tx_status_enum.bind(py).call1((1,)),
            ExecutionResult::Revert { .. } => py_objects.tx_status_enum.bind(py).call1((0,)),
            ExecutionResult::Halt { .. } => py_objects.tx_status_enum.bind(py).call1((0,)),
        }
    }

    #[getter]
    pub fn return_value(slf: &Bound<Self>, py: Python) -> PyResult<PyObject> {
        let borrowed = slf.borrow();

        if let ExecutionResult::Success { output, .. } = &borrowed.result {
            if let Some(return_value) = &borrowed.cached_return_value {
                return Ok(return_value.clone_ref(py));
            }

            match output {
                Output::Call(data) => {
                    let ret_type = borrowed.return_type.bind(py);

                    let ret = if ret_type.is(&PyNone::type_object(py)) {
                        PyNone::get(py).into_py_any(py)?
                    } else if let Some(abi) = &borrowed.abi {
                        let py_objects = get_py_objects(py);
                        decode_and_normalize(
                            py,
                            data,
                            abi.bind(py),
                            ret_type,
                            &borrowed.chain,
                            intern!(py, "outputs"),
                            py_objects,
                        )?
                    } else {
                        ret_type.call1((PyBytes::new(py, data),))?.unbind()
                    };

                    drop(borrowed);
                    slf.borrow_mut().cached_return_value = Some(ret.clone_ref(py));

                    Ok(ret)
                }
                Output::Create(_, address) => {
                    let address = Address::from(*address.unwrap());
                    let ret = borrowed.return_type.call(
                        py,
                        (address, borrowed.chain.clone_ref(py)),
                        None,
                    )?;

                    drop(borrowed);
                    slf.borrow_mut().cached_return_value = Some(ret.clone_ref(py));

                    Ok(ret)
                }
            }
        } else {
            Err(TransactionAbc::error(slf, py)?.unwrap())
        }
    }

    #[getter]
    fn raw_return_value<'py>(slf: &Bound<Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let borrowed = slf.borrow();
        if let ExecutionResult::Success { output, .. } = &borrowed.result {
            match output {
                Output::Call(data) => Ok(PyBytes::new(py, &data).into_any()),
                Output::Create(_, address) => Bound::new(
                    py,
                    Account::from_address_native(
                        py,
                        address.unwrap(),
                        borrowed.chain.clone_ref(py),
                    )?,
                )
                .map(|a| a.into_any()),
            }
        } else {
            Err(TransactionAbc::error(slf, py)?.unwrap())
        }
    }

    #[getter]
    fn events(&self, py: Python) -> PyResult<Vec<Py<PyAny>>> {
        match &self.result {
            ExecutionResult::Success { logs, .. } => {
                let py_objects = get_py_objects(py);

                logs.iter()
                    .map(|log| {
                        resolve_event(py, log, &self.chain, self.events_metadata.get(log), py_objects)
                    })
                    .collect()
            }
            _ => Ok(vec![]),
        }
    }

    #[getter]
    fn raw_events(&self, py: Python) -> PyResult<Vec<Py<PyAny>>> {
        match &self.result {
            ExecutionResult::Success { logs, .. } => {
                let py_objects = get_py_objects(py);
                let mut events = Vec::with_capacity(logs.len());

                for log in logs {
                    let topics: Vec<Bound<PyBytes>> = log
                        .topics()
                        .iter()
                        .map(|t| PyBytes::new(py, t.as_slice()))
                        .collect();
                    let event = py_objects.wake_unknown_event.call(
                        py,
                        (topics, PyBytes::new(py, &log.data.data)),
                        None,
                    )?;
                    event.setattr(
                        py,
                        "origin",
                        Account::from_address_native(py, log.address, self.chain.clone_ref(py))?,
                    )?;
                    events.push(event);
                }

                Ok(events)
            }
            _ => Ok(vec![]),
        }
    }

    #[getter]
    pub fn error(slf: &Bound<Self>, py: Python) -> PyResult<Option<PyErr>> {
        let borrowed = slf.borrow();
        match &borrowed.result {
            ExecutionResult::Success { .. } => Ok(None),
            ExecutionResult::Revert {
                gas_used: _,
                output,
            } => Ok(Some(PyErr::from_value(
                resolve_error(
                    py,
                    &output,
                    &borrowed.chain,
                    Some(slf),
                    &borrowed.errors_metadata,
                    get_py_objects(py),
                )?
                .bind(py)
                .clone(),
            ))),
            ExecutionResult::Halt { reason, .. } => {
                let error = get_py_objects(py).wake_halt_exception.bind(py).call1((format!("{:?}", reason),))?;
                error.setattr("tx", slf)?;
                Ok(Some(PyErr::from_value(error,)))
            }
        }
    }

    #[getter]
    fn raw_error(slf: &Bound<Self>, py: Python) -> PyResult<Option<PyErr>> {
        match &slf.borrow().result {
            ExecutionResult::Success { .. } => Ok(None),
            ExecutionResult::Revert {
                gas_used: _,
                output,
            } => {
                let error = new_unknown_error(py, output, Some(slf), get_py_objects(py))?;
                error.setattr(py, "tx", slf)?;
                Ok(Some(PyErr::from_value(error.into_bound(py),)))
            }
            ExecutionResult::Halt { reason, .. } => {
                let error = get_py_objects(py).wake_halt_exception.bind(py).call1((format!("{:?}", reason),))?;
                error.setattr("tx", slf)?;
                Ok(Some(PyErr::from_value(error,)))
            }
        }
    }

    #[getter]
    fn console_logs(&self, py: Python) -> PyResult<Vec<Py<PyAny>>> {
        let mut block_env = match &self.block {
            BlockInfo::Mined(block) => block.borrow(py).block_env.clone(),
            BlockInfo::Pending(block_env) => block_env.clone(),
        };
        block_env.gas_limit = self.gas_limit_before;

        let console_logs = self.chain.borrow_mut(py).get_console_logs(
            py,
            self.journal_index,
            &self.tx_env,
            block_env,
        )?;
        let py_objects = get_py_objects(py);
        let hardhat_console_abi = py_objects.hardhat_console_abi.bind_borrowed(py);

        let mut logs = Vec::with_capacity(console_logs.len());

        for log in console_logs {
            if let Some(abi) = hardhat_console_abi.get_item(PyBytes::new(py, &log[..4]))? {
                let abi = abi.downcast_into::<PyList>()?;
                let mut abi_types = Vec::with_capacity(abi.len());

                for input in abi.iter() {
                    let output_dict = input.downcast::<PyDict>()?;
                    collapse_if_tuple(py, output_dict, &mut abi_types)?;
                }

                let alloy_type: DynSolType = format!("({})", abi_types.join(",")).parse().unwrap();

                let decoded = alloy_type
                    .abi_decode_sequence(&log[4..])
                    .map_err(|e| AbiError::new_err(e.to_string()))?;

                logs.push(alloy_to_py(py, &decoded, py_objects)?);
            }
        }

        Ok(logs)
    }

    #[getter]
    fn call_trace<'py>(slf: &Bound<Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let borrowed = slf.borrow();
        let journal_index = borrowed.journal_index;

        let mut block_env = match &borrowed.block {
            BlockInfo::Mined(block) => block.borrow(py).block_env.clone(),
            BlockInfo::Pending(block_env) => block_env.clone(),
        };
        block_env.gas_limit = borrowed.gas_limit_before;

        let trace = borrowed.chain.borrow_mut(py).get_call_trace(
            py,
            journal_index,
            &borrowed.tx_env,
            block_env,
        );

        let py_objects = get_py_objects(py);

        let tmp = py_objects.wake_call_trace.bind(py).call_method1(
            intern!(py, "from_native_trace"),
            (
                trace,
                Address::from(borrowed.tx_env.caller),
                borrowed.chain.clone_ref(py),
            ),
        )?;

        Ok(tmp)
    }
}

#[pyclass(extends=TransactionAbc)]
pub struct Eip1559Transaction {}

#[pymethods]
impl Eip1559Transaction {
    #[getter]
    fn chain_id(slf: PyRef<'_, Self>, py: Python) -> PyResult<u64> {
        Ok(slf.as_ref().chain.borrow(py).get_evm()?.cfg.chain_id)
    }
}
