use abi_old::Abi;
use abi::abi as abi_new;
use account::Account;
use address::Address;
use chain::{Chain, default_chain};
use contract::Contract;
use library::Library;
use utils::keccak256;
use pyo3::prelude::*;
use pyo3_log;
use utils::{new_mnemonic, to_checksum_address};
use inspectors::coverage_inspector::{sync_coverage, set_coverage_callback};
use eip712::{encode_eip712_type, encode_eip712_data};

mod core;
mod address;
mod blocks;
mod contract;
mod account;
mod chain;
mod enums;
mod library;
mod evm;
mod abi_old;
mod abi;
mod utils;
mod tx;
mod pytypes;
mod memory_db;
mod globals;
mod eip712;
mod chain_interface;
mod txs;
mod wei;
mod inspectors;
pub mod db;


#[pymodule]
fn wake_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    pyo3_log::init();

    m.add_function(wrap_pyfunction!(default_chain, m)?)?;
    m.add_function(wrap_pyfunction!(keccak256, m)?)?;
    m.add_function(wrap_pyfunction!(new_mnemonic, m)?)?;
    m.add_function(wrap_pyfunction!(to_checksum_address, m)?)?;
    m.add_function(wrap_pyfunction!(sync_coverage, m)?)?;
    m.add_function(wrap_pyfunction!(set_coverage_callback, m)?)?;
    m.add_function(wrap_pyfunction!(encode_eip712_type, m)?)?;
    m.add_function(wrap_pyfunction!(encode_eip712_data, m)?)?;

    m.add_class::<Address>()?;
    m.add_class::<Account>()?;
    m.add_class::<Chain>()?;
    m.add_class::<Abi>()?;
    m.add_class::<abi_new>()?;
    m.add_class::<Contract>()?;
    m.add_class::<Library>()?;
    Ok(())
}
