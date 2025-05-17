use std::fmt;
use std::sync::Arc;

use alloy::network::Ethereum;
use alloy::providers::fillers::{BlobGasFiller, ChainIdFiller, FillProvider, GasFiller, JoinFill, NonceFiller};
use alloy::providers::{Identity, RootProvider};
use pyo3::exceptions::PyException;
use pyo3::PyErr;
use revm::context::DBErrorMarker;
use revm::database::{AlloyDB, EmptyDB, WrapDatabaseAsync};
use revm::primitives::{Address, B256, U256, HashMap as RevmHashMap};
use revm::state::{Account, AccountInfo, Bytecode};
use revm::{Database, DatabaseCommit};

use crate::memory_db::{CacheDB, JournalEntry};


pub struct DBError(String);

impl std::error::Error for DBError {}

impl DBErrorMarker for DBError {}

impl std::fmt::Debug for DBError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl From<DBError> for PyErr {
    fn from(error: DBError) -> Self {
        PyException::new_err(error.0)
    }
}

impl fmt::Display for DBError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

pub enum DB {
    EmptyDB(CacheDB<EmptyDB>),
    ForkDB(CacheDB<WrapDatabaseAsync<AlloyDB<Ethereum, Arc<FillProvider<JoinFill<Identity, JoinFill<GasFiller, JoinFill<BlobGasFiller, JoinFill<NonceFiller, ChainIdFiller>>>>, RootProvider>>>>>),
}

impl DB {
    pub(crate) fn dump_forked_state(&mut self, file_path: &str) -> Result<(), Box<dyn std::error::Error>> {
        match self {
            DB::EmptyDB(db) => db.dump_forked_state(file_path),
            DB::ForkDB(db) => db.dump_forked_state(file_path),
        }
    }

    pub(crate) fn is_contract_forked(&self, address: &Address) -> Result<bool, DBError> {
        match self {
            DB::EmptyDB(_) => Ok(false),
            DB::ForkDB(db) => db.is_contract_forked(address).map_err(|e| DBError(e.to_string())),
        }
    }

    pub(crate) fn get_journal_index(&self) -> usize {
        match self {
            DB::EmptyDB(db) => db.journal.len(),
            DB::ForkDB(db) => db.journal.len(),
        }
    }

    pub(crate) fn rollback(&mut self, journal_index: usize) -> Vec<JournalEntry> {
        match self {
            DB::EmptyDB(db) => db.rollback(journal_index),
            DB::ForkDB(db) => db.rollback(journal_index),
        }
    }

    pub(crate) fn restore_rollback(&mut self, rollback: Vec<JournalEntry>) {
        match self {
            DB::EmptyDB(db) => db.restore_rollback(rollback),
            DB::ForkDB(db) => db.restore_rollback(rollback),
        }
    }

    /*
    pub(crate) fn with_rollback<R>(&mut self, journal_index: usize, f: impl FnOnce() -> R) -> R {
        match self {
            DB::EmptyDB(db) => db.with_rollback(journal_index, f),
            DB::ForkWsDB(db) => db.with_rollback(journal_index, f),
        }
    }
    */

    pub(crate) fn snapshot(&mut self) -> usize {
        match self {
            DB::EmptyDB(db) => db.snapshot(),
            DB::ForkDB(db) => db.snapshot(),
        }
    }

    pub(crate) fn revert(&mut self, snapshot_id: usize) {
        match self {
            DB::EmptyDB(db) => db.revert_snapshot(snapshot_id),
            DB::ForkDB(db) => db.revert_snapshot(snapshot_id),
        }
    }

    pub(crate) fn last_block_number(&self) -> u64 {
        match self {
            DB::EmptyDB(db) => db.last_block_number,
            DB::ForkDB(db) => db.last_block_number,
        }
    }

    pub(crate) fn set_last_block_number(&mut self, number: u64) {
        match self {
            DB::EmptyDB(db) => db.last_block_number = number,
            DB::ForkDB(db) => db.last_block_number = number,
        }
    }

    pub(crate) fn set_block_hash(&mut self, number: u64, hash: B256) {
        match self {
            DB::EmptyDB(db) => db.block_hashes.insert(number, hash),
            DB::ForkDB(db) => db.block_hashes.insert(number, hash),
        };
    }

    pub(crate) fn set_balance(&mut self, address: Address, balance: U256) -> Result<(), DBError> {
        match self {
            DB::EmptyDB(db) => db.set_balance(address, balance).map_err(|e| DBError(e.to_string())),
            DB::ForkDB(db) => db.set_balance(address, balance).map_err(|e| DBError(e.to_string())),
        }
    }

    pub(crate) fn set_code(&mut self, address: Address, code: Vec<u8>) -> Result<(), DBError> {
        match self {
            DB::EmptyDB(db) => db.set_code(address, code).map_err(|e| DBError(e.to_string())),
            DB::ForkDB(db) => db.set_code(address, code).map_err(|e| DBError(e.to_string())),
        }
    }

    pub(crate) fn set_storage(&mut self, address: Address, index: U256, value: U256) -> Result<(), DBError> {
        match self {
            DB::EmptyDB(db) => db.set_storage(address, index, value).map_err(|e| DBError(e.to_string())),
            DB::ForkDB(db) => db.set_storage(address, index, value).map_err(|e| DBError(e.to_string())),
        }
    }

    pub(crate) fn set_nonce(&mut self, address: Address, nonce: u64) -> Result<(), DBError> {
        match self {
            DB::EmptyDB(db) => db.set_nonce(address, nonce).map_err(|e| DBError(e.to_string())),
            DB::ForkDB(db) => db.set_nonce(address, nonce).map_err(|e| DBError(e.to_string())),
        }
    }
}

impl Database for DB {
    // TODO better error type?
    type Error = DBError;

    fn basic(&mut self, address: Address) -> Result<Option<AccountInfo>, Self::Error> {
        match self {
            DB::EmptyDB(db) => db.basic(address).map_err(|e| DBError(e.to_string())),
            DB::ForkDB(db) => db.basic(address).map_err(|e| DBError(e.to_string())),
        }
    }

    fn code_by_hash(&mut self, code_hash: B256) -> Result<Bytecode, Self::Error> {
        match self {
            DB::EmptyDB(db) => db.code_by_hash(code_hash).map_err(|e| DBError(e.to_string())),
            DB::ForkDB(db) => db.code_by_hash(code_hash).map_err(|e| DBError(e.to_string())),
        }
    }

    fn storage(&mut self, address: Address, index: U256) -> Result<U256, Self::Error> {
        match self {
            DB::EmptyDB(db) => db.storage(address, index).map_err(|e| DBError(e.to_string())),
            DB::ForkDB(db) => db.storage(address, index).map_err(|e| DBError(e.to_string())),
        }
    }

    fn block_hash(&mut self, number: u64) -> Result<B256, Self::Error> {
        match self {
            DB::EmptyDB(db) => db.block_hash(number).map_err(|e| DBError(e.to_string())),
            DB::ForkDB(db) => db.block_hash(number).map_err(|e| DBError(e.to_string())),
        }
    }
}

impl DatabaseCommit for DB {
    fn commit(&mut self, changes: RevmHashMap<Address, Account>) {
        //info!("committing changes to db: {:?}", changes);
        match self {
            DB::EmptyDB(db) => db.commit(changes),
            DB::ForkDB(db) => db.commit(changes),
        }
    }
}
