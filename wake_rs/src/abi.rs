use crate::{
    abi_old::{py_to_alloy, Abi, AbiError},
    account::Account,
    address::Address,
    pytypes::{extract_abi_types, normalize_output},
    utils::{big_int_to_i256, big_uint_to_u256, get_py_objects, PyObjects},
};
use alloy::core::dyn_abi::{DynSolType, DynSolValue, Error as AlloyAbiError};
use alloy::primitives::keccak256;
use num_bigint::{BigInt, BigUint};
use pyo3::{types::PySequence, IntoPyObjectExt};
use pyo3::{
    exceptions::PyValueError,
    intern,
    prelude::*,
    types::{PyBool, PyByteArray, PyBytes, PyDict, PyList, PyInt, PyString, PyTuple, PyType},
    PyTypeInfo,
};
use revm::primitives::{B256, U256};

#[allow(non_camel_case_types)]
#[pyclass]
pub struct abi {}

#[pymethods]
impl abi {
    #[staticmethod]
    #[pyo3(signature = (*args))]
    fn encode<'py>(py: Python<'py>, args: &Bound<'py, PyTuple>) -> PyResult<Bound<'py, PyBytes>> {
        let py_objects = get_py_objects(py);
        let values: Result<Vec<_>, _> = args
            .iter()
            .map(|arg| normalize_input(py, &arg, None, py_objects))
            .collect();
        let tuple = DynSolValue::Tuple(values?);
        let encoded = tuple.abi_encode_sequence().unwrap();
        Ok(PyBytes::new(py, encoded.as_slice()))
    }

    #[staticmethod]
    #[pyo3(signature = (selector, *args))]
    fn encode_with_selector<'py>(
        py: Python<'py>,
        selector: &Bound<'py, PyAny>,
        args: &Bound<'py, PyTuple>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let py_objects = get_py_objects(py);
        let values: Result<Vec<_>, _> = args
            .iter()
            .map(|arg| normalize_input(py, &arg, None, py_objects))
            .collect();
        let tuple = DynSolValue::Tuple(values?);
        let encoded = tuple.abi_encode_sequence().unwrap();

        let mut result = Vec::with_capacity(4 + encoded.len());
        if let Ok(bytes) = selector.downcast::<PyBytes>() {
            result.extend_from_slice(&bytes.as_bytes()[..4]);
        } else if let Ok(bytearray) = selector.downcast::<PyByteArray>() {
            unsafe {
                result.extend_from_slice(&bytearray.as_bytes()[..4]);
            }
        } else {
            let bytes = selector
                .call_method0(intern!(py, "__bytes__"))?
                .downcast_into::<PyBytes>()?;
            result.extend_from_slice(&bytes.as_bytes()[..4]);
        };
        result.extend_from_slice(&encoded);

        Ok(PyBytes::new(py, result.as_slice()))
    }

    #[staticmethod]
    #[pyo3(signature = (signature, *args))]
    fn encode_with_signature<'py>(
        py: Python<'py>,
        signature: &Bound<'py, PyString>,
        args: &Bound<'py, PyTuple>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let py_objects = get_py_objects(py);
        let signature_str = signature.to_str()?;
        let stripped_signature = if let Some(index) = signature_str.find('(') {
            signature_str[index..].to_string()
        } else {
            return Err(PyErr::new::<PyValueError, _>("Invalid function signature"));
        };
        let alloy_type: DynSolType = stripped_signature
            .parse()
            .map_err(|e: AlloyAbiError| AbiError::new_err(e.to_string()))?;

        let values = match alloy_type {
            DynSolType::Tuple(types) => args
                .iter()
                .zip(types.iter())
                .map(|(arg, t)| normalize_input(py, &arg, Some(t), py_objects))
                .collect::<Result<Vec<_>, _>>()?,
            _ => {
                return Err(PyErr::new::<PyValueError, _>("Invalid function signature"));
            }
        };

        let tuple = DynSolValue::Tuple(values);
        let encoded = tuple.abi_encode_sequence().unwrap();

        let mut result = Vec::with_capacity(4 + encoded.len());
        let selector = keccak256(signature.to_str()?.as_bytes());
        result.extend_from_slice(&selector[..4]);
        result.extend_from_slice(&encoded);

        Ok(PyBytes::new(py, result.as_slice()))
    }

    #[staticmethod]
    fn encode_call<'py>(
        py: Python<'py>,
        func: &Bound<'py, PyAny>,
        args: Vec<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let py_objects = get_py_objects(py);
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
        Ok(PyBytes::new(py, result.as_slice()))
    }

    #[staticmethod]
    #[pyo3(signature = (*args))]
    fn encode_packed<'py>(
        py: Python<'py>,
        args: &Bound<'py, PyTuple>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let py_objects = get_py_objects(py);
        let values: Result<Vec<_>, _> = args
            .iter()
            .map(|arg| normalize_input(py, &arg, None, py_objects))
            .collect();
        let tuple = DynSolValue::Tuple(values?);
        let encoded = tuple.abi_encode_packed();
        Ok(PyBytes::new(py, encoded.as_slice()))
    }

    #[staticmethod]
    #[pyo3(signature = (data, types, *, chain=None))]
    fn decode<'py>(
        py: Python<'py>,
        data: &Bound<'py, PyAny>,
        types: &Bound<'py, PySequence>,
        chain: Option<Py<PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let tmp;

        let data = if let Ok(bytes) = data.downcast::<PyBytes>() {
            bytes.as_bytes()
        } else if let Ok(bytearray) = data.downcast::<PyByteArray>() {
            unsafe { bytearray.as_bytes() }
        } else {
            tmp = data
                .call_method0(intern!(py, "__bytes__"))?
                .downcast_into::<PyBytes>()?;
            tmp.as_bytes()
        };
        let py_objects = get_py_objects(py);
        let alloy_type = DynSolType::Tuple(
            types
                .try_iter()?
                .map(|t| t.and_then(|t| convert_type(py, &t, py_objects)))
                .collect::<Result<Vec<DynSolType>, _>>()?,
        );

        let decoded = alloy_type
            .abi_decode_sequence(data)
            .map_err(|e| AbiError::new_err(e.to_string()))?;

        let chain = match chain {
            Some(chain) => &chain.clone_ref(py),
            None => &py_objects.wake_detect_default_chain.call0(py)?,
        };

        if let DynSolValue::Tuple(ref tuple) = decoded {
            assert_eq!(tuple.len(), types.len()?);
            let mut tmp = tuple
                .iter()
                .zip(types.try_iter()?)
                .map(|(item, t)| {
                    t.and_then(|t| Ok(normalize_output(py, item, &t, &chain, py_objects)?))
                })
                .collect::<Result<Vec<PyObject>, _>>()?;

            if tmp.len() == 1 {
                Ok(tmp.pop().unwrap().into_bound(py))
            } else {
                PyTuple::new(py, tmp)?.into_bound_py_any(py)
            }
        } else {
            panic!("Decoded value is not a tuple");
        }
    }
}

// TODO function
fn convert_type(
    py: Python,
    value: &Bound<PyAny>,
    py_objects: &mut PyObjects,
) -> PyResult<DynSolType> {
    if value.is(&PyBool::type_object(py)) {
        Ok(DynSolType::Bool)
    } else if value.is(&PyBytes::type_object(py))
        || value.is(&PyByteArray::type_object(py))
    {
        Ok(DynSolType::Bytes)
    } else if value.is(&PyString::type_object(py)) {
        Ok(DynSolType::String)
    } else if value.is(&PyInt::type_object(py)) {
        // fallback for int used directly
        // does NOT cover IntEnum
        Ok(DynSolType::Int(256))
    } else if let Ok(pytype) = value.downcast::<PyType>() {
        if pytype.is_subclass(&Address::type_object(py))?
            || pytype.is_subclass(&Account::type_object(py))?
        {
            Ok(DynSolType::Address)
        } else if pytype.is_subclass(&py_objects.wake_integer.bind(py))? {
            let bits = value.getattr(intern!(py, "bits"))?.extract::<usize>()?;
            if value
                .getattr(intern!(py, "signed"))?
                .downcast::<PyBool>()?
                .is_true()
            {
                Ok(DynSolType::Int(bits))
            } else {
                Ok(DynSolType::Uint(bits))
            }
        } else if pytype.is_subclass(&py_objects.enums_int_enum.bind(py))? {
            Ok(DynSolType::Uint(8))
        } else if pytype.is_subclass(&py_objects.wake_fixed_bytes.bind(py))? {
            let length = value.getattr(intern!(py, "length"))?.extract::<usize>()?;
            Ok(DynSolType::FixedBytes(length))
        } else if py_objects
            .dataclasses_is_dataclass
            .call(py, (value.clone(),), None)?
            .downcast_bound::<PyBool>(py)?
            .is_true()
        {
            let hints = py_objects.get_type_hints(py, pytype.clone())?;
            let fields = py_objects
                .dataclasses_fields
                .call(py, (value.clone(),), None)?;
            let fields = fields.downcast_bound::<PyTuple>(py)?;

            let mut types = Vec::with_capacity(fields.len());
            for field in fields.iter() {
                let name = field
                    .getattr(intern!(py, "name"))?
                    .downcast_into::<PyString>()?
                    .to_string();
                let t = convert_type(py, &hints.get_item(name)?.unwrap(), py_objects)?;
                types.push(t);
            }
            Ok(DynSolType::Tuple(types))
        } else {
            panic!("Unsupported type: {:?}", value);
        }
    } else {
        // static and dynamic arrays
        let origin = py_objects
            .typing_get_origin
            .call(py, (value.clone(),), None)?;
        let origin = origin.bind(py);

        let inner_type = py_objects
            .typing_get_args
            .call(py, (value.clone(),), None)?
            .downcast_bound::<PyTuple>(py)?
            .get_item(0)?;

        if origin.is(&PyList::type_object(py)) {
            // ok
        } else if let Ok(origin) = origin.downcast::<PyType>() {
            if !origin.is_subclass(&py_objects.wake_fixed_list.bind(py))? {
                return Err(PyErr::new::<PyValueError, _>(format!(
                    "Unsupported type: {:?}",
                    value
                        .call_method0(intern!(py, "__repr__"))?
                        .extract::<String>()?
                )));
            }
        } else {
            return Err(PyErr::new::<PyValueError, _>(format!(
                "Unsupported type: {:?}",
                value
                    .call_method0(intern!(py, "__repr__"))?
                    .extract::<String>()?
            )));
        }

        if let Ok(length) = origin.getattr(intern!(py, "length")) {
            Ok(DynSolType::FixedArray(
                Box::new(convert_type(py, &inner_type, py_objects)?),
                length.extract::<usize>()?,
            ))
        } else {
            Ok(DynSolType::Array(Box::new(convert_type(
                py,
                &inner_type,
                py_objects,
            )?)))
        }
    }
}

// TODO enum, Contract
// TODO function
fn normalize_input(
    py: Python,
    value: &Bound<PyAny>,
    target_type: Option<&DynSolType>,
    py_objects: &mut PyObjects,
) -> PyResult<DynSolValue> {
    fn normalize_array(
        py: Python,
        array: &Bound<PyAny>,
        length: usize,
        py_objects: &mut PyObjects,
    ) -> PyResult<Vec<DynSolValue>> {
        let mut values = Vec::with_capacity(length);
        let mut item_type: Option<DynSolType> = None;
        let mut failed_items = Vec::new();

        for index in 0..length {
            match normalize_input(py, &array.get_item(index)?, item_type.as_ref(), py_objects) {
                Ok(value) => {
                    if let Some(t) = value.as_type() {
                        item_type = Some(t);
                    }
                    values.push(value);
                }
                Err(_) => {
                    // insert dummy value
                    values.push(DynSolValue::Bool(false));
                    failed_items.push(index);
                }
            }
        }

        if let Some(item_type) = &item_type {
            for index in failed_items {
                values[index] = normalize_input(
                    py,
                    &array.get_item(index)?,
                    Some(item_type),
                    py_objects,
                )?;
            }
        } else {
            if !failed_items.is_empty() {
                return Err(PyErr::new::<PyValueError, _>(
                    "Unable to infer type for all array elements",
                ));
            }
        }

        Ok(values)
    }

    if let Some(target_type) = target_type {
        return Ok(py_to_alloy(py, value, target_type, py_objects)?);
    }

    if let Ok(bool) = value.downcast::<PyBool>() {
        Ok(DynSolValue::Bool(bool.is_true()))
    } else if let Ok(str) = value.downcast::<PyString>() {
        Ok(DynSolValue::String(str.to_string()))
    } else if value.is_instance(py_objects.wake_fixed_bytes.bind(py))? {
        // must go before PyBytes check
        let length = value.getattr(intern!(py, "length"))?.extract::<usize>()?;
        let mut bytes = value
            .call_method0(intern!(py, "__bytes__"))?
            .downcast::<PyBytes>()?
            .as_bytes()
            .to_vec();
        bytes.resize(32, 0);
        Ok(DynSolValue::FixedBytes(B256::from_slice(&bytes), length))
    } else if let Ok(bytes) = value.downcast::<PyBytes>() {
        Ok(DynSolValue::Bytes(bytes.as_bytes().to_vec()))
    } else if let Ok(bytes_array) = value.downcast::<PyByteArray>() {
        Ok(DynSolValue::Bytes(unsafe {
            bytes_array.as_bytes().to_vec()
        }))
    } else if let Ok(tuple) = value.downcast::<PyTuple>() {
        let mut values = Vec::with_capacity(tuple.len());
        for item in tuple.iter() {
            values.push(normalize_input(py, &item, None, py_objects)?);
        }
        Ok(DynSolValue::Tuple(values))
    } else if value // must go before PyList check
        .is_instance(py_objects.wake_fixed_list.bind(py))?
    {
        let length = value.getattr(intern!(py, "length"))?.extract::<usize>()?;
        Ok(DynSolValue::FixedArray(normalize_array(
            py, value, length, py_objects,
        )?))
    } else if let Ok(array) = value.downcast::<PyList>() {
        Ok(DynSolValue::Array(normalize_array(
            py,
            array,
            array.len(),
            py_objects,
        )?))
    } else if let Ok(address) = value.downcast::<Address>() {
        Ok(DynSolValue::Address(address.borrow().0))
    } else if let Ok(account) = value.downcast::<Account>() {
        Ok(DynSolValue::Address(account.borrow().address.borrow(py).0))
    } else if value.is_instance(py_objects.wake_integer.bind(py))? {
        let bits = value.getattr(intern!(py, "bits"))?.extract::<usize>()?;
        if value
            .getattr(intern!(py, "signed"))?
            .downcast::<PyBool>()?
            .is_true()
        {
            let int = value.extract::<BigInt>()?;
            Ok(DynSolValue::Int(big_int_to_i256(int), bits))
        } else {
            let uint = value.extract::<BigUint>()?;
            Ok(DynSolValue::Uint(big_uint_to_u256(uint), bits))
        }
    } else if value.is_instance(py_objects.enums_int_enum.bind(py))? {
        let int = value.extract::<usize>()?;
        Ok(DynSolValue::Uint(U256::from(int), 8))
    } else if py_objects
        .dataclasses_is_dataclass
        .call(py, (value.clone(),), None)?
        .extract::<bool>(py)?
    {
        let hints = py_objects.get_type_hints(py, value.get_type())?;
        let fields = py_objects
            .dataclasses_fields
            .call(py, (value.clone(),), None)?;
        let fields = fields.downcast_bound::<PyTuple>(py)?;

        let mut values = Vec::with_capacity(fields.len());
        for field in fields.iter() {
            let name = field
                .getattr(intern!(py, "name"))?
                .downcast_into::<PyString>()?;
            let t = convert_type(py, &hints.get_item(name.clone())?.unwrap(), py_objects)?;

            values.push(normalize_input(
                py,
                &value.getattr(name)?,
                Some(&t),
                py_objects,
            )?);
        }

        Ok(DynSolValue::Tuple(values))
    } else {
        Err(PyErr::new::<PyValueError, _>(format!(
            "Unsupported type for abi encoding: {:?}",
            value
                .call_method0(intern!(py, "__repr__"))?
                .extract::<String>()?
        )))
    }
}
