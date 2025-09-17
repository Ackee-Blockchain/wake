use std::{collections::HashMap, sync::Arc};

use pyo3::{prelude::*, types::PyType};
use revm::context::{BlockEnv, CfgEnv};
use revm::primitives::Address as RevmAddress;

use crate::{account::Account, chain::Chain, tx::TransactionAbc};


pub struct ChainSnapshot {
    // EVM state
    cfg_env: CfgEnv,

    // Chain state
    labels: Arc<HashMap<RevmAddress, String>>,
    deployed_libraries: Arc<HashMap<[u8; 17], RevmAddress>>,
    fqn_overrides: Arc<HashMap<RevmAddress, Py<PyType>>>,

    // Latest state
    latest_block_env: Option<BlockEnv>,

    // Pending state
    pub(crate) pending_block_env: BlockEnv,
    pending_txs: Vec<Py<TransactionAbc>>,
    pending_gas_used: u64,

    // Configuration state
    default_tx_account: Option<Py<Account>>,
    default_call_account: Option<Py<Account>>,
    default_estimate_account: Option<Py<Account>>,
    default_access_list_account: Option<Py<Account>>,
    block_gas_limit: u64,
    automine: bool,
}

impl ChainSnapshot {
    pub fn from_chain(chain: &Chain, py: Python) -> PyResult<Self> {
        let evm = chain.get_evm()?;
        Ok(Self {
            cfg_env: evm.cfg.clone(),
            labels: chain.labels.clone(),
            deployed_libraries: chain.deployed_libraries.clone(),
            fqn_overrides: chain.fqn_overrides.clone(),
            latest_block_env: chain.latest_block_env.clone(),
            pending_block_env: evm.block.clone(),
            pending_txs: chain.pending_txs.iter().map(|tx| tx.clone_ref(py)).collect(),
            pending_gas_used: chain.pending_gas_used,
            default_tx_account: chain.default_tx_account.as_ref().map(|account| account.clone_ref(py)),
            default_call_account: chain.default_call_account.as_ref().map(|account| account.clone_ref(py)),
            default_estimate_account: chain.default_estimate_account.as_ref().map(|account| account.clone_ref(py)),
            default_access_list_account: chain.default_access_list_account.as_ref().map(|account| account.clone_ref(py)),
            block_gas_limit: chain.block_gas_limit,
            automine: chain.automine,
        })
    }
    pub fn restore_to_chain(self, chain: &mut Chain) -> PyResult<()> {
        let evm = chain.get_evm_mut()?;
        evm.cfg = self.cfg_env;
        evm.block = self.pending_block_env;

        chain.labels = self.labels;
        chain.deployed_libraries = self.deployed_libraries;
        chain.fqn_overrides = self.fqn_overrides;
        chain.latest_block_env = self.latest_block_env;
        chain.pending_txs = self.pending_txs;
        chain.pending_gas_used = self.pending_gas_used;
        chain.default_tx_account = self.default_tx_account;
        chain.default_call_account = self.default_call_account;
        chain.default_estimate_account = self.default_estimate_account;
        chain.default_access_list_account = self.default_access_list_account;
        chain.block_gas_limit = self.block_gas_limit;
        chain.automine = self.automine;
        Ok(())
    }
}