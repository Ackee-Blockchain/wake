use alloy::signers::local::coins_bip39::English;
use alloy::signers::local::{LocalSigner, LocalSignerError, MnemonicBuilder};
use alloy::signers::trezor::{HDPath, TrezorSigner};
use eth_keystore::KeystoreError;
use num_bigint::BigUint;
use pyo3::exceptions::PyValueError;
use pyo3::{intern, prelude::*};
use pyo3::class::basic::CompareOp;
use pyo3::types::{PyByteArray, PyBytes, PyString, PyType};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::path::PathBuf;
use revm::primitives::{Address as RevmAddress, FixedBytes};
use crate::core::signer::{Signer, SIGNERS};
use crate::enums::RawAddressEnum;
use crate::globals::TOKIO_RUNTIME;
use crate::utils::get_py_objects;


#[pyclass]
#[derive(Hash, PartialEq, Eq, Clone)]
pub struct Address(pub RevmAddress);

#[pymethods]
impl Address {
    #[allow(non_snake_case)]
    #[classattr]
    fn ZERO() -> Self {
        Self(RevmAddress::ZERO)
    }

    #[new]
    pub fn new(address: RawAddressEnum) -> PyResult<Self> {
        match address {
            RawAddressEnum::Int(i) => {
                let mut bytes = vec![0; 20];
                let be_bytes = i.to_bytes_be();
                bytes[20-be_bytes.len()..].copy_from_slice(&be_bytes);
                Ok(Self(RevmAddress::from_slice(&bytes)))
            }
            RawAddressEnum::String(s) => s.parse().map(Self).map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))
        }
    }

    pub fn __str__(&self) -> String {
        self.0.to_string()
    }

    fn __repr__(&self) -> String {
        self.__str__()
    }

    // TODO support int and str comparison?
    pub fn __richcmp__(&self, other: &Self, op: CompareOp) -> bool {
        op.matches(self.0.cmp(&other.0))
    }

    fn __hash__(&self) -> u64 {
        let mut hasher = DefaultHasher::new();
        self.0.hash(&mut hasher);
        hasher.finish()
    }

    fn __bytes__<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, self.0.as_slice())
    }

    fn __int__(&self) -> BigUint {
        BigUint::from_bytes_be(self.0.as_slice())
    }

    #[classmethod]
    pub fn from_key(_cls: &Bound<'_, PyType>, key: &Bound<PyAny>) -> PyResult<Self> {
        let signer = if let Ok(key) = key.downcast::<PyString>() {
            let key_str = key.to_str()?.trim_start_matches("0x");
            let key = hex::decode(key_str).map_err(|_| PyErr::new::<PyValueError, _>("Invalid hex string"))?;
            LocalSigner::from_slice(&key)
        } else if let Ok(key) = key.downcast::<PyBytes>() {
            LocalSigner::from_slice(key.as_bytes())
        } else if let Ok(key) = key.downcast::<PyByteArray>() {
            LocalSigner::from_slice(unsafe { key.as_bytes() })
        } else if let Ok(key) = key.extract::<BigUint>() {
            LocalSigner::from_slice(&key.to_bytes_be())
        } else {
            return Err(PyValueError::new_err("Invalid private key"));
        }.map_err(|_| PyErr::new::<PyValueError, _>("Invalid private key"))?;

        let address = signer.address();

        SIGNERS
            .lock()
            .unwrap()
            .insert(address, Signer::SigningKey(signer));

        Ok(Self(address))
    }

    #[classmethod]
    #[pyo3(signature = (mnemonic, passphrase="", path="m/44'/60'/0'/0/0"))]
    pub fn from_mnemonic(
        _cls: &Bound<'_, PyType>,
        mnemonic: &str,
        passphrase: &str,
        path: &str,
    ) -> PyResult<Self> {
        let e = MnemonicBuilder::<English>::default()
            .phrase(mnemonic)
            .password(passphrase)
            .derivation_path(path)
            .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?
            .build()
            .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?;
        let address = e.address();

        SIGNERS
            .lock()
            .unwrap()
            .insert(address, Signer::SigningKey(e));

        Ok(Self(address))
    }

    #[classmethod]
    #[pyo3(signature = (alias, password=None, keystore=None))]
    pub fn from_alias<'py>(_cls: &Bound<'py, PyType>, py: Python<'py>, alias: &str, password: Option<Bound<'py, PyString>>, keystore: Option<PathBuf>) -> PyResult<Self> {
        let py_objects = get_py_objects(py);
        let keypath = if let Some(keystore) = keystore {
            keystore.join(format!("{}.json", alias))
        } else {
            py_objects.get_config(py)?.getattr(intern!(py, "global_data_path"))?.extract::<PathBuf>()?.join(format!("keystore/{}.json", alias))
        };
        let password = match password {
            Some(p) => p,
            None => py_objects.click_prompt.bind(py).call1((format!("Password for account {}", alias), "", true),).map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?.downcast_into::<PyString>()?
        };

        let signer = LocalSigner::decrypt_keystore(keypath, password.to_str()?.to_owned().into_bytes()).map_err(|e|
            match e {
                LocalSignerError::EthKeystoreError(KeystoreError::StdIo(_)) => PyErr::new::<PyValueError, _>(format!("Account '{}' not found", alias)),
                _ => PyErr::new::<PyValueError, _>(e.to_string()) // TODO better mapping?
            }
        )?;
        let address = signer.address();

        SIGNERS
            .lock()
            .unwrap()
            .insert(address, Signer::SigningKey(signer));

        Ok(Self(address))
    }

    #[classmethod]
    #[pyo3(signature = (path="m/44'/60'/0'/0/0"))]
    pub fn from_trezor(
        _cls: &Bound<'_, PyType>,
        path: &str,
    ) -> PyResult<Self> {
        let handle = TOKIO_RUNTIME.handle();
        let signer = handle
            .block_on(TrezorSigner::new(
                HDPath::Other(path.to_string()),
                None,
            ))
            .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?;

        let address = handle
            .block_on(signer.get_address())
            .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?;

        SIGNERS
            .lock()
            .unwrap()
            .insert(address, Signer::Trezor(signer));

        Ok(Self(address))
    }

    #[getter]
    pub fn get_private_key<'py>(&self, py: Python<'py>) -> Option<Bound<'py, PyBytes>> {
        let signers = SIGNERS
            .lock()
            .unwrap();
        let signer = signers.get(&self.0);

        signer.map(|s| {
            match s {
                Signer::SigningKey(signer) => Some(PyBytes::new(py, signer.to_bytes().as_slice())),
                _ => None
            }
        }).flatten()
    }

    #[pyo3(signature = (alias, password, keystore=None))]
    fn export_keystore(&self, py: Python, alias: &str, password: &str, keystore: Option<PathBuf>) -> PyResult<()> {
        let signers = SIGNERS
            .lock()
            .unwrap();
        let signer = signers.get(&self.0).ok_or(PyErr::new::<PyValueError, _>("No private key found"))?;

        match signer {
            Signer::SigningKey(signer) => {
                let keystore = match keystore {
                    Some(keystore) => keystore,
                    None => {
                        let py_objects = get_py_objects(py);
                        py_objects.get_config(py)?.getattr(intern!(py, "global_data_path"))?.extract::<PathBuf>()?.join("keystore/")
                    }
                };

                LocalSigner::encrypt_keystore(keystore, &mut rand::rngs::OsRng, signer.to_bytes().as_slice(), password, Some(format!("{}.json", alias).as_str()))
                    .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?;
                Ok(())
            }
            _ => Err(PyErr::new::<PyValueError, _>("Unsupported signer type"))
        }
    }
}

impl From<RevmAddress> for Address {
    fn from(address: RevmAddress) -> Self {
        Address(address)
    }
}

impl From<FixedBytes<20>> for Address {
    fn from(address: FixedBytes<20>) -> Self {
        Address(RevmAddress::from_slice(address.as_slice()))
    }
}
