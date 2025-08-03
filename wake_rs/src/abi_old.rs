use alloy::core::dyn_abi::{DynSolType, DynSolValue, Error as AlloyAbiError};
use alloy::core::primitives::{FixedBytes, Function, Keccak256};
use num_bigint::{BigInt, BigUint};
use pyo3::exceptions::{PyException, PyValueError};
use pyo3::{intern, prelude::*, IntoPyObjectExt};
use pyo3::create_exception;
use pyo3::types::{PyBool, PyByteArray, PyBytes, PyDict, PyList, PyString, PyTuple};

use crate::address::Address;
use crate::enums::AddressEnum;
use crate::pytypes::extract_abi_types;
use crate::utils::{big_int_to_i256, big_uint_to_u256, get_py_objects, PyObjects};

create_exception!("wake.development.core", AbiError, PyException);

#[pyclass(module = "wake.development.core")]
pub struct Abi {}

impl Abi {
    pub(crate) fn encode<'py>(py: Python<'py>, types: Vec<String>, data: Vec<Bound<'py, PyAny>>, py_objects: &PyObjects) -> PyResult<Vec<u8>> {
        let alloy_type: DynSolType = format!("({})", types.join(",")).parse().map_err(|e: AlloyAbiError| AbiError::new_err(e.to_string()))?;
        let converted = py_to_alloy(py, PyTuple::new(py, data)?.as_any(), &alloy_type, py_objects)?;

        Ok(converted.abi_encode_sequence().unwrap())
    }

    pub(crate) fn encode_with_selector<'py>(
        py: Python<'py>,
        selector: Vec<u8>,
        types: Vec<String>,
        data: Vec<Bound<'py, PyAny>>,
        py_objects: &PyObjects,
    ) -> PyResult<Vec<u8>> {
        let alloy_type: DynSolType = format!("({})", types.join(",")).parse().map_err(|e: AlloyAbiError| AbiError::new_err(e.to_string()))?;
        let converted = py_to_alloy(py, PyTuple::new(py, data)?.as_any(), &alloy_type, py_objects)?;

        let encoded = converted.abi_encode_sequence().unwrap();
        let mut result = Vec::with_capacity(4 + encoded.len());
        result.extend_from_slice(&selector);
        result.extend_from_slice(&encoded);

        Ok(result)
    }

    pub(crate) fn encode_with_signature<'py>(
        py: Python<'py>,
        signature: &str,
        types: Vec<String>,
        data: Vec<Bound<'py, PyAny>>,
        py_objects: &PyObjects,
    ) -> PyResult<Vec<u8>> {
        let alloy_type: DynSolType = format!("({})", types.join(",")).parse().map_err(|e: AlloyAbiError| AbiError::new_err(e.to_string()))?;
        let converted = py_to_alloy(py, PyTuple::new(py, data)?.as_any(), &alloy_type, py_objects)?;

        let mut hasher = Keccak256::new();
        hasher.update(signature.as_bytes());
        let selector = hasher.finalize();
        let encoded = converted.abi_encode_sequence().unwrap();

        let mut result = Vec::with_capacity(4 + encoded.len());
        result.extend_from_slice(&selector[..4]);
        result.extend_from_slice(&encoded);

        Ok(result)
    }

    pub(crate) fn encode_packed<'py>(
        py: Python<'py>,
        types: Vec<String>,
        data: Vec<Bound<'py, PyAny>>,
        py_objects: &PyObjects,
    ) -> PyResult<Vec<u8>> {
        let alloy_type: DynSolType = format!("({})", types.join(",")).parse().map_err(|e: AlloyAbiError| AbiError::new_err(e.to_string()))?;
        let converted = py_to_alloy(py, PyTuple::new(py, data)?.as_any(), &alloy_type, py_objects)?;

        Ok(converted.abi_encode_packed())
    }

    pub(crate) fn encode_call<'py>(
        py: Python<'py>,
        func: &Bound<'py, PyAny>,
        args: Vec<Bound<'py, PyAny>>,
        py_objects: &PyObjects,
    ) -> PyResult<Vec<u8>> {
        let selector = func
            .getattr(intern!(py, "selector"))?
            .downcast_into::<PyBytes>()?;
        let contract =
            py_objects
                .wake_get_class_that_defined_method
                .call(py, (func,), None)?;
        let contract = contract.bind(py);
        let abi = contract
            .getattr(intern!(py, "_abi"))?
            .downcast_into::<PyDict>()?
            .get_item(selector.clone())?
            .expect("selector not found in abi")
            .downcast_into::<PyDict>()?;
        let types = extract_abi_types(py, &abi, intern!(py, "inputs"))?;

        let encoded = Abi::encode(py, types, args, py_objects)?;
        let mut result = Vec::with_capacity(4 + encoded.len());
        result.extend_from_slice(&selector.as_bytes()[..4]);
        result.extend_from_slice(&encoded);

        Ok(result)
    }

    pub(crate) fn decode<'py>(py: Python<'py>, types: Vec<String>, data: Vec<u8>, py_objects: &PyObjects) -> PyResult<PyObject> {
        let alloy_type: DynSolType = format!("({})", types.join(",")).parse().map_err(|e: AlloyAbiError| AbiError::new_err(e.to_string()))?;
        let decoded = alloy_type.abi_decode_sequence(data.as_slice()).map_err(|e| AbiError::new_err(e.to_string()))?;

        alloy_to_py(py, &decoded, py_objects)
    }
}

#[pymethods]
impl Abi {
    #[staticmethod]
    #[pyo3(name = "encode")]
    fn encode_py<'py>(
        py: Python<'py>,
        types: Vec<String>,
        data: Vec<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        Ok(PyBytes::new(py, Self::encode(py, types, data, get_py_objects(py))?.as_slice()))
    }

    #[staticmethod]
    #[pyo3(name = "encode_with_selector")]
    fn encode_with_selector_py<'py>(
        py: Python<'py>,
        selector: Vec<u8>,
        types: Vec<String>,
        data: Vec<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        Ok(PyBytes::new(
            py,
            Self::encode_with_selector(py, selector, types, data, get_py_objects(py))?.as_slice(),
        ))
    }

    #[staticmethod]
    #[pyo3(name = "encode_with_signature")]
    fn encode_with_signature_py<'py>(
        py: Python<'py>,
        signature: &str,
        types: Vec<String>,
        data: Vec<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        Ok(PyBytes::new(
            py,
            Self::encode_with_signature(py, signature, types, data, get_py_objects(py))?.as_slice(),
        ))
    }

    #[staticmethod]
    #[pyo3(name = "encode_packed")]
    fn encode_packed_py<'py>(
        py: Python<'py>,
        types: Vec<String>,
        data: Vec<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        Ok(PyBytes::new(py, Self::encode_packed(py, types, data, get_py_objects(py))?.as_slice()))
    }
    #[staticmethod]
    #[pyo3(name = "encode_call")]
    fn encode_call_py<'py>(
        py: Python<'py>,
        func: &Bound<'py, PyAny>,
        args: Vec<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        Ok(PyBytes::new(py, Self::encode_call(py, func, args, get_py_objects(py))?.as_slice()))
    }

    #[staticmethod]
    #[pyo3(name = "decode")]
    fn decode_py<'py>(py: Python<'py>, types: Vec<String>, data: Vec<u8>) -> PyResult<PyObject> {
        Ok(Self::decode(py, types, data, get_py_objects(py))?)
    }
}

pub(crate) fn alloy_to_py(py: Python<'_>, value: &DynSolValue, py_objects: &PyObjects) -> PyResult<PyObject> {
    match value {
        DynSolValue::Address(v) => Address::from(*v).into_py_any(py),
        DynSolValue::Bytes(v) => PyBytes::new(py, v.as_slice()).into_py_any(py),
        DynSolValue::Int(v, bits) => {
            let int = BigInt::from_signed_bytes_le(&v.to_le_bytes::<32>()).into_pyobject(py)?;
            py_objects.wake_int_map.bind(py).get_item(bits)?.unwrap().call1((int,))?.into_py_any(py)
        }
        DynSolValue::Uint(v, bits) => {
            let uint = BigUint::from_bytes_le(v.as_le_slice());
            py_objects.wake_uint_map.bind(py).get_item(bits)?.unwrap().call1((uint,))?.into_py_any(py)
        }
        DynSolValue::Bool(v) => v.into_py_any(py),
        DynSolValue::String(v) => v.into_py_any(py),
        DynSolValue::FixedBytes(v, size) => {
            let bytes = &v.as_slice()[..*size];
            py_objects.wake_fixed_bytes_map.bind(py).get_item(size)?.unwrap().call1((bytes,))?.into_py_any(py)
        }
        DynSolValue::FixedArray(v) => {
            let values = v.into_iter().map(|v| alloy_to_py(py, &v, py_objects)).collect::<Result<Vec<_>, _>>()?;

            if v.len() <= 32 {
                py_objects.wake_fixed_list_map.bind(py).get_item(v.len())?.unwrap().call1((values,))?.into_py_any(py)
            } else {
                py_objects.wake_new_fixed_list.bind(py).call1((v.len(), values))?.into_py_any(py)
            }
        }
        DynSolValue::Array(v) => PyList::new(py, v
            .into_iter()
            .map(|v| alloy_to_py(py, v, py_objects))
            .collect::<Result<Vec<_>, _>>()?)?.into_py_any(py),
        DynSolValue::Tuple(v) => PyTuple::new(py, v
            .into_iter()
            .map(|v| alloy_to_py(py, v, py_objects))
            .collect::<Result<Vec<_>, _>>()?)?.into_py_any(py),
        DynSolValue::Function(v) => {
            py_objects.wake_fixed_bytes_map.bind(py).get_item(24)?.unwrap().call1((v.as_slice(),))?.into_py_any(py)
        }
        DynSolValue::CustomStruct {
            name: _,
            prop_names: _,
            tuple: _,
        } => panic!("Custom struct not supported"),
    }
}

pub(crate) fn py_to_alloy(py: Python<'_>, value: &Bound<PyAny>, t: &DynSolType, py_objects: &PyObjects) -> PyResult<DynSolValue> {
    match t {
        DynSolType::Address => {
            let address = value.extract::<AddressEnum>()?;
            return Ok(DynSolValue::Address(address.try_into()?));
        }
        DynSolType::Array(arr) => {
            if let Ok(v) = value.downcast::<PyList>() {
                let mut values = Vec::with_capacity(v.len());
                for v in v.iter() {
                    values.push(py_to_alloy(py, &v, &**arr, py_objects)?);
                }
                return Ok(DynSolValue::Array(values));
            } else if let Ok(v) = value.downcast::<PyTuple>() {
                let mut values = Vec::with_capacity(v.len());
                for v in v.iter() {
                    values.push(py_to_alloy(py, &v, &**arr, py_objects)?);
                }
                return Ok(DynSolValue::Array(values));
            } else {
                let v = value.extract::<Vec<PyObject>>()?;

                let mut values = Vec::with_capacity(v.len());
                for v in v {
                    values.push(py_to_alloy(py, v.bind(py), &**arr, py_objects)?);
                }
                return Ok(DynSolValue::Array(values));
            }
        }
        DynSolType::Bool => {
            let bool = value.downcast::<PyBool>()?;
            return Ok(DynSolValue::Bool(bool.is_true()));
        }
        DynSolType::Bytes => {
            let bytes: Vec<u8> = if let Ok(b) = value.downcast::<PyBytes>() {
                b.as_bytes().to_vec()
            } else if let Ok(b) = value.downcast::<PyByteArray>() {
                b.to_vec()
            } else {
                value.call_method0(intern!(py, "__bytes__"))?.downcast_into::<PyBytes>()?.as_bytes().to_vec()
            };
            return Ok(DynSolValue::Bytes(bytes));
        }
        DynSolType::FixedArray(arr, _size) => {
            if let Ok(v) = value.downcast::<PyTuple>() {
                let mut values = Vec::with_capacity(v.len());
                for v in v.iter() {
                    values.push(py_to_alloy(py, &v, &**arr, py_objects)?);
                }
                return Ok(DynSolValue::FixedArray(values));
            } else if let Ok(v) = value.downcast::<PyList>() {
                let mut values = Vec::with_capacity(v.len());
                for v in v.iter() {
                    values.push(py_to_alloy(py, &v, &**arr, py_objects)?);
                }
                return Ok(DynSolValue::FixedArray(values));
            } else {
                let v = value.extract::<Vec<PyObject>>()?;

                let mut values = Vec::with_capacity(v.len());
                for v in v {
                    values.push(py_to_alloy(py, v.bind(py), &**arr, py_objects)?);
                }

                return Ok(DynSolValue::FixedArray(values));
            }
        }
        DynSolType::FixedBytes(size) => {
            let mut bytes = if let Ok(b) = value.downcast::<PyBytes>() {
                b.as_bytes().to_vec()
            } else if let Ok(b) = value.downcast::<PyByteArray>() {
                b.to_vec()
            } else {
                value.call_method0(intern!(py, "__bytes__"))?.downcast_into::<PyBytes>()?.as_bytes().to_vec()
            };

            bytes.resize(32, 0);
            return Ok(DynSolValue::FixedBytes(FixedBytes::from_slice(bytes.as_slice()), *size));
        }
        DynSolType::Function => {
            // TODO callable?
            let tmp;
            let bytes = if let Ok(b) = value.downcast::<PyBytes>() {
                b.as_bytes()
            } else if let Ok(b) = value.downcast::<PyByteArray>() {
                unsafe {
                    b.as_bytes()
                }
            } else {
                tmp = value.call_method0(intern!(py, "__bytes__"))?.downcast_into::<PyBytes>()?;
                tmp.as_bytes()
            };

            let function = Function::try_from(bytes).map_err(|_| {
                PyValueError::new_err(format!("cannot convert bytes of length {} to {} represented by 24 bytes", bytes.len(), "function"))
            })?;
            return Ok(DynSolValue::Function(function));
        }
        DynSolType::String => {
            let string = value.downcast::<PyString>()?.to_string();
            return Ok(DynSolValue::String(string));
        }
        DynSolType::Tuple(tuple) => {
            if let Ok(v) = value.downcast::<PyTuple>() {
                let mut values = Vec::with_capacity(v.len());
                for (t, v) in tuple.iter().zip(v.iter()) {
                    values.push(py_to_alloy(py, &v, t, py_objects)?);
                }
                return Ok(DynSolValue::Tuple(values));
            } else if let Ok(v) = value.downcast::<PyList>() {
                let mut values = Vec::with_capacity(v.len());
                for (t, v) in tuple.iter().zip(v.iter()) {
                    values.push(py_to_alloy(py, &v, t, py_objects)?);
                }
                return Ok(DynSolValue::Tuple(values));
            } else if py_objects.dataclasses_is_dataclass.call1(py, (value,))?.downcast_bound::<PyBool>(py)?.is_true() {
                let fields = py_objects
                    .dataclasses_fields
                    .bind(py)
                    .call1((value,))?
                    .downcast_into::<PyTuple>()?;
                let mut values = Vec::with_capacity(fields.len());

                for (t, field) in tuple.iter().zip(fields.iter()) {
                    let name = field.getattr("name")?.downcast_into::<PyString>()?;
                    let value = value.getattr(name)?;
                    values.push(py_to_alloy(py, &value, t, py_objects)?);
                }

                return Ok(DynSolValue::Tuple(values));
            } else {
                let iterable = value.extract::<Vec<PyObject>>()?;
                let mut values = Vec::with_capacity(iterable.len());
                for (i, v) in iterable.iter().enumerate() {
                    values.push(py_to_alloy(py, v.bind(py), tuple.get(i).unwrap(), py_objects)?);
                }
                return Ok(DynSolValue::Tuple(values));
            }
        }
        DynSolType::Int(size) => {
            let num = value.extract::<BigInt>()?;
            return Ok(DynSolValue::Int(big_int_to_i256(num), *size));
        }
        DynSolType::Uint(size) => {
            let num = value.extract::<BigUint>()?;
            return Ok(DynSolValue::Uint(big_uint_to_u256(num), *size));
        }
        DynSolType::CustomStruct {
            name: _,
            prop_names: _,
            tuple: _,
        } => panic!("Custom struct not supported"),
    }
}
