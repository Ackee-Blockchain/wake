use std::{
    collections::{hash_map::Entry, HashMap},
    iter::zip,
    mem,
    process,
};

use revm::{
    primitives::{Address, B256, KECCAK_EMPTY, U256, HashMap as RevmHashMap }, state::{Account, AccountInfo, Bytecode}, Database, DatabaseCommit, DatabaseRef
};

use bincode::{serialize_into, Options};
use std::fs::File;
use std::io::{self, Write};

use uuid::Uuid;

#[derive(Debug, Clone)]
pub enum JournalEntry {
    ContractChange(B256, Option<Bytecode>),
    AccountChange(Address, Option<DbAccount>),
    StorageChange(Address, HashMap<U256, Option<U256>>),
    StorageReplace(Address, Option<HashMap<U256, U256>>),
}

#[derive(serde::Serialize, serde::Deserialize)]
pub struct DiskCache {
    accounts: HashMap<Address, DbAccount>, // only accounts[0] from CacheDB is saved
    contracts: HashMap<B256, Bytecode>,
    storage: HashMap<Address, HashMap<U256, U256>>, // only storage[0] from CacheDB is saved
    block_hashes: HashMap<u64, B256>,
}

#[derive(Debug, Clone)]
pub struct CacheDB<ExtDB> {
    /// Account info where None means it is not existing. Not existing state is needed for Pre TANGERINE forks.
    /// `code` is always `None`, and bytecode can be found in `contracts`.
    /// Each item in the vector represents a snapshot.
    pub accounts: Vec<HashMap<Address, DbAccount>>,
    /// Tracks all contracts by their code hash.
    pub contracts: HashMap<B256, Bytecode>,
    pub storage: Vec<HashMap<Address, HashMap<U256, U256>>>,
    /// All cached block hashes from the [DatabaseRef].
    pub block_hashes: HashMap<u64, B256>,
    /// The underlying database ([DatabaseRef]) that is used to load data.
    ///
    /// Note: this is read-only, data is never written to this database.
    pub db: ExtDB,

    pub last_block_number: u64,
    pub journal: Vec<JournalEntry>,
    pub snapshot_journal_indexes: Vec<usize>,
}

impl<ExtDB: DatabaseRef> CacheDB<ExtDB> {
    pub fn new(db: ExtDB, last_block_number: u64) -> Self {
        let mut contracts = HashMap::new();
        contracts.insert(KECCAK_EMPTY, Bytecode::default());
        contracts.insert(B256::ZERO, Bytecode::default());
        Self {
            accounts: vec![HashMap::new(), HashMap::new()],
            contracts: contracts,
            storage: vec![HashMap::new(), HashMap::new()],
            block_hashes: HashMap::new(),
            db,
            last_block_number,
            journal: vec![],
            snapshot_journal_indexes: vec![],
        }
    }

    pub fn load_forked_state(&mut self, file_path: &str) -> Result<(), Box<dyn std::error::Error>> {
        let file = File::open(file_path).map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;
        let mut reader = io::BufReader::new(file);
        let disk_cache: DiskCache =
            bincode::options()
            .with_limit(10_000_000)
            .with_fixint_encoding()
            .deserialize_from(&mut reader).map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;

        self.accounts[0] = disk_cache.accounts;
        self.contracts = disk_cache.contracts;
        self.storage[0] = disk_cache.storage;
        self.block_hashes = disk_cache.block_hashes;

        Ok(())
    }

    pub fn dump_forked_state(&mut self, file_path: &str) -> Result<(), Box<dyn std::error::Error>> {
        // Create a unique temp file name using PID and UUID
        let temp_path = format!("{}.{}.{}.tmp",
            file_path,
            process::id(),
            Uuid::new_v4()
        );

        let file = File::options()
            .write(true)
            .create_new(true)
            .open(&temp_path)
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;

        let mut writer = io::BufWriter::new(file);

        let disk_cache = DiskCache {
            accounts: std::mem::take(&mut self.accounts[0]),
            contracts: std::mem::take(&mut self.contracts),
            storage: std::mem::take(&mut self.storage[0]),
            block_hashes: std::mem::take(&mut self.block_hashes),
        };

        // Write to temporary file
        serialize_into(&mut writer, &disk_cache)
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;

        // Ensure all data is written to disk
        writer.flush().map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;

        // Atomically rename temp file to target file
        std::fs::rename(&temp_path, file_path)
            .map_err(|e| {
                // Clean up temp file if rename fails
                let _ = std::fs::remove_file(&temp_path);
                Box::new(e) as Box<dyn std::error::Error>
            })?;

        Ok(())
    }

    pub fn is_contract_forked(&self, address: &Address) -> Result<bool, ExtDB::Error> {
        let basic = if let Some(basic) = self.accounts[0].get(address) {
            basic
        } else {
            &self.forked_account_or_new(*address)?
        };

        Ok(basic.info.code.as_ref().is_some_and(|code| !code.is_empty()))
    }

    fn forked_account_or_new(&self, address: Address) -> Result<DbAccount, ExtDB::Error> {
        let mut basic = self
            .db
            .basic_ref(address)?
            .map(|info| DbAccount {
                info,
                ..Default::default()
            })
            .unwrap_or_else(DbAccount::new_not_existing);

        if let Some(bytecode) = basic.info.code {
            basic.info.code = Some(bytecode);
        }

        Ok(basic)
    }

    fn rollback_journal_entry(
        &mut self,
        entry: JournalEntry,
        journal_index: usize,
    ) -> JournalEntry {
        match entry {
            JournalEntry::ContractChange(code_hash, _) => {
                JournalEntry::ContractChange(code_hash, self.contracts.remove(&code_hash))
            }
            JournalEntry::AccountChange(address, account) => {
                let pos = self
                    .snapshot_journal_indexes
                    .binary_search(&(journal_index + 1))
                    .unwrap_or_else(|x| x)
                    + 1;
                assert!(pos >= 1);
                let old = match account {
                    Some(account) => self.accounts[pos].insert(address, account),
                    None => self.accounts[pos].remove(&address),
                };
                JournalEntry::AccountChange(address, old)
            }
            JournalEntry::StorageChange(address, storage_change) => {
                let pos = self
                    .snapshot_journal_indexes
                    .binary_search(&(journal_index + 1))
                    .unwrap_or_else(|x| x)
                    + 1;
                assert!(pos >= 1);
                let storage = self.storage[pos].entry(address).or_default();
                let mut new_changes = HashMap::new();
                for (k, v) in storage_change {
                    if let Some(v) = v {
                        let old = storage.insert(k, v);
                        new_changes.insert(k, old);
                    } else {
                        let old = storage.remove(&k);
                        new_changes.insert(k, old);
                    }
                }
                JournalEntry::StorageChange(address, new_changes)
            }
            JournalEntry::StorageReplace(address, storage) => {
                let old = match storage {
                    Some(storage) => self.storage.last_mut().unwrap().insert(address, storage),
                    None => self.storage.last_mut().unwrap().remove(&address),
                };
                JournalEntry::StorageReplace(address, old)
            }
        }
    }

    /*
    fn rollback_journal_entry_no_reverse(&mut self, entry: JournalEntry) {
        match entry {
            JournalEntry::ContractChange(code_hash, _) => {
                self.contracts.remove(&code_hash);
            }
            JournalEntry::AccountChange(address, account) => {
                self.accounts.last_mut().unwrap().insert(address, account);
            }
            JournalEntry::StorageChange(address, storage_change) => {
                let storage = self.storage.last_mut().unwrap().entry(address).or_default();
                for (k, v) in storage_change {
                    if let Some(v) = v {
                        storage.insert(k, v);
                    } else {
                        storage.remove(&k);
                    }
                }
            }
            JournalEntry::StorageReplace(address, storage) => {
                self.storage.last_mut().unwrap().insert(address, storage);
            }
        }
    }
    */

    pub fn rollback(&mut self, journal_index: usize) -> Vec<JournalEntry> {
        let items_to_remove = self.journal.len() - journal_index;
        let mut rollback_items = Vec::with_capacity(items_to_remove);

        for i in (journal_index..self.journal.len()).rev() {
            let entry = self.journal.pop().unwrap();
            let reverse_entry = self.rollback_journal_entry(entry, i);
            rollback_items.push(reverse_entry);
        }
        rollback_items
    }

    pub fn restore_rollback(&mut self, rollback: Vec<JournalEntry>) {
        let mut journal_index = self.journal.len();

        for entry in rollback.into_iter().rev() {
            let reverse_entry = self.rollback_journal_entry(entry, journal_index);
            self.journal.push(reverse_entry);
            journal_index += 1;
        }
    }

    /*
    pub fn with_rollback<R>(&mut self, journal_index: usize, f: impl FnOnce() -> R) -> R {
        // roll back to the journal_index
        let items_to_remove = self.journal.len() - journal_index;
        let mut rollback_items = Vec::with_capacity(items_to_remove);
        for _ in 0..items_to_remove {
            let entry = self.journal.pop().unwrap();
            let reverse_entry = self.rollback_journal_entry(entry);
            rollback_items.push(reverse_entry);
        }

        let ret: R = f();

        // count with that `f` may commit changes to the DB, so we need to truncate the journal
        // assuming `f` does not remove any items from the journal
        let items_to_remove = self.journal.len() - journal_index;
        for _ in 0..items_to_remove {
            let entry = rollback_items.pop().unwrap();
            self.rollback_journal_entry_no_reverse(entry);
        }

        // re-apply rollback
        for entry in rollback_items.into_iter().rev() {
            self.rollback_journal_entry_no_reverse(entry);
        }

        ret
    }
    */

    pub fn snapshot(&mut self) -> usize {
        self.accounts.push(HashMap::new());
        self.storage.push(HashMap::new());
        self.snapshot_journal_indexes.push(self.journal.len());

        self.accounts.len() - 2
        // last_block_number saved and restored from chain.rs
    }

    pub fn revert_snapshot(&mut self, snapshot: usize) -> usize {
        self.accounts.truncate(snapshot + 1);
        self.storage.truncate(snapshot + 1);
        assert!(self.accounts.len() >= 2);

        let journal_index = self.snapshot_journal_indexes[snapshot - 1];
        self.journal.truncate(journal_index);
        self.snapshot_journal_indexes.truncate(snapshot - 1);
        assert!(self.accounts.len() == self.snapshot_journal_indexes.len() + 2);

        journal_index
    }

    pub fn set_balance(&mut self, address: Address, balance: U256) -> Result<(), ExtDB::Error> {
        let mut latest_db_account = None;

        for account in self.accounts.iter().rev() {
            if let Some(db_account) = account.get(&address) {
                latest_db_account = Some(db_account.clone());
                break;
            }
        }

        if latest_db_account.is_none() {
            let basic = self.forked_account_or_new(address)?;
            self.accounts[0].insert(address, basic.clone());

            latest_db_account = Some(basic);
        };

        let db_account = self
            .accounts
            .last_mut()
            .unwrap()
            .entry(address)
            .or_insert(latest_db_account.unwrap());

        self.journal.push(JournalEntry::AccountChange(
            address,
            Some(db_account.clone()),
        ));

        db_account.info.balance = balance;
        if db_account.account_state == AccountState::NotExisting {
            db_account.account_state = AccountState::Touched;
        }
        Ok(())
    }

    pub fn set_code(&mut self, address: Address, code: Vec<u8>) -> Result<(), ExtDB::Error> {
        let mut latest_db_account = None;

        for account in self.accounts.iter().rev() {
            if let Some(db_account) = account.get(&address) {
                latest_db_account = Some(db_account.clone());
                break;
            }
        }

        if latest_db_account.is_none() {
            let basic = self.forked_account_or_new(address)?;
            self.accounts[0].insert(address, basic.clone());

            latest_db_account = Some(basic);
        };

        let db_account = self
            .accounts
            .last_mut()
            .unwrap()
            .entry(address)
            .or_insert(latest_db_account.unwrap());

        self.journal.push(JournalEntry::AccountChange(
            address,
            Some(db_account.clone()),
        ));

        db_account.info.code = Some(Bytecode::new_legacy(code.into()));
        db_account.info.code_hash = db_account.info.code.as_ref().unwrap().hash_slow();

        if db_account.account_state == AccountState::NotExisting {
            db_account.account_state = AccountState::Touched;
        }

        Ok(())
    }

    pub fn set_storage(
        &mut self,
        address: Address,
        index: U256,
        value: U256,
    ) -> Result<(), ExtDB::Error> {
        let storage = self.storage.last_mut().unwrap().entry(address).or_default();

        let prev_value = storage.insert(index, value);
        self.journal.push(JournalEntry::StorageChange(
            address,
            HashMap::from([(index, prev_value)]),
        ));

        Ok(())
    }

    pub fn set_nonce(&mut self, address: Address, nonce: u64) -> Result<(), ExtDB::Error> {
        let mut latest_db_account = None;

        for account in self.accounts.iter().rev() {
            if let Some(db_account) = account.get(&address) {
                latest_db_account = Some(db_account.clone());
                break;
            }
        }

        if latest_db_account.is_none() {
            let basic = self.forked_account_or_new(address)?;
            self.accounts[0].insert(address, basic.clone());

            latest_db_account = Some(basic);
        };

        let db_account = self
            .accounts
            .last_mut()
            .unwrap()
            .entry(address)
            .or_insert(latest_db_account.unwrap());

        self.journal.push(JournalEntry::AccountChange(
            address,
            Some(db_account.clone()),
        ));

        db_account.info.nonce = nonce;

        if db_account.account_state == AccountState::NotExisting {
            db_account.account_state = AccountState::Touched;
        }
        Ok(())
    }

    /// Inserts the account's code into the cache.
    ///
    /// Accounts objects and code are stored separately in the cache, this will take the code from the account and instead map it to the code hash.
    ///
    /// Note: This will not insert into the underlying external database.
    pub fn insert_contract(&mut self, account: &mut AccountInfo) {
        if let Some(code) = &account.code {
            if !code.is_empty() {
                if account.code_hash == KECCAK_EMPTY {
                    account.code_hash = code.hash_slow();
                }
                self.contracts.entry(account.code_hash).or_insert_with(|| {
                    // previous value was unset
                    self.journal
                        .push(JournalEntry::ContractChange(account.code_hash, None));
                    code.clone()
                });
            }
        }
        if account.code_hash.is_zero() {
            account.code_hash = KECCAK_EMPTY;
        }
    }

    /// Insert account info but not override storage
    pub fn insert_account_info(&mut self, address: Address, mut info: AccountInfo) {
        self.insert_contract(&mut info);
        self.accounts
            .last_mut()
            .unwrap()
            .entry(address)
            .or_default()
            .info = info;
    }
}

impl<ExtDB: DatabaseRef> CacheDB<ExtDB> {
    /// Returns the account for the given address.
    ///
    /// If the account was not found in the cache, it will be loaded from the underlying database.
    pub fn load_account(&mut self, address: Address) -> Result<&mut DbAccount, ExtDB::Error> {
        let db = &self.db;
        match self.accounts.last_mut().unwrap().entry(address) {
            Entry::Occupied(entry) => Ok(entry.into_mut()),
            Entry::Vacant(entry) => Ok(entry.insert(
                db.basic_ref(address)?
                    .map(|info| DbAccount {
                        info,
                        ..Default::default()
                    })
                    .unwrap_or_else(DbAccount::new_not_existing),
            )),
        }
    }

    /*
    /// insert account storage without overriding account info
    pub fn insert_account_storage(
        &mut self,
        address: Address,
        slot: U256,
        value: U256,
    ) -> Result<(), ExtDB::Error> {
        let account = self.load_account(address)?;
        account.storage.insert(slot, value);
        Ok(())
    }

    /// replace account storage without overriding account info
    pub fn replace_account_storage(
        &mut self,
        address: Address,
        storage: HashMap<U256, U256>,
    ) -> Result<(), ExtDB::Error> {
        let account = self.load_account(address)?;
        account.account_state = AccountState::StorageCleared;
        account.storage = storage.into_iter().collect();
        Ok(())
    }
    */
}

impl<ExtDB: DatabaseRef> DatabaseCommit for CacheDB<ExtDB> {
    fn commit(&mut self, changes: RevmHashMap<Address, Account>) {
        for (address, mut account) in changes {
            if !account.is_touched() {
                continue;
            }

            if account.is_selfdestructed() {
                let prev_account = match self.accounts.last_mut().unwrap().entry(address) {
                    Entry::Occupied(mut entry) => {
                        let prev_state = mem::replace(
                            &mut entry.get_mut().account_state,
                            AccountState::NotExisting,
                        );
                        let prev_info =
                            mem::replace(&mut entry.get_mut().info, AccountInfo::default());
                        let prev_locally_created = mem::replace(
                            &mut entry.get_mut().locally_created,
                            false,
                        );

                        Some(DbAccount {
                            info: prev_info,
                            account_state: prev_state,
                            locally_created: prev_locally_created,
                        })
                    }
                    Entry::Vacant(entry) => {
                        entry.insert(DbAccount::new_not_existing());

                        None
                    }
                };
                self.journal
                    .push(JournalEntry::AccountChange(address, prev_account));

                let prev_storage = match self.storage.last_mut().unwrap().entry(address) {
                    Entry::Occupied(mut entry) => {
                        let prev_storage =
                            mem::replace(&mut entry.get_mut().clone(), HashMap::new());
                        Some(prev_storage)
                    }
                    Entry::Vacant(entry) => {
                        entry.insert(HashMap::new());
                        None
                    }
                };
                self.journal
                    .push(JournalEntry::StorageReplace(address, prev_storage));

                continue;
            }

            self.insert_contract(&mut account.info);

            let prev_account = match self.accounts.last_mut().unwrap().entry(address) {
                Entry::Occupied(mut entry) => {
                    let prev_state =
                        mem::replace(&mut entry.get_mut().account_state, AccountState::Touched);
                    let prev_info = mem::replace(&mut entry.get_mut().info, account.info);
                    let prev_locally_created = entry.get().locally_created;

                    Some(DbAccount {
                        info: prev_info,
                        account_state: prev_state,
                        locally_created: prev_locally_created,
                    })
                }
                Entry::Vacant(entry) => {
                    let locally_created = account.is_created();
                    entry.insert(DbAccount {
                        info: account.info,
                        account_state: AccountState::Touched,
                        locally_created,
                    });

                    None
                }
            };

            let mut prev_storage = HashMap::new();
            let current_storage = self.storage.last_mut().unwrap().entry(address).or_default();

            for (key, value) in account.storage {
                prev_storage.insert(key, current_storage.insert(key, value.present_value));
            }

            self.journal
                .push(JournalEntry::AccountChange(address, prev_account));
            self.journal
                .push(JournalEntry::StorageChange(address, prev_storage));
        }
    }
}

impl<ExtDB: DatabaseRef> Database for CacheDB<ExtDB> {
    type Error = ExtDB::Error;

    fn basic(&mut self, address: Address) -> Result<Option<AccountInfo>, Self::Error> {
        for account in self.accounts.iter().rev() {
            if let Some(db_account) = account.get(&address) {
                return Ok(db_account.info());
            }
        }
        let basic = self.forked_account_or_new(address)?;
        let info = basic.info();
        self.accounts[0].insert(address, basic);
        Ok(info)
    }

    fn code_by_hash(&mut self, code_hash: B256) -> Result<Bytecode, Self::Error> {
        match self.contracts.entry(code_hash) {
            Entry::Occupied(entry) => Ok(entry.get().clone()),
            Entry::Vacant(entry) => {
                // if you return code bytes when basic fn is called this function is not needed.
                Ok(entry.insert(self.db.code_by_hash_ref(code_hash)?).clone())
            }
        }
    }

    /// Get the value in an account's storage slot.
    ///
    /// It is assumed that account is already loaded.
    fn storage(&mut self, address: Address, index: U256) -> Result<U256, Self::Error> {
        let mut locally_created = false;

        for (accounts, storage) in zip(self.accounts.iter().rev(), self.storage.iter().rev()) {
            if let Some(account) = accounts.get(&address) {
                if account.locally_created {
                    locally_created = true;
                }
                if account.account_state == AccountState::NotExisting {
                    return Ok(U256::ZERO);
                }
            }
            if let Some(storage) = storage.get(&address) {
                if let Some(entry) = storage.get(&index) {
                    return Ok(*entry);
                }
            }
        }

        if locally_created {
            return Ok(U256::ZERO);
        }

        match self.accounts.first_mut().unwrap().entry(address) {
            Entry::Occupied(_) => {
                let value = self.db.storage_ref(address, index)?;

                match self.storage.first_mut().unwrap().entry(address) {
                    Entry::Occupied(mut entry) => {
                        entry.get_mut().insert(index, value);
                    }
                    Entry::Vacant(entry) => {
                        entry.insert(HashMap::from([(index, value)]));
                    }
                }

                return Ok(value);
            }
            Entry::Vacant(entry) => {
                let info = self.db.basic_ref(address)?;
                let value = if info.is_some() {
                    self.db.storage_ref(address, index)?
                } else {
                    U256::ZERO
                };
                entry.insert(info.into());

                match self.storage.first_mut().unwrap().entry(address) {
                    Entry::Occupied(mut entry) => {
                        entry.get_mut().insert(index, value);
                    }
                    Entry::Vacant(entry) => {
                        entry.insert(HashMap::from([(index, value)]));
                    }
                }

                return Ok(value);
            }
        }
    }

    fn block_hash(&mut self, number: u64) -> Result<B256, Self::Error> {
        if number > self.last_block_number || number < self.last_block_number - 256 {
            return Ok(B256::ZERO);
        }
        match self.block_hashes.entry(number) {
            Entry::Occupied(entry) => Ok(*entry.get()),
            Entry::Vacant(entry) => {
                let hash = self.db.block_hash_ref(number)?;
                entry.insert(hash);
                Ok(hash)
            }
        }
    }
}

impl<ExtDB: DatabaseRef> DatabaseRef for CacheDB<ExtDB> {
    type Error = ExtDB::Error;

    fn basic_ref(&self, address: Address) -> Result<Option<AccountInfo>, Self::Error> {
        for map in self.accounts.iter().rev() {
            if let Some(account) = map.get(&address) {
                return Ok(account.info());
            }
        }
        self.db.basic_ref(address)
    }

    fn code_by_hash_ref(&self, code_hash: B256) -> Result<Bytecode, Self::Error> {
        match self.contracts.get(&code_hash) {
            Some(entry) => Ok(entry.clone()),
            None => self.db.code_by_hash_ref(code_hash),
        }
    }

    fn storage_ref(&self, address: Address, index: U256) -> Result<U256, Self::Error> {
        let mut locally_created = false;

        for (accounts, storage) in zip(self.accounts.iter().rev(), self.storage.iter().rev()) {
            if let Some(account) = accounts.get(&address) {
                if account.locally_created {
                    locally_created = true;
                }
                if account.account_state == AccountState::NotExisting {
                    return Ok(U256::ZERO);
                }
            }
            if let Some(storage) = storage.get(&address) {
                if let Some(entry) = storage.get(&index) {
                    return Ok(*entry);
                }
            }
        }
        if locally_created {
            return Ok(U256::ZERO);
        }

        self.db.storage_ref(address, index)
    }

    fn block_hash_ref(&self, number: u64) -> Result<B256, Self::Error> {
        if number > self.last_block_number || number < self.last_block_number - 256 {
            return Ok(B256::ZERO);
        }
        match self.block_hashes.get(&number) {
            Some(entry) => Ok(*entry),
            None => self.db.block_hash_ref(number),
        }
    }
}

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct DbAccount {
    pub info: AccountInfo,
    /// If account is selfdestructed or newly created, storage will be cleared.
    pub account_state: AccountState,
    pub locally_created: bool,
}

impl DbAccount {
    pub fn new_not_existing() -> Self {
        Self {
            account_state: AccountState::NotExisting,
            ..Default::default()
        }
    }

    pub fn info(&self) -> Option<AccountInfo> {
        if matches!(self.account_state, AccountState::NotExisting) {
            None
        } else {
            Some(self.info.clone())
        }
    }
}

impl From<Option<AccountInfo>> for DbAccount {
    fn from(from: Option<AccountInfo>) -> Self {
        from.map(Self::from).unwrap_or_else(Self::new_not_existing)
    }
}

impl From<AccountInfo> for DbAccount {
    fn from(info: AccountInfo) -> Self {
        Self {
            info,
            account_state: AccountState::None,
            ..Default::default()
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum AccountState {
    /// Before Spurious Dragon hardfork there was a difference between empty and not existing.
    /// And we are flagging it here.
    NotExisting,
    /// EVM touched this account. For newer hardfork this means it can be cleared/removed from state.
    Touched,
    /// EVM didn't interacted with this account
    #[default]
    None,
}
