use alloy::eips::{BlockId, BlockNumberOrTag};
use alloy::providers::{Provider, ProviderBuilder, RootProvider, WsConnect};
use alloy::rpc::client::ClientBuilder;
use alloy::rpc::types::Block as AlloyBlock;
use alloy::transports::{RpcError, TransportErrorKind};
use auto_impl::auto_impl;
use num_bigint::BigUint;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::types::{PyBytes, PyDict, PyNone, PyString, PyTuple};
use rand::rngs::SmallRng;
use rand::{Rng, SeedableRng};
use revm::context::result::ExecutionResult;
use revm::context::transaction::AccessList;
use revm::context::{BlockEnv, CfgEnv, ContextTr, Evm, EvmData, TxEnv};
use revm::database::{AlloyDB, EmptyDB, WrapDatabaseAsync};
use revm::handler::instructions::EthInstructions;
use revm::handler::EthPrecompiles;
use revm::inspector::{InspectEvm, InspectCommitEvm};
use revm::inspector::JournalExt;
use revm::interpreter::interpreter::EthInterpreter;
use revm::precompile::{PrecompileSpecId, Precompiles};
use revm::primitives::hardfork::SpecId;
use revm::primitives::{Address as RevmAddress, Bytes, Log, B256, U256};
use std::collections::HashMap;
use std::mem;
use std::str::FromStr;
use std::time::{SystemTime, UNIX_EPOCH};

use pyo3::{intern, prelude::*, IntoPyObjectExt, PyTypeInfo};
use std::sync::Arc;

use crate::inspectors::access_list_inspector::AccessListInspector;
use crate::account::Account;
use crate::address::Address;
use crate::blocks::{Block, Blocks};
use crate::chain_interface::ChainInterface;
use crate::inspectors::console_log_inspector::ConsoleLogInspector;
use crate::contract::Contract;
use crate::inspectors::coverage_inspector::CoverageInspector;
use crate::db::DB;
use crate::enums::{
    AccessListEnum, AddressEnum, BlockEnum, GasLimitEnum, RequestTypeEnum, ValueEnum,
};
use crate::evm::prepare_tx_env;
use crate::inspectors::fqn_inspector::{ErrorMetadata, EventMetadata, FqnInspector};
use crate::globals::{DEFAULT_CHAIN, TOKIO_RUNTIME};
use crate::pytypes::{decode_and_normalize, resolve_error};
use crate::tx::{BlockInfo, TransactionAbc};
use crate::txs::Txs;
use crate::utils::get_py_objects;
use crate::memory_db::CacheDB;
use revm::{Context, Inspector};
use url::Url;

use crate::inspectors::trace_inspector::{NativeTrace, TraceInspector};

use tokio;

#[pyfunction]
pub fn default_chain(py: Python) -> PyResult<Py<Chain>> {
    let mut chain = DEFAULT_CHAIN.lock().unwrap();
    match chain.as_ref() {
        Some(chain) => Ok(chain.clone_ref(py)),
        None => {
            *chain = Some(Chain::new(py)?);
            Ok(chain.as_ref().unwrap().clone_ref(py))
        }
    }
}

#[derive(Clone)]
pub(crate) struct ProviderWrapper(RootProvider);

impl ProviderWrapper {
    pub(crate) fn get_block_by_number(
        &self,
        py: Python,
        number: u64,
        with_transactions: bool,
        handle: &tokio::runtime::Handle,
    ) -> Result<Option<AlloyBlock>, RpcError<TransportErrorKind>> {
        py.allow_threads(|| {
            let future = self.0.get_block_by_number(BlockNumberOrTag::Number(number));
            if with_transactions {
                handle.block_on(async { future.full().await })
            } else {
                handle.block_on(async { future.await })
            }
        })
    }
}

#[auto_impl(&mut)]
trait InspectorExt<CTX: ContextTr<Journal: JournalExt>>: Inspector<CTX> {}

impl<CTX: ContextTr<Journal: JournalExt>> InspectorExt<CTX> for AccessListInspector {}
impl<CTX: ContextTr<Journal: JournalExt>> InspectorExt<CTX> for FqnInspector {}
impl<CTX: ContextTr<Journal: JournalExt>> InspectorExt<CTX> for TraceInspector {}
impl<CTX: ContextTr<Journal: JournalExt>> InspectorExt<CTX> for CoverageInspector {}
impl<CTX: ContextTr<Journal: JournalExt>> InspectorExt<CTX> for ConsoleLogInspector {}

trait FqnInspectorExt<CTX: ContextTr<Journal: JournalExt>>: InspectorExt<CTX> + Send {
    fn into_metadata(
        self: Box<Self>,
    ) -> (HashMap<[u8; 4], ErrorMetadata>, HashMap<Log, EventMetadata>);
    fn errors_metadata(&self) -> &HashMap<[u8; 4], ErrorMetadata>;
    fn sync_coverage(&mut self, py: Python) -> PyResult<()>;
}

impl<CTX: ContextTr<Journal: JournalExt>> FqnInspectorExt<CTX> for FqnInspector {
    fn into_metadata(
        self: Box<Self>,
    ) -> (HashMap<[u8; 4], ErrorMetadata>, HashMap<Log, EventMetadata>) {
        (self.errors_metadata, self.events_metadata)
    }
    fn errors_metadata(&self) -> &HashMap<[u8; 4], ErrorMetadata> {
        &self.errors_metadata
    }
    fn sync_coverage(&mut self, _: Python) -> PyResult<()> {
        // nothing to do
        Ok(())
    }
}

impl<CTX: ContextTr<Journal: JournalExt>> FqnInspectorExt<CTX> for CoverageInspector {
    fn into_metadata(
        self: Box<Self>,
    ) -> (HashMap<[u8; 4], ErrorMetadata>, HashMap<Log, EventMetadata>) {
        (
            self.fqn_inspector.errors_metadata,
            self.fqn_inspector.events_metadata,
        )
    }
    fn errors_metadata(&self) -> &HashMap<[u8; 4], ErrorMetadata> {
        &self.fqn_inspector.errors_metadata
    }
    fn sync_coverage(&mut self, py: Python) -> PyResult<()> {
        self.update_coverage(py)
    }
}

pub(crate) type CustomContext = Context<BlockEnv, TxEnv, CfgEnv, DB>;

pub(crate) type CustomEvm = Evm<
    CustomContext,
    (),
    EthInstructions<EthInterpreter, CustomContext>,
    EthPrecompiles,
>;

#[pyclass]
pub struct Chain {
    rng: SmallRng,
    pub evm: Option<CustomEvm>,
    pub(crate) provider: Option<ProviderWrapper>,
    pub labels: HashMap<RevmAddress, String>,
    collect_coverage: bool,

    pub deployed_libraries: HashMap<[u8; 17], RevmAddress>,

    pub(crate) blocks: Option<Py<Blocks>>,
    pub(crate) txs: Option<Py<Txs>>,
    pub(crate) chain_interface: Option<Py<ChainInterface>>,
    #[pyo3(get)]
    connected: bool,
    pub(crate) forked_chain_id: Option<u64>,
    forked_block: Option<u64>,
    accounts: Vec<Py<Account>>,
    #[pyo3(get)]
    default_tx_account: Option<Py<Account>>,
    #[pyo3(get)]
    default_call_account: Option<Py<Account>>,
    #[pyo3(get)]
    default_estimate_account: Option<Py<Account>>,
    #[pyo3(get)]
    default_access_list_account: Option<Py<Account>>,
    #[pyo3(get, set)]
    automine: bool,
    #[pyo3(get)]
    pub(crate) block_gas_limit: u64,

    latest_block_env: Option<BlockEnv>,
    snapshots: Vec<(CfgEnv, BlockEnv)>,
    pending_txs: Vec<Py<TransactionAbc>>,
    pub(crate) pending_gas_used: u64,

    // address => fqn
    // overrides how to resolve fqn (and pytypes) for this address
    pub(crate) fqn_overrides: HashMap<RevmAddress, Py<PyString>>,

    #[pyo3(get, set)]
    tx_callback: Option<Py<PyAny>>,
}

#[pymethods]
impl Chain {
    #[new]
    fn new(py: Python) -> PyResult<Py<Self>> {
        let random = Python::import(py, intern!(py, "wake.development.globals"))?
            .getattr(intern!(py, "random"))?;

        let chain = Py::new(
            py,
            Self {
                rng: SmallRng::seed_from_u64(
                    random
                        .call_method1(intern!(py, "getrandbits"), (64,))?
                        .extract()?,
                ),
                evm: None,
                provider: None,
                deployed_libraries: HashMap::new(),
                blocks: None,
                txs: None,
                chain_interface: None,
                labels: HashMap::new(),
                collect_coverage: false,
                connected: false,
                forked_chain_id: None,
                forked_block: None,
                accounts: vec![],
                default_tx_account: None,
                default_call_account: None,
                default_estimate_account: None,
                default_access_list_account: None,
                automine: true,
                block_gas_limit: 30000000_u64,
                latest_block_env: None,
                snapshots: vec![],
                pending_txs: vec![],
                pending_gas_used: 0,
                fqn_overrides: HashMap::new(),
                tx_callback: None,
            },
        )?;
        chain.borrow_mut(py).chain_interface =
            Some(Py::new(py, ChainInterface::new(chain.clone_ref(py)))?);
        Ok(chain)
    }

    pub fn __hash__(&self) -> u64 {
        self as *const _ as usize as u64
    }

    #[setter]
    fn set_default_call_account(
        slf: &Bound<Self>,
        py: Python,
        account: Option<AddressEnum>,
    ) -> PyResult<()> {
        slf.borrow_mut().default_call_account = match account {
            Some(account) => Some(Py::new(
                py,
                Account::from_revm_address(
                    py,
                    account.try_into()?,
                    slf.clone().unbind().into_any(),
                )?,
            )?),
            None => None,
        };
        Ok(())
    }

    #[setter]
    fn set_default_tx_account(
        slf: &Bound<Self>,
        py: Python,
        account: Option<AddressEnum>,
    ) -> PyResult<()> {
        slf.borrow_mut().default_tx_account = match account {
            Some(account) => Some(Py::new(
                py,
                Account::from_revm_address(
                    py,
                    account.try_into()?,
                    slf.clone().unbind().into_any(),
                )?,
            )?),
            None => None,
        };
        Ok(())
    }

    #[setter]
    fn set_default_estimate_account(
        slf: &Bound<Self>,
        py: Python,
        account: Option<AddressEnum>,
    ) -> PyResult<()> {
        slf.borrow_mut().default_estimate_account = match account {
            Some(account) => Some(Py::new(
                py,
                Account::from_revm_address(
                    py,
                    account.try_into()?,
                    slf.clone().unbind().into_any(),
                )?,
            )?),
            None => None,
        };
        Ok(())
    }

    #[setter]
    fn set_default_access_list_account(
        slf: &Bound<Self>,
        py: Python,
        account: Option<AddressEnum>,
    ) -> PyResult<()> {
        slf.borrow_mut().default_access_list_account = match account {
            Some(account) => Some(Py::new(
                py,
                Account::from_revm_address(
                    py,
                    account.try_into()?,
                    slf.clone().unbind().into_any(),
                )?,
            )?),
            None => None,
        };
        Ok(())
    }

    #[getter]
    fn get_accounts<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(py, &self.accounts)
    }

    #[getter]
    fn get_chain_id(&self, py: Python) -> PyResult<PyObject> {
        get_py_objects(py).wake_u256.call1(py, (self.get_evm()?.cfg.chain_id,))
    }

    #[getter]
    fn get_forked_chain_id(&self, py: Python) -> PyResult<PyObject> {
        match self.forked_chain_id {
            Some(chain_id) => get_py_objects(py)
                .wake_u256
                .call1(py, (chain_id,)),
            None => PyNone::get(py).into_py_any(py),
        }
    }

    #[getter]
    fn get_blocks(&self, py: Python) -> Py<Blocks> {
        self.blocks.as_ref().unwrap().clone_ref(py)
    }

    #[getter]
    fn get_txs(&self, py: Python) -> Py<Txs> {
        self.txs.as_ref().unwrap().clone_ref(py)
    }

    #[getter]
    fn get_chain_interface(&self, py: Python) -> Py<ChainInterface> {
        self.chain_interface.as_ref().unwrap().clone_ref(py)
    }

    #[getter]
    fn get_coinbase(slf: Py<Self>, py: Python) -> PyResult<Account> {
        let addr = slf.borrow(py).get_evm()?.block.beneficiary;
        Account::from_revm_address(py, addr, slf.into_any())
    }

    #[setter]
    fn set_coinbase(slf: Py<Self>, py: Python, value: AddressEnum) -> PyResult<()> {
        if let AddressEnum::Account(account) = &value {
            if !account.borrow(py).chain.inner().is(&slf) {
                return Err(PyValueError::new_err(
                    "Account does not belong to this chain",
                ));
            }
        }

        slf.borrow_mut(py)
            .get_evm_mut()?
            .block
            .beneficiary = value.try_into()?;

        Ok(())
    }

    #[pyo3(signature = (account))]
    fn set_default_accounts(
        slf: &Bound<Self>,
        py: Python,
        account: Option<AddressEnum>,
    ) -> PyResult<()> {
        let acc = match account {
            Some(account) => Some(Py::new(
                py,
                Account::from_revm_address(
                    py,
                    account.try_into()?,
                    slf.clone().unbind().into_any(),
                )?,
            )?),
            None => None,
        };

        let mut borrowed = slf.borrow_mut();

        borrowed.default_tx_account = acc.as_ref().map(|a| a.clone_ref(py));
        borrowed.default_call_account = acc.as_ref().map(|a| a.clone_ref(py));
        borrowed.default_estimate_account = acc.as_ref().map(|a| a.clone_ref(py));
        borrowed.default_access_list_account = acc;

        Ok(())
    }

    #[getter(_labels)]
    fn get_labels<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let labels = PyDict::new(py);
        for (addr, label) in &self.labels {
            labels.set_item(Py::new(py, Address(*addr))?, label)?;
        }
        Ok(labels)
    }

    #[setter(_labels)]
    fn set_labels(&mut self, labels: Bound<PyDict>) -> PyResult<()> {
        for (addr, label) in labels.iter() {
            self.labels.insert(
                addr.downcast_into::<Address>()?.borrow().0,
                label.downcast_into::<PyString>()?.to_string(),
            );
        }
        Ok(())
    }

    #[setter]
    fn set_block_gas_limit(&mut self, gas_limit: u64) -> PyResult<()> {
        if gas_limit < self.pending_gas_used {
            return Err(PyValueError::new_err("Gas limit is lower than gas already used in pending block"));
        }
        self.block_gas_limit = gas_limit;
        self.get_evm_mut()?.block.gas_limit = gas_limit - self.pending_gas_used;
        Ok(())
    }

    fn snapshot(&mut self) -> PyResult<String> {
        let evm = self.get_evm_mut()?;
        let snapshot_id = evm.db().snapshot().to_string();

        let cfg_env = evm.cfg.clone();
        let block_env = evm.block.clone();
        self.snapshots.push((cfg_env, block_env));
        // TODO: deployed libraries

        Ok(snapshot_id)
    }

    fn revert(slf: &Bound<Self>, py: Python, id: &str) -> PyResult<()> {
        let mut borrowed = slf.borrow_mut();

        let snapshot_id = id.parse().unwrap();
        borrowed.snapshots.truncate(snapshot_id);
        let (cfg_env, block_env) = borrowed.snapshots.pop().unwrap();

        let last_block_number = block_env.number - 1;

        let evm = borrowed.get_evm_mut()?;
        let journal_index = evm.db().revert(snapshot_id);
        evm.db().set_last_block_number(last_block_number);
        evm.cfg = cfg_env;
        evm.block = block_env;

        let provider = borrowed.provider.clone();
        let mut blocks = borrowed.blocks.as_mut().unwrap().borrow_mut(py);
        blocks.remove_blocks(last_block_number);

        drop(blocks);

        borrowed.txs.as_mut().unwrap().borrow_mut(py).remove_txs(py, journal_index);

        drop(borrowed);
        let latest_block_env = slf
            .borrow()
            .blocks
            .as_ref()
            .unwrap()
            .borrow_mut(py)
            .get_block(
                py,
                BlockEnum::Int(last_block_number as i64),
                last_block_number,
                provider,
            )?
            .borrow(py)
            .block_env
            .clone();

        slf.borrow_mut().latest_block_env = Some(latest_block_env);

        Ok(())
    }

    #[pyo3(signature = (*, accounts=10, chain_id=None, fork=None, hardfork=None))]
    fn connect(
        slf: Py<Self>,
        py: Python,
        accounts: u16,
        chain_id: Option<u64>,
        fork: Option<String>,
        hardfork: Option<String>,
    ) -> PyResult<PyObject> {
        let connect_context = PyModule::import(py, "wake.utils.connect_context")?
            .getattr("ConnectContext")?
            .call1((slf.clone_ref(py), accounts, chain_id, fork, hardfork))?;
        Ok(connect_context.into())
    }

    fn snapshot_and_revert(slf: Py<Self>, py: Python) -> PyResult<PyObject> {
        let context = PyModule::import(py, "wake.utils.snapshot_revert_context")?
            .getattr("SnapshotRevertContext")?
            .call1((slf.clone_ref(py),))?;
        Ok(context.into())
    }

    fn change_automine(slf: Py<Self>, py: Python, automine: bool) -> PyResult<PyObject> {
        let automine_context = PyModule::import(py, "wake.utils.automine_context")?
            .getattr("AutomineContext")?
            .call1((slf.clone_ref(py), automine))?;
        Ok(automine_context.into())
    }

    #[pyo3(name = "mine", signature = (callback=None))]
    fn mine_py(slf: Bound<Self>, py: Python, callback: Option<Bound<PyAny>>) -> PyResult<()> {
        if let Some(callback) = callback {
            let latest_timestamp = slf.borrow().latest_block_env.as_ref().unwrap().timestamp;
            let new_timestamp = callback
                .call1::<(u64,)>((latest_timestamp.try_into().unwrap(),))?
                .extract::<u64>()?;
            let mut borrowed = slf.borrow_mut();
            let evm = borrowed.get_evm_mut()?;
            evm.block.timestamp = new_timestamp;
            let _ = borrowed.mine(py, true);
        } else {
            let _ = slf.borrow_mut().mine(py, true);
        }

        Ok(())
    }

    fn set_next_block_timestamp(&mut self, new_timestamp: u64) -> PyResult<()> {
        let evm = self.get_evm_mut()?;
        evm.block.timestamp = new_timestamp;
        Ok(())
    }

    #[pyo3(signature = (accounts, chain_id, fork_url, hardfork))]
    fn _connect(
        slf: Py<Chain>,
        py: Python,
        accounts: u16,
        chain_id: Option<u64>,
        fork_url: Option<&str>,
        hardfork: Option<&str>,
    ) -> PyResult<()> {
        let mut slf_ = slf.borrow_mut(py);
        slf_.connected = true;

        let py_objects = get_py_objects(py);
        py_objects
            .wake_connected_chains
            .bind(py)
            .append(slf.clone_ref(py))?;

        slf_.collect_coverage = py
            .import("wake.testing.native_coverage")?
            .getattr("collect_coverage")?
            .extract::<bool>()?;

        for i in 0..accounts {
            slf_.accounts.push(Py::new(
                py,
                Account::from_mnemonic(
                    &Account::type_object(py),
                    py,
                    "test test test test test test test test test test test junk",
                    "",
                    format!("m/44'/60'/0'/0/{}", i).as_str(),
                    Some(slf.clone_ref(py).into_py_any(py)?), // TODO optimize
                )?,
            )?);
        }
        slf_.default_call_account = Some(slf_.accounts[0].clone_ref(py));
        slf_.default_tx_account = Some(slf_.accounts[0].clone_ref(py));
        slf_.default_estimate_account = Some(slf_.accounts[0].clone_ref(py));
        slf_.default_access_list_account = Some(slf_.accounts[0].clone_ref(py));

        //let runtime = tokio::runtime::Runtime::new().unwrap();
        let runtime = &TOKIO_RUNTIME;
        /*
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()
            .unwrap();
        */

        // TODO handler config

        let spec = match hardfork {
            Some(hardfork) => SpecId::from_str(hardfork)
                .map_err(|_| PyValueError::new_err("Invalid hardfork"))?,
            None => SpecId::default(),
        };


        match fork_url {
            Some(url) => {
                let mut parts = url.split('@');
                let url = parts.next().unwrap_or_default().to_string();
                let block = parts
                    .next()
                    .and_then(|b| b.parse::<u64>().ok())
                    .map(BlockId::from)
                    .unwrap_or(BlockId::latest());

                let (provider, forked_block, forked_chain_id) = py.allow_threads(|| {
                    let provider = if url.starts_with("ws://") || url.starts_with("wss://") {
                        Arc::new(ProviderBuilder::new().on_client(
                            runtime
                                .block_on(ClientBuilder::default().ws(WsConnect::new(url)))
                                .unwrap(),
                        ))
                    } else {
                        Arc::new(ProviderBuilder::new().on_client(
                            ClientBuilder::default().http(Url::parse(&url).unwrap()),
                        ))
                    };

                    let forked_block = runtime
                        .block_on(async { provider.get_block(block).await })
                        .unwrap()
                        .unwrap();
                    let forked_chain_id = runtime
                        .block_on(async { provider.get_chain_id().await })
                        .unwrap();

                    (provider, forked_block, forked_chain_id)
                });

                slf_.provider = Some(ProviderWrapper(provider.root().clone()));

                let mut db = CacheDB::new(
                    WrapDatabaseAsync::with_handle(
                        AlloyDB::new(provider, forked_block.header.number.into()),
                        runtime.handle().clone(),
                    ),
                    forked_block.header.number,
                );

                let path = format!(
                    ".wake/fork_cache/{}/{}/state.db",
                    forked_chain_id, forked_block.header.number
                );
                if std::path::Path::new(&path).is_file() {
                    if let Err(e) = db.load_forked_state(&path) {
                        log::warn!("Failed to load cached forking state: {}", e);
                    }
                }

                let mut evm: CustomEvm = Evm::new(
                    Context::new(DB::ForkDB(db), spec),
                    EthInstructions::default(),
                    EthPrecompiles{
                        precompiles: Precompiles::new(PrecompileSpecId::from_spec_id(spec)),
                        spec,
                    }
                );

                for account in slf_.accounts.iter() {
                    evm.db().set_code(account.borrow(py).address.borrow(py).0, vec![])?;
                }

                evm.cfg.chain_id = chain_id.unwrap_or(forked_chain_id);
                evm.block.number = forked_block.header.number + 1;
                evm.block.timestamp = forked_block.header.timestamp + 1;
                slf_.evm = Some(evm);
                slf_.forked_chain_id = Some(forked_chain_id);
                slf_.forked_block = Some(forked_block.header.number);
            }
            None => {
                let db = CacheDB::new(EmptyDB::new(), 0);

                let mut evm: CustomEvm = Evm::new(
                    Context::new(DB::EmptyDB(db), spec),
                    EthInstructions::default(),
                    EthPrecompiles{
                        precompiles: Precompiles::new(PrecompileSpecId::from_spec_id(spec)),
                        spec,
                    }
                );
                evm.cfg.chain_id = chain_id.unwrap_or(31337);
                evm.block.number = 0;
                evm.block.timestamp = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_secs()
                    .try_into()
                    .unwrap();
                slf_.evm = Some(evm);
            }
        }

        let block_gas_limit = slf_.block_gas_limit;
        let evm = slf_.get_evm_mut()?;
        evm.cfg.limit_contract_code_size = Some(usize::max_value());
        evm.cfg.disable_nonce_check = true;
        evm.cfg.disable_eip3607 = true;
        evm.block.gas_limit = block_gas_limit;
        evm.tx.chain_id = Some(evm.cfg.chain_id);

        slf_.blocks = Some(Py::new(py, Blocks::new(slf.clone_ref(py), slf_.forked_block))?);
        slf_.txs = Some(Py::new(py, Txs::new())?);

        let _ = slf_.mine(py, true)?; // mine one block

        Ok(())
    }

    fn _disconnect(slf: Bound<Self>, py: Python) -> PyResult<()> {
        let mut borrowed = slf.borrow_mut();
        borrowed.connected = false;
        borrowed.fqn_overrides.clear();

        if let Some(block_number) = borrowed.forked_block {
            let path = format!(
                ".wake/fork_cache/{}/{}",
                borrowed.forked_chain_id.unwrap(),
                block_number
            );
            match std::fs::create_dir_all(&path) {
                Ok(_) => {
                    let state_db_path = format!("{}/state.db", path);

                    if let Some(evm) = &mut borrowed.evm {
                        if let Err(e) = evm.db().dump_forked_state(&state_db_path) {
                            log::warn!("Failed to dump forked state: {}", e);
                        }
                    }
                }
                Err(e) => {
                    log::warn!("Failed to create fork cache directory: {}", e);
                }
            }
        }

        let py_objects = get_py_objects(py);
        let connected_chains = py_objects.wake_connected_chains.bind(py);

        let index = connected_chains.index(slf.into_pyobject(py)?)?;
        connected_chains.del_item(index)?;

        Ok(())
    }

    #[pyo3(signature = (
        creation_code,
        *,
        request_type=RequestTypeEnum::Tx,
        return_tx=false,
        from_=None,
        value=ValueEnum::Int(BigUint::ZERO),
        gas_limit=None,
        gas_price=None,
        max_fee_per_gas=None,
        max_priority_fee_per_gas=None,
        access_list=None,
        authorization_list=None,
        block=None,
        confirmations=None,
        revert_on_failure=true,
    ))]
    fn deploy(
        slf: &Bound<Self>,
        py: Python,
        creation_code: Vec<u8>,
        request_type: RequestTypeEnum,
        return_tx: bool,
        from_: Option<AddressEnum>,
        value: ValueEnum,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<ValueEnum>,
        max_fee_per_gas: Option<ValueEnum>,
        max_priority_fee_per_gas: Option<ValueEnum>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'_, PyDict>>>,
        block: Option<BlockEnum>,
        confirmations: Option<u64>,
        revert_on_failure: bool,
    ) -> PyResult<PyObject> {
        Contract::_execute(
            &Contract::type_object(py),
            py,
            slf.into_py_any(py)?,
            request_type,
            &hex::encode(creation_code),
            vec![],
            return_tx,
            Contract::type_object(py).into_any(),
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
            revert_on_failure,
        )
    }
}

impl Chain {
    fn with_evm_with_inspector<'a, F, R, I>(&mut self, py: Python, inspector: I, f: F) -> R
    where
        F: FnOnce(&mut Evm<CustomContext, I, EthInstructions<EthInterpreter, CustomContext>, EthPrecompiles>) -> R + Send,
        R: Send,
        I: Send + 'a + InspectorExt<CustomContext>,
    {
        let evm = self.evm.take().expect("Not connected");

        let (result, new_evm) = py.allow_threads(move || {
            let mut evm = evm.with_inspector(inspector);

            let result = f(&mut evm);

            let Evm { data: EvmData { ctx, .. }, instruction, precompiles } = evm;
            let new_evm = Evm {
                data: EvmData { ctx, inspector: () },
                instruction,
                precompiles,
            };

            (result, new_evm)
        });

        self.evm = Some(new_evm);
        result
    }

    pub(crate) fn get_evm(&self) -> PyResult<&CustomEvm> {
        self.evm
            .as_ref()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Not connected"))
    }

    pub(crate) fn get_evm_mut(&mut self) -> PyResult<&mut CustomEvm> {
        self.evm
            .as_mut()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Not connected"))
    }

    pub(crate) fn mine(&mut self, py: Python, force: bool) -> PyResult<Option<Py<Block>>> {
        if !self.automine && !force {
            return Ok(None);
        }

        let evm = self.evm
            .as_mut()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Not connected"))?;
        self.latest_block_env = Some(evm.block.clone());

        let last_block_number = self.latest_block_env.as_ref().unwrap().number;
        let block_hash = B256::from_slice(&self.rng.gen::<[u8; 32]>());

        evm.db()
            .set_last_block_number(last_block_number.try_into().unwrap());
        evm.db().set_block_hash(last_block_number, block_hash);

        let mut block_env = evm.block.clone();
        // reset to its original value
        block_env.gas_limit += self.pending_gas_used;

        let block = self
            .blocks
            .as_mut()
            .unwrap()
            .bind(py)
            .borrow_mut()
            .add_block(
                py,
                block_env,
                evm.db().get_journal_index(),
                block_hash,
                self.pending_gas_used,
            )?;

        // assign mined block to pending txs and clear them
        for tx in self.pending_txs.drain(..) {
            tx.borrow_mut(py).block = BlockInfo::Mined(block.clone_ref(py));
        }
        self.pending_gas_used = 0;

        // prepare pending block
        evm.block.number += 1;
        evm.block.timestamp += 1;
        evm.block.gas_limit = self.block_gas_limit;

        Ok(Some(block))
    }

    pub(crate) fn last_block_number(&self) -> PyResult<u64> {
        Ok(self.get_evm()?.db_ref().last_block_number())
    }

    pub(crate) fn call(
        slf: &Bound<Self>,
        py: Python,
        data: Vec<u8>,
        to: Option<RevmAddress>,
        value: U256,
        from_: Option<AddressEnum>,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<u128>,
        max_fee_per_gas: Option<U256>,
        max_priority_fee_per_gas: Option<U256>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'_, PyDict>>>,
        block: BlockEnum,
        return_type: Option<Bound<PyAny>>,
        abi: Option<Bound<PyDict>>,
    ) -> PyResult<PyObject> {
        let mut borrowed = slf.borrow_mut();
        let default_call_account = from_.unwrap_or(AddressEnum::Account(
            borrowed
                .default_call_account
                .as_ref()
                .expect("Default call account not set")
                .clone_ref(py),
        ));
        let collect_coverage = borrowed.collect_coverage;
        let block_gas_limit = borrowed.get_evm()?.block.gas_limit;
        let evm = borrowed.get_evm_mut()?;
        prepare_tx_env(
            py,
            &mut evm.tx,
            block_gas_limit,
            data,
            to,
            value,
            default_call_account,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            authorization_list,
        )?;

        let py_objects = get_py_objects(py);

        let mut inspector: Box<dyn FqnInspectorExt<CustomContext>> = if !collect_coverage {
            Box::new(FqnInspector::new())
        } else {
            Box::new(CoverageInspector::new())
        };

        let res = match block {
            BlockEnum::Pending => borrowed
                .with_evm_with_inspector(py, &mut *inspector, |evm| evm.inspect_replay())
                .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?,
            BlockEnum::Int(_) | BlockEnum::Latest => {
                let block = borrowed.blocks.as_ref().unwrap().borrow_mut(py).get_block(
                    py,
                    block,
                    borrowed.last_block_number()?,
                    borrowed.provider.clone(),
                )?;
                let block = block.borrow(py);
                let journal_index = block.journal_index;
                let journal_index = if let Some(journal_index) = journal_index {
                    journal_index
                } else {
                    todo!() // fetch from forked chain wih rpc
                };
                let block_env = block.block_env.clone();

                borrowed
                    .with_evm_with_inspector(py, &mut *inspector, |evm| {
                        let block_env_backup =
                            mem::replace(&mut evm.block, block_env);
                        let rollback = evm.db().rollback(journal_index);
                        let res = evm.inspect_replay();
                        evm.db().restore_rollback(rollback);
                        evm.block = block_env_backup;

                        res
                    })
                    .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?
            }
            _ => return Err(PyValueError::new_err("Invalid block")),
        };

        inspector.sync_coverage(py)?;

        match res.result {
            ExecutionResult::Success { output, .. } => {
                if let Some(abi) = abi {
                    Ok(decode_and_normalize(
                        py,
                        output.data(),
                        &abi,
                        &return_type.unwrap(),
                        &Py::from(borrowed),
                        intern!(py, "outputs"),
                        py_objects,
                    )?)
                } else {
                    PyBytes::new(py, output.data()).into_py_any(py)
                }
            }
            ExecutionResult::Revert {
                gas_used: _,
                output,
            } => Err(PyErr::from_value(
                resolve_error(
                    py,
                    &output,
                    &Py::from(borrowed),
                    None,
                    inspector.errors_metadata(),
                    py_objects,
                )?
                .bind(py)
                .clone(),
            )),
            ExecutionResult::Halt { reason, .. } => Err(PyErr::from_type(
                py_objects.wake_halt_exception.bind(py).clone(),
                format!("{:?}", reason),
            )),
        }
    }

    pub(crate) fn transact(
        slf: &Bound<Self>,
        py: Python,
        data: Vec<u8>,
        to: Option<RevmAddress>,
        value: U256,
        from_: Option<AddressEnum>,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<u128>,
        max_fee_per_gas: Option<U256>,
        max_priority_fee_per_gas: Option<U256>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'_, PyDict>>>,
        return_type: Bound<PyAny>,
        abi: Option<Bound<PyDict>>,
    ) -> PyResult<Py<TransactionAbc>> {
        let mut borrowed = slf.borrow_mut();
        let default_tx_account = from_.unwrap_or(AddressEnum::Account(
            borrowed
                .default_tx_account
                .as_ref()
                .expect("Default tx account not set")
                .clone_ref(py),
        ));
        let collect_coverage = borrowed.collect_coverage;

        let block_gas_limit = borrowed.get_evm()?.block.gas_limit;
        let evm = borrowed.get_evm_mut()?;
        prepare_tx_env(
            py,
            &mut evm.tx,
            block_gas_limit,
            data,
            to,
            value,
            default_tx_account,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            authorization_list,
        )?;

        let tx_env = evm.tx.clone();

        let mut inspector: Box<dyn FqnInspectorExt<CustomContext>> = if !collect_coverage {
            Box::new(FqnInspector::new())
        } else {
            Box::new(CoverageInspector::new())
        };

        let journal_index = evm.db_ref().get_journal_index();

        let result = borrowed
            .with_evm_with_inspector(py, &mut *inspector, |evm| evm.inspect_replay_commit())
            .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?;

        inspector.sync_coverage(py)?;

        let gas_limit_before = borrowed.get_evm()?.block.gas_limit;
        borrowed.get_evm_mut()?.block.gas_limit -= result.gas_used();
        borrowed.pending_gas_used += result.gas_used();

        let block = match borrowed.mine(py, false)? {
            Some(block) => BlockInfo::Mined(block),
            None => {
                BlockInfo::Pending(borrowed.get_evm()?.block.clone())
            }
        };
        let mined = matches!(block, BlockInfo::Mined(_));

        let (errors_metadata, events_metadata) = inspector.into_metadata();
        let tx = Py::new(
            py,
            TransactionAbc::new(
                slf.clone().unbind(),
                block,
                Py::from(return_type),
                abi.map(|abi| Py::from(abi)),
                to,
                result,
                errors_metadata,
                events_metadata,
                journal_index,
                tx_env,
                gas_limit_before,
            ),
        )?;
        if !mined {
            borrowed.pending_txs.push(tx.clone_ref(py));
        }

        borrowed
            .txs
            .as_mut()
            .unwrap()
            .bind(py)
            .borrow_mut()
            .add_tx(tx.clone_ref(py));

        let tx_callback = borrowed
            .tx_callback
            .as_ref()
            .map(|tx_callback| tx_callback.clone_ref(py));

        drop(borrowed);

        if let Some(tx_callback) = tx_callback {
            tx_callback.call1(py, (tx.clone_ref(py),))?;
        }

        match TransactionAbc::error(tx.bind(py), py)? {
            Some(error) => Err(error),
            None => Ok(tx),
        }
    }

    pub(crate) fn estimate(
        slf: &Bound<Self>,
        py: Python,
        data: Vec<u8>,
        to: Option<RevmAddress>,
        value: U256,
        from_: Option<AddressEnum>,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<u128>,
        max_fee_per_gas: Option<U256>,
        max_priority_fee_per_gas: Option<U256>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'_, PyDict>>>,
        block: BlockEnum,
        revert: bool,
    ) -> PyResult<u64> {
        let mut borrowed = slf.borrow_mut();
        let default_estimate_account = from_.unwrap_or(AddressEnum::Account(
            borrowed
                .default_estimate_account
                .as_ref()
                .expect("Default call account not set")
                .clone_ref(py),
        ));
        let block_gas_limit = borrowed.get_evm()?.block.gas_limit;
        let evm = borrowed.get_evm_mut()?;
        prepare_tx_env(
            py,
            &mut evm.tx,
            block_gas_limit,
            data,
            to,
            value.try_into()?,
            default_estimate_account,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            authorization_list,
        )?;

        let py_objects = get_py_objects(py);
        let mut inspector = FqnInspector::new();

        let res = match block {
            BlockEnum::Pending => borrowed
                .with_evm_with_inspector(py, &mut inspector, |evm| evm.inspect_replay())
                .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?,
            BlockEnum::Int(_) | BlockEnum::Latest => {
                let block = borrowed.blocks.as_ref().unwrap().borrow_mut(py).get_block(
                    py,
                    block,
                    borrowed.last_block_number()?,
                    borrowed.provider.clone(),
                )?;
                let block = block.borrow(py);
                let journal_index = block.journal_index;
                let journal_index = if let Some(journal_index) = journal_index {
                    journal_index
                } else {
                    todo!() // fetch from forked chain wih rpc
                };
                let block_env = block.block_env.clone();

                borrowed
                    .with_evm_with_inspector(py, &mut inspector, |evm| {
                        let block_env_backup =
                            mem::replace(&mut evm.block, block_env);
                        let rollback = evm.db().rollback(journal_index);
                        let res = evm.inspect_replay();
                        evm.db().restore_rollback(rollback);
                        evm.block = block_env_backup;

                        res
                    })
                    .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?
            }
            _ => return Err(PyValueError::new_err("Invalid block")),
        };

        match res.result {
            ExecutionResult::Success { gas_used, .. } => Ok(gas_used),
            ExecutionResult::Revert {
                gas_used, output, ..
            } => {
                if revert {
                    Err(PyErr::from_value(
                        resolve_error(
                            py,
                            &output,
                            &Py::from(borrowed),
                            None,
                            &inspector.errors_metadata,
                            py_objects,
                        )?
                        .bind(py)
                        .clone(),
                    ))
                } else {
                    Ok(gas_used)
                }
            }
            ExecutionResult::Halt { reason, gas_used } => {
                if revert {
                    Err(PyErr::from_type(
                        py_objects.wake_halt_exception.bind(py).clone(),
                        format!("{:?}", reason),
                    ))
                } else {
                    Ok(gas_used)
                }
            }
        }
    }

    pub(crate) fn access_list(
        slf: &Bound<Self>,
        py: Python,
        data: Vec<u8>,
        to: Option<RevmAddress>,
        value: U256,
        from_: Option<AddressEnum>,
        gas_limit: Option<GasLimitEnum>,
        gas_price: Option<u128>,
        max_fee_per_gas: Option<U256>,
        max_priority_fee_per_gas: Option<U256>,
        authorization_list: Option<Vec<Bound<'_, PyDict>>>,
        block: BlockEnum,
        revert: bool,
    ) -> PyResult<(HashMap<Address, Vec<BigUint>>, u64)> {
        let mut borrowed = slf.borrow_mut();
        let default_access_list_account = from_.unwrap_or(AddressEnum::Account(
            borrowed
                .default_access_list_account
                .as_ref()
                .expect("Default access list account not set")
                .clone_ref(py),
        ));
        let block_gas_limit = borrowed.get_evm()?.block.gas_limit;
        let evm = borrowed.get_evm_mut()?;
        prepare_tx_env(
            py,
            &mut evm.tx,
            block_gas_limit,
            data,
            to,
            value.try_into()?,
            default_access_list_account,
            gas_limit,
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            None,
            authorization_list,
        )?;

        let mut inspector = AccessListInspector::new(vec![].into());

        let res = match block {
            BlockEnum::Pending => borrowed
                .with_evm_with_inspector(py, &mut inspector, |evm| evm.inspect_replay())
                .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?,
            BlockEnum::Int(_) | BlockEnum::Latest => {
                let block = borrowed.blocks.as_ref().unwrap().borrow_mut(py).get_block(
                    py,
                    block,
                    borrowed.last_block_number()?,
                    borrowed.provider.clone(),
                )?;
                let block = block.borrow(py);
                let journal_index = block.journal_index;
                let journal_index = if let Some(journal_index) = journal_index {
                    journal_index
                } else {
                    todo!() // fetch from forked chain wih rpc
                };
                let block_env = block.block_env.clone();

                borrowed
                    .with_evm_with_inspector(py, &mut inspector, |evm| {
                        let block_env_backup =
                            mem::replace(&mut evm.block, block_env);
                        let rollback = evm.db().rollback(journal_index);
                        let res = evm.inspect_replay();
                        evm.db().restore_rollback(rollback);
                        evm.block = block_env_backup;

                        res
                    })
                    .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?
            }
            _ => return Err(PyValueError::new_err("Invalid block")),
        };

        let py_objects = get_py_objects(py);

        match res.result {
            ExecutionResult::Success { gas_used, .. } => {
                Ok((access_list_into_py(inspector.into_access_list()), gas_used))
            }
            ExecutionResult::Revert { gas_used, output } => {
                if revert {
                    Err(PyErr::from_value(
                        resolve_error(
                            py,
                            &output,
                            &Py::from(borrowed),
                            None,
                            &inspector.into_errors_metadata(),
                            py_objects,
                        )?
                        .bind(py)
                        .clone(),
                    ))
                } else {
                    Ok((access_list_into_py(inspector.into_access_list()), gas_used))
                }
            }
            ExecutionResult::Halt { reason, gas_used } => {
                if revert {
                    Err(PyErr::from_type(
                        py_objects.wake_halt_exception.bind(py).clone(),
                        format!("{:?}", reason),
                    ))
                } else {
                    Ok((access_list_into_py(inspector.into_access_list()), gas_used))
                }
            }
        }
    }

    pub(crate) fn get_call_trace(
        &mut self,
        py: Python,
        journal_index: usize,
        tx_env: &TxEnv,
        block_env: BlockEnv,
    ) -> NativeTrace {
        let mut inspector = TraceInspector::new();

        self.with_evm_with_inspector(py, &mut inspector, |evm| {
            let block_env_backup = mem::replace(&mut evm.block, block_env);
            let rollback = evm.db().rollback(journal_index);
            let _ = evm.inspect_with_tx(tx_env.clone());
            evm.db().restore_rollback(rollback);
            evm.block = block_env_backup;
        });

        inspector.into_root_trace()
    }

    pub(crate) fn get_console_logs(
        &mut self,
        py: Python,
        journal_index: usize,
        tx_env: &TxEnv,
        block_env: BlockEnv,
    ) -> PyResult<Vec<Bytes>> {
        let mut inspector = ConsoleLogInspector::new();

        self.with_evm_with_inspector(py, &mut inspector, |evm| {
            let block_env_backup = mem::replace(&mut evm.block, block_env);
            let rollback = evm.db().rollback(journal_index);
            let _ = evm.inspect_with_tx(tx_env.clone());
            evm.db().restore_rollback(rollback);
            evm.block = block_env_backup;
        });

        Ok(inspector.into_inputs())
    }
}

fn access_list_into_py(access_list: AccessList) -> HashMap<Address, Vec<BigUint>> {
    access_list
        .iter()
        .map(|a| {
            (
                Address::from(a.address),
                a.storage_keys
                    .iter()
                    .map(|k| BigUint::from_bytes_be(k.as_slice()))
                    .collect(),
            )
        })
        .collect()
}
