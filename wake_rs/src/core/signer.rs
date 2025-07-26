use std::collections::HashMap;
use std::sync::Mutex;

use alloy::consensus::SignableTransaction;
use alloy::dyn_abi::TypedData;
use alloy::network::{TxSigner, TxSignerSync};
use alloy::signers::{k256::ecdsa::SigningKey, local::LocalSigner, trezor::TrezorSigner, Signer as AlloySigner, Error as AlloySignerError};
use alloy::signers::{Signature, SignerSync};
use lazy_static::lazy_static;
use revm::primitives::Address;


lazy_static! {
    pub(crate) static ref SIGNERS: Mutex<HashMap<Address, Signer>> = Mutex::new(HashMap::new());
}


pub(crate) enum Signer {
    SigningKey(LocalSigner<SigningKey>),
    Trezor(TrezorSigner),
}

impl Signer {
    pub(crate) fn sign_hash(&self, hash: &[u8; 32], handle: &tokio::runtime::Handle) -> Result<Signature, AlloySignerError> {
        match self {
            Signer::SigningKey(signer) => signer.sign_hash_sync(hash.into()),
            Signer::Trezor(signer) => handle.block_on(signer.sign_hash(hash.into()))
        }
    }

    pub(crate) fn sign_message(&self, data: &[u8], handle: &tokio::runtime::Handle) -> Result<Signature, AlloySignerError> {
        match self {
            Signer::SigningKey(signer) => signer.sign_message_sync(data),
            Signer::Trezor(signer) => handle.block_on(signer.sign_message(data))
        }
    }

    pub(crate) fn sign_typed(&self, data: &TypedData, handle: &tokio::runtime::Handle) -> Result<Signature, AlloySignerError> {
        match self {
            Signer::SigningKey(signer) => signer.sign_dynamic_typed_data_sync(data),
            Signer::Trezor(signer) => handle.block_on(signer.sign_dynamic_typed_data(data))
        }
    }

    pub(crate) fn sign_transaction(&self, tx: &mut dyn SignableTransaction<Signature>, handle: &tokio::runtime::Handle) -> Result<Signature, AlloySignerError> {
        match self {
            Signer::SigningKey(signer) => signer.sign_transaction_sync(tx),
            Signer::Trezor(signer) => handle.block_on(signer.sign_transaction(tx))
        }
    }
}
