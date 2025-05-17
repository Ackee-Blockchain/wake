use std::collections::HashMap;

use alloy::rpc::types::Header;
use alloy::signers::local::coins_bip39::{ChineseSimplified, ChineseTraditional, Czech, English, French, Italian, Japanese, Korean, Mnemonic, Portuguese, Spanish};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use num_bigint::{BigInt, BigUint};
use pyo3::intern;
use pyo3::sync::GILOnceCell;
use pyo3::types::{PyByteArray, PyBytes, PyDict, PyFunction, PyList, PyType};
use alloy::primitives::keccak256 as alloy_keccak256;
use rand::rngs::OsRng;
use revm::context::BlockEnv;
use revm::context_interface::block::BlobExcessGasAndPrice;
use revm::primitives::{Address as RevmAddress, I256, U256};

use crate::enums::AddressEnum;
static mut PY_FUNCTIONS: GILOnceCell<PyObjects> = GILOnceCell::new();

#[allow(static_mut_refs)]
pub(crate) fn get_py_objects(py: Python<'_>) -> &mut PyObjects {
    unsafe {
        if let Some(objects) = PY_FUNCTIONS.get_mut() {
            return objects;
        }

        PY_FUNCTIONS.get_or_init(py, || PyObjects {
            type_hints_cache: HashMap::new(),
            typing_get_origin: py
                .import("typing_extensions")
                .unwrap()
                .getattr("get_origin")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            typing_get_args: py
                .import("typing_extensions")
                .unwrap()
                .getattr("get_args")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            typing_get_type_hints: py
                .import("typing_extensions")
                .unwrap()
                .getattr("get_type_hints")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            dataclasses_is_dataclass: py
                .import("dataclasses")
                .unwrap()
                .getattr("is_dataclass")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            dataclasses_fields: py
                .import("dataclasses")
                .unwrap()
                .getattr("fields")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            enums_int_enum: py
                .import("enum")
                .unwrap()
                .getattr("IntEnum")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_integer: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("Integer")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_fixed_bytes: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("FixedSizeBytes")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_fixed_list: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("FixedSizeList")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_u256: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("uint256")
                .unwrap()
                .unbind(),
            wake_errors: py
                .import("wake.development.core")
                .unwrap()
                .getattr("errors")
                .unwrap()
                .downcast_into::<PyDict>()
                .unwrap()
                .unbind(),
            wake_halt_exception: py
                .import("wake.development.transactions")
                .unwrap()
                .getattr("Halt")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_unknown_revert_exception: py
                .import("wake.development.transactions")
                .unwrap()
                .getattr("UnknownRevertError")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_external_error: py
                .import("wake.development.transactions")
                .unwrap()
                .getattr("ExternalError")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_events: py
                .import("wake.development.core")
                .unwrap()
                .getattr("events")
                .unwrap()
                .downcast_into::<PyDict>()
                .unwrap()
                .unbind(),
            wake_unknown_event: py
                .import("wake.development.internal")
                .unwrap()
                .getattr("UnknownEvent")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_external_event: py
                .import("wake.development.internal")
                .unwrap()
                .getattr("ExternalEvent")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_uint_map: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("uint_map")
                .unwrap()
                .downcast_into::<PyDict>()
                .unwrap()
                .unbind(),
            wake_int_map: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("int_map")
                .unwrap()
                .downcast_into::<PyDict>()
                .unwrap()
                .unbind(),
            wake_fixed_bytes_map: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("fixed_bytes_map")
                .unwrap()
                .downcast_into::<PyDict>()
                .unwrap()
                .unbind(),
            wake_fixed_list_map: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("fixed_list_map")
                .unwrap()
                .downcast_into::<PyDict>()
                .unwrap()
                .unbind(),
            wake_new_fixed_list: py
                .import("wake.development.primitive_types")
                .unwrap()
                .getattr("new_fixed_list")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            wake_contracts_by_metadata: py
                .import("wake.development.core")
                .unwrap()
                .getattr("contracts_by_metadata")
                .unwrap()
                .downcast_into::<PyDict>()
                .unwrap()
                .unbind(),
            wake_get_class_that_defined_method: py
                .import("wake.utils")
                .unwrap()
                .getattr("get_class_that_defined_method")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            wake_detect_default_chain: py
                .import("wake.development.core")
                .unwrap()
                .getattr("detect_default_chain")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            wake_random: py
                .import("wake.development.globals")
                .unwrap()
                .getattr("random")
                .unwrap()
                .unbind(),
            wake_get_config: py
                .import("wake.development.globals")
                .unwrap()
                .getattr("get_config")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            wake_wei: py
                .import("wake.development.core")
                .unwrap()
                .getattr("Wei")
                .unwrap()
                .unbind(),
            wake_call_trace: py
                .import("wake.development.call_trace")
                .unwrap()
                .getattr("CallTrace")
                .unwrap()
                .downcast_into::<PyType>()
                .unwrap()
                .unbind(),
            wake_connected_chains: py
                .import("wake.testing.core")
                .unwrap()
                .getattr("connected_chains")
                .unwrap()
                .downcast_into::<PyList>()
                .unwrap()
                .unbind(),
            wake_get_name_abi: py
                .import("wake.development.utils")
                .unwrap()
                .getattr("get_name_abi_from_explorer_cached")
                .unwrap()
                .unbind(),
            click_prompt: py
                .import("click")
                .unwrap()
                .getattr("prompt")
                .unwrap()
                .downcast_into::<PyFunction>()
                .unwrap()
                .unbind(),
            hardhat_console_abi: py
                .import("wake.development.hardhat_console")
                .unwrap()
                .getattr("abis")
                .unwrap()
                .downcast_into::<PyDict>()
                .unwrap()
                .unbind(),
        });

        PY_FUNCTIONS.get_mut().unwrap()
    }
}

pub(crate) struct PyObjects {
    pub typing_get_origin: Py<PyFunction>,
    pub typing_get_args: Py<PyFunction>,
    pub typing_get_type_hints: Py<PyFunction>,
    pub dataclasses_is_dataclass: Py<PyFunction>,
    pub dataclasses_fields: Py<PyFunction>,
    pub enums_int_enum: Py<PyType>,
    pub wake_integer: Py<PyType>,
    pub wake_fixed_bytes: Py<PyType>,
    pub wake_fixed_list: Py<PyType>,
    pub wake_u256: Py<PyAny>,
    pub wake_errors: Py<PyDict>,
    pub wake_halt_exception: Py<PyType>,
    pub wake_unknown_revert_exception: Py<PyType>,
    pub wake_external_error: Py<PyType>,
    pub wake_events: Py<PyDict>,
    pub wake_unknown_event: Py<PyType>,
    pub wake_external_event: Py<PyType>,
    pub wake_uint_map: Py<PyDict>,
    pub wake_int_map: Py<PyDict>,
    pub wake_fixed_bytes_map: Py<PyDict>,
    pub wake_fixed_list_map: Py<PyDict>,
    pub wake_new_fixed_list: Py<PyFunction>,
    pub wake_contracts_by_metadata: Py<PyDict>,
    pub wake_get_class_that_defined_method: Py<PyFunction>,
    pub wake_detect_default_chain: Py<PyFunction>,
    pub wake_random: Py<PyAny>,
    pub wake_get_config: Py<PyFunction>,
    pub wake_wei: Py<PyAny>,
    pub wake_call_trace: Py<PyType>,
    pub wake_connected_chains: Py<PyList>,
    pub wake_get_name_abi: Py<PyAny>,
    pub click_prompt: Py<PyFunction>,
    pub hardhat_console_abi: Py<PyDict>,

    type_hints_cache: HashMap<String, Py<PyDict>>,
}

impl PyObjects {
    pub fn get_type_hints<'py>(&mut self, py: Python<'py>, obj: Bound<PyType>) -> PyResult<Bound<'py, PyDict>> {
        if let Some(hints) = self.type_hints_cache.get(obj.fully_qualified_name()?.to_str()?) {
            return Ok(hints.bind(py).clone());
        }

        let kwargs = PyDict::new(py);
        kwargs.set_item(intern!(py, "include_extras"), true)?;

        let hints = self.typing_get_type_hints.call(py, (obj.clone(),), Some(&kwargs))?;
        let hints = hints.downcast_bound::<PyDict>(py)?;
        self.type_hints_cache.insert(obj.fully_qualified_name()?.to_string(), hints.clone().unbind());
        Ok(hints.clone())
    }

    pub fn get_config<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.wake_get_config.bind(py).call0()
    }
}

pub(crate) fn big_int_to_i256(int: BigInt) -> I256 {
    let bytes = int.to_signed_bytes_le();
    let mut fixed_bytes = [0u8; 32];
    let len = bytes.len().min(32);
    fixed_bytes[..len].copy_from_slice(&bytes[..len]);

    // Apply sign extension
    if int.sign() == num_bigint::Sign::Minus && len < 32 {
        for byte in &mut fixed_bytes[len..] {
            *byte = 0xFF;
        }
    }

    I256::try_from_le_slice(&fixed_bytes).unwrap()
}

pub(crate) fn big_uint_to_u256(int: BigUint) -> U256 {
    U256::try_from_le_slice(&int.to_bytes_le()).unwrap()
}

pub(crate) fn header_to_block_env(header: Header) -> BlockEnv {
    let blob_info = if let Some(excess_blob_gas) = header.excess_blob_gas {
        Some(BlobExcessGasAndPrice::new(excess_blob_gas.try_into().unwrap(), false)) // TODO!!
    } else {
        None
    };

    BlockEnv {
        number: header.number,
        beneficiary: header.beneficiary,
        timestamp: header.timestamp,
        gas_limit: header.gas_limit,
        basefee: header.base_fee_per_gas.unwrap_or(0),
        difficulty: header.difficulty,
        prevrandao: Some(header.mix_hash), // TODO!!
        blob_excess_gas_and_price: blob_info,
    }
}

#[pyfunction]
pub fn keccak256<'py>(py: Python<'py>, data: &Bound<PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let b = if let Ok(bytes) = data.downcast::<PyBytes>() {
        alloy_keccak256(bytes.as_bytes())
    } else if let Ok(bytearray) = data.downcast::<PyByteArray>() {
        unsafe {
            alloy_keccak256(bytearray.as_bytes())
        }
    } else {
        let bytes = data.call_method0(intern!(py, "__bytes__"))?;
        let bytes = bytes.downcast::<PyBytes>().unwrap().as_bytes();
        alloy_keccak256(bytes)
    };

    let py_objects = get_py_objects(py);
    py_objects.wake_fixed_bytes_map.bind(py).get_item(32)?.unwrap().call1((b.as_slice(),))
}


#[pyfunction(signature = (words=12, language="english"))]
pub fn new_mnemonic(words: usize, language: &str) -> PyResult<String> {
    Ok(match language {
        "english" => Mnemonic::<English>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "chinese_simplified" => Mnemonic::<ChineseSimplified>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "chinese_traditional" => Mnemonic::<ChineseTraditional>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "czech" => Mnemonic::<Czech>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "french" => Mnemonic::<French>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "italian" => Mnemonic::<Italian>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "japanese" => Mnemonic::<Japanese>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "korean" => Mnemonic::<Korean>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "portuguese" => Mnemonic::<Portuguese>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        "spanish" => Mnemonic::<Spanish>::new_with_count(&mut OsRng, words).map(|m| m.to_phrase()),
        _ => return Err(PyErr::new::<PyValueError, _>("Invalid language")),
    }.map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?)
}

#[pyfunction]
pub fn to_checksum_address(address: AddressEnum) -> PyResult<String> {
    let addr: RevmAddress = address.try_into()?;
    Ok(addr.to_checksum(None))
}
