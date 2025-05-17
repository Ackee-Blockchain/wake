use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use revm::context::BlockEnv;
use revm::primitives::B256;

use crate::chain::{Chain, ProviderWrapper};
use crate::enums::BlockEnum;
use crate::globals::TOKIO_RUNTIME;
use crate::utils::header_to_block_env;
use log::info;

#[pyclass]
pub(crate) struct Blocks {
    chain: Py<Chain>,
    blocks: HashMap<u64, Py<Block>>
}

impl Blocks {
    pub fn add_block(&mut self, py: Python, block_env: BlockEnv, journal_index: usize, block_hash: B256) -> PyResult<Py<Block>> {
        let block_number = block_env.number.try_into().unwrap();
        let block = Py::new(py, Block {
            chain: self.chain.clone_ref(py),
            block_hash,
            block_env,
            journal_index: Some(journal_index),
        })?;
        self.blocks.insert(block_number, block.clone_ref(py));
        Ok(block)
    }

    pub fn remove_blocks(&mut self, latest_block_number: u64) {
        self.blocks.retain(|number, _| *number <= latest_block_number);
    }

    pub fn get_block(&mut self, py: Python, block: BlockEnum, last_block_number: u64, provider: Option<ProviderWrapper>) -> Result<Py<Block>, PyErr> {
        let number = match block {
            BlockEnum::Int(block_number) => {
                if block_number > last_block_number {
                    return Err(PyValueError::new_err("Block number out of range"));
                }
                block_number
            }
            BlockEnum::Latest | BlockEnum::Safe | BlockEnum::Finalized => {
                self.chain.borrow(py).last_block_number()?
            }
            BlockEnum::Pending => {
                let pending_block_env = self.chain.borrow(py).get_evm()?.block.clone();

                return Py::new(py, Block {
                    chain: self.chain.clone_ref(py),
                    block_hash: B256::ZERO,
                    block_env: pending_block_env,
                    journal_index: None,
                });
            }
            BlockEnum::Earliest => {
                0
            }
        };

        if let Some(block) = self.blocks.get(&number) {
            Ok(block.clone_ref(py))
        } else {
            match provider {
                Some(provider) => {
                    let block = provider.get_block_by_number(py, number, true, TOKIO_RUNTIME.handle());
                    match block {
                        Ok(block) => {
                            if let Some(block) = block {
                                let block = Py::new(py, Block {
                                    chain: self.chain.clone_ref(py),
                                    block_hash: block.header.hash,
                                    block_env: header_to_block_env(block.header),
                                    journal_index: None,
                                })?;
                                self.blocks.insert(number, block.clone_ref(py));
                                Ok(block)
                            } else {
                                info!("Block not found: {}", number);
                                Err(PyValueError::new_err("Block not found"))
                            }
                        }
                        Err(e) => Err(PyValueError::new_err(e.to_string())),
                    }
                }
                None => Err(PyValueError::new_err("Block not found"))
            }
        }
    }
}

#[pymethods]
impl Blocks {
    #[new]
    pub(crate) fn new(chain: Py<Chain>) -> Self {
        Self { chain, blocks: HashMap::new() }
    }

    fn __getitem__(&mut self, py: Python, block: BlockEnum) -> PyResult<Py<Block>> {
        let chain = self.chain.borrow(py);
        let last_block_number = chain.last_block_number()?;
        let provider = chain.provider.clone();
        drop(chain);
        Ok(Py::new(py, self.get_block(py, block, last_block_number, provider)?)?)
    }
}

#[pyclass]
pub struct Block {
    #[pyo3(get)]
    chain: Py<Chain>,
    pub block_env: BlockEnv,
    pub block_hash: B256,
    /// index into DB journal after this block was created
    /// None if this block was forked or this is temporal pending block
    pub journal_index: Option<usize>,
}

#[pymethods]
impl Block {
    #[getter]
    fn get_number(&self) -> u64 {
        self.block_env.number.try_into().unwrap()
    }

    #[getter]
    fn get_timestamp(&self) -> u64 {
        self.block_env.timestamp.try_into().unwrap()
    }
}
