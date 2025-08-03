use alloy::hex::FromHexError;
use num_bigint::BigUint;
use pyo3::exceptions::PyValueError;
use pyo3::intern;
use pyo3::types::PyByteArray;
use pyo3::{prelude::*, types::PyBytes};
use revm::context::ContextTr;
use revm::primitives::U256;
use revm::Database;

use crate::account::Account;
use crate::chain::CustomEvm;
use crate::enums::BlockEnum;
use crate::{chain::Chain, utils::big_uint_to_u256};

#[pyclass]
pub struct ChainInterface {
    pub chain: Py<Chain>,
}

impl ChainInterface {
    fn with_evm<F, R>(&self, py: Python, chain: &Py<Chain>, f: F) -> PyResult<R>
    where
        F: FnOnce(&mut CustomEvm) -> R + Send,
        R: Send,
    {
        let mut chain = chain.borrow_mut(py);
        let evm = chain.get_evm_mut()?;

        let result = py.allow_threads(|| f(&mut *evm));

        Ok(result)
    }
}

#[pymethods]
impl ChainInterface {
    #[new]
    pub fn new(chain: Py<Chain>) -> Self {
        Self { chain }
    }

    #[pyo3(name = "type")]
    fn type_(&self) -> &str {
        "revm"
    }

    #[pyo3(signature = (address, position, block_identifier = BlockEnum::Latest))]
    fn get_storage_at<'py>(
        &self,
        py: Python<'py>,
        address: &str,
        position: BigUint,
        block_identifier: BlockEnum,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let address = address.parse().map_err(|e: FromHexError| PyValueError::new_err(e.to_string()))?;

        let data = match block_identifier {
            BlockEnum::Pending => self.with_evm(py, &self.chain, |evm| {
                evm.db().storage(address, big_uint_to_u256(position))
            })?,
            BlockEnum::Int(_) | BlockEnum::Latest => {
                let last_block_number = self.chain.borrow(py).last_block_number()?;
                let chain = self.chain.bind(py).borrow_mut();
                let journal_index = chain
                    .blocks
                    .as_ref()
                    .expect("Not connected")
                    .borrow_mut(py)
                    .get_block(
                        py,
                        block_identifier,
                        last_block_number,
                        chain.provider.clone(),
                    )?
                    .borrow(py)
                    .journal_index;
                let journal_index = if let Some(journal_index) = journal_index {
                    journal_index
                } else {
                    todo!() // fetch from forked chain wih rpc
                };

                self.with_evm(py, &self.chain, |evm| {
                    let rollback = evm.db().rollback(journal_index);
                    let data = evm.db().storage(address, big_uint_to_u256(position));
                    evm.db().restore_rollback(rollback);
                    data
                })?
            }
            _ => return Err(PyValueError::new_err("Invalid block identifier")),
        }?;
        Ok(PyBytes::new(py, &data.to_be_bytes::<32>()))
    }

    fn set_storage_at(
        &self,
        py: Python,
        address: &str,
        position: BigUint,
        value: Bound<PyAny>,
    ) -> PyResult<()> {
        let tmp;
        let tmp2;

        let bytes = if let Ok(bytes) = value.downcast::<PyBytes>() {
            bytes.as_bytes()
        } else if let Ok(bytearray) = value.downcast::<PyByteArray>() {
            tmp = bytearray.to_vec();
            tmp.as_slice()
        } else {
            tmp2 = value
                .call_method0(intern!(py, "__bytes__"))?
                .downcast_into::<PyBytes>()?;
            tmp2.as_bytes()
        };

        let address = address.parse().map_err(|e: FromHexError| PyValueError::new_err(e.to_string()))?;

        self.with_evm(py, &self.chain, |evm| {
            evm.db().set_storage(address, big_uint_to_u256(position), U256::from_be_slice(bytes))
        })??;

        self.chain.borrow_mut(py).mine(py, false)?;

        Ok(())
    }

    #[pyo3(signature = (address, block_identifier = BlockEnum::Latest))]
    fn get_code<'py>(
        &self,
        py: Python<'py>,
        address: &str,
        block_identifier: BlockEnum,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let address = address.parse().map_err(|e: FromHexError| PyValueError::new_err(e.to_string()))?;

        match block_identifier {
            BlockEnum::Pending => {
                let account = Account::from_address_native(
                    py,
                    address,
                    self.chain.clone_ref(py),
                )?;
                account.get_code(py)
            }
            BlockEnum::Int(_) | BlockEnum::Latest => {
                let last_block_number = self.chain.borrow(py).last_block_number()?;
                let journal_index = self
                    .chain
                    .borrow(py)
                    .blocks
                    .as_ref()
                    .expect("Not connected")
                    .borrow_mut(py)
                    .get_block(
                        py,
                        block_identifier,
                        last_block_number,
                        self.chain.borrow(py).provider.clone(),
                    )?
                    .borrow(py)
                    .journal_index;
                let journal_index = if let Some(journal_index) = journal_index {
                    journal_index
                } else {
                    todo!() // fetch from forked chain wih rpc
                };

                let code = self.with_evm(py, &self.chain, |evm| -> PyResult<Vec<u8>> {
                    let rollback = evm.db().rollback(journal_index);
                    let code = evm.db().basic(address)?.map_or(vec![], |a| {
                        a.code.map_or(vec![], |c| c.original_bytes().to_vec())
                    });
                    evm.db().restore_rollback(rollback);
                    Ok(code)
                })??;

                Ok(PyBytes::new(py, &code))
            }
            _ => Err(PyValueError::new_err("Invalid block identifier")),
        }
    }
}
