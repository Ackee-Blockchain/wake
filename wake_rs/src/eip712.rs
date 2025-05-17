use std::borrow::Cow;

use alloy::{
    dyn_abi::{Eip712Domain, PropertyDef, Resolver, TypeDef, TypedData},
};
use num_bigint::{BigInt, BigUint};
use pyo3::{
    exceptions::PyValueError,
    intern,
    prelude::*,
    types::{PyBool, PyByteArray, PyBytes, PyDict, PyList, PyString, PyTuple, PyType},
    PyTypeInfo,
};
use revm::primitives::Address as RevmAddress;
use revm::primitives::B256;

use crate::{
    account::Account,
    address::Address,
    enums::AddressEnum,
    utils::{big_uint_to_u256, PyObjects},
};

pub(crate) fn py_to_eip712(
    py: Python,
    obj: &Bound<PyAny>,
    domain: &Bound<PyDict>,
    py_objects: &mut PyObjects,
) -> PyResult<TypedData> {
    let mut resolver = Resolver::default();

    // must be dataclass
    let (primary_type, message) = process_dataclass(py, obj, &mut resolver, py_objects)?;

    let name = domain
        .get_item(intern!(py, "name"))?
        .map(|v| v.extract::<String>())
        .transpose()?
        .map(Cow::Owned);

    let version = domain
        .get_item(intern!(py, "version"))?
        .map(|v| v.extract::<String>())
        .transpose()?
        .map(Cow::Owned);

    let chain_id = domain
        .get_item(intern!(py, "chainId"))?
        .map(|v| v.extract::<BigUint>())
        .transpose()?
        .map(|v| big_uint_to_u256(v));

    let verifying_contract = domain
        .get_item(intern!(py, "verifyingContract"))?
        .map(|v| v.extract::<AddressEnum>())
        .transpose()?
        .map(|v| v.try_into())
        .map(|v| v)
        .transpose()?;

    let salt = match domain.get_item(intern!(py, "salt"))? {
        Some(v) => {
            if let Ok(bytes) = v.downcast::<PyBytes>() {
                Some(B256::from_slice(bytes.as_bytes()))
            } else if let Ok(bytearray) = v.downcast::<PyByteArray>() {
                Some(B256::from_slice(unsafe { bytearray.as_bytes() }))
            } else {
                let bytes = v.call_method0(intern!(py, "__bytes__"))?;
                Some(B256::from_slice(bytes.downcast::<PyBytes>()?.as_bytes()))
            }
        }
        None => None,
    };

    Ok(TypedData {
        domain: Eip712Domain {
            name,
            version,
            chain_id,
            verifying_contract,
            salt,
        },
        resolver,
        primary_type,
        message,
    })
}

// same as convert but does not convert the value
// todo function
fn pytype_to_abi_type(
    py: Python,
    pytype: &Bound<PyAny>,
    resolver: &mut Resolver,
    py_objects: &mut PyObjects,
) -> PyResult<String> {
    if pytype.is(&PyBool::type_object(py)) {
        Ok("bool".into())
    } else if pytype.is(&PyBytes::type_object(py))
        || pytype.is(&PyByteArray::type_object(py))
    {
        Ok("bytes".into())
    } else if pytype.is(&PyString::type_object(py)) {
        Ok("string".into())
    } else if let Ok(pytype) = pytype.downcast::<PyType>() {
        if pytype.is_subclass(&Address::type_object(py))?
            || pytype.is_subclass(&Account::type_object(py))?
        {
            Ok("address".into())
        } else if pytype.is_subclass(&py_objects.wake_integer.bind(py))? {
            let bits = pytype.getattr(intern!(py, "bits"))?.extract::<usize>()?;
            if pytype
                .getattr(intern!(py, "signed"))?
                .downcast::<PyBool>()?
                .is_true()
            {
                Ok(format!("int{}", bits))
            } else {
                Ok(format!("uint{}", bits))
            }
        } else if pytype.is_subclass(&py_objects.enums_int_enum.bind(py))? {
            Ok("uint8".into())
        } else if pytype.is_subclass(&py_objects.wake_fixed_bytes.bind(py))? {
            let length = pytype.getattr(intern!(py, "length"))?.extract::<usize>()?;
            Ok(format!("bytes{}", length))
        } else if py_objects
            .dataclasses_is_dataclass
            .call(py, (pytype.clone(),), None)?
            .downcast_bound::<PyBool>(py)?
            .is_true()
        {
            let type_name = pytype.getattr(intern!(py, "original_name")).map_or(
                pytype.getattr(intern!(py, "__name__"))?.extract::<String>(),
                |n| n.extract::<String>(),
            )?;

            let hints = py_objects.get_type_hints(py, pytype.clone())?;
            let fields = py_objects
                .dataclasses_fields
                .call(py, (pytype,), None)?;
            let fields = fields.downcast_bound::<PyTuple>(py)?;

            let mut props = Vec::with_capacity(fields.len());

            for field in fields.iter() {
                let name = field
                    .getattr(intern!(py, "name"))?
                    .downcast_into::<PyString>()?;
                let original_name = field
                    .getattr(intern!(py, "original_name"))
                    .map_or(Ok(name.clone()), |n| n.downcast_into::<PyString>())?;
                let pytype = hints.get_item(name)?.unwrap();

                let t = pytype_to_abi_type(py, &pytype, resolver, py_objects)?;
                props.push(PropertyDef::new_unchecked(t, original_name.to_string()));
            }

            resolver.ingest(TypeDef::new_unchecked(type_name.clone(), props));

            Ok(type_name)
        } else {
            Err(PyErr::new::<PyValueError, _>(format!(
                "Unexpected type for EIP-712: {:?}",
                pytype
            )))
        }
    } else {
        let origin = py_objects.typing_get_origin.call1(py, (pytype,))?;
        let origin = origin.bind(py);

        if origin.is(&PyList::type_object(py)) {
            let inner_type = py_objects
                .typing_get_args
                .call1(py, (pytype,))?
                .downcast_bound::<PyTuple>(py)?
                .get_item(0)?;

            Ok(format!(
                "{}[]",
                pytype_to_abi_type(py, &inner_type, resolver, py_objects)?
            ))
        } else if let Ok(origin) = origin.downcast::<PyType>() {
            if origin.is_subclass(&py_objects.wake_fixed_list.bind(py))? {
                let inner_type = py_objects
                    .typing_get_args
                    .call1(py, (pytype,))?
                    .downcast_bound::<PyTuple>(py)?
                    .get_item(0)?;
                let length = pytype.getattr(intern!(py, "length"))?.extract::<usize>()?;

                Ok(format!(
                    "{}[{}]",
                    pytype_to_abi_type(py, &inner_type, resolver, py_objects)?,
                    length
                ))
            } else {
                Err(PyErr::new::<PyValueError, _>(format!(
                    "Unexpected type for EIP-712: {:?}",
                    pytype
                )))
            }
        } else {
            Err(PyErr::new::<PyValueError, _>(format!(
                "Unexpected type for EIP-712: {:?}",
                pytype
            )))
        }
    }
}

// TODO function
fn convert(
    py: Python,
    value: &Bound<PyAny>,
    pytype: &Bound<PyAny>,
    resolver: &mut Resolver,
    py_objects: &mut PyObjects,
) -> PyResult<(String, serde_json::Value)> {
    if pytype.is(&PyBool::type_object(py)) {
        Ok((
            "bool".into(),
            serde_json::Value::Bool(value.downcast::<PyBool>()?.is_true()),
        ))
    } else if pytype.is(&PyBytes::type_object(py))
        || pytype.is(&PyByteArray::type_object(py))
    {
        let str = if let Ok(bytes) = value.downcast::<PyBytes>() {
            hex::encode(bytes.as_bytes())
        } else if let Ok(bytearray) = value.downcast::<PyByteArray>() {
            unsafe { hex::encode(bytearray.as_bytes()) }
        } else {
            let bytes = value.call_method0(intern!(py, "__bytes__"))?;
            hex::encode(bytes.downcast_into::<PyBytes>()?.as_bytes())
        };
        Ok(("bytes".into(), serde_json::Value::String(str)))
    } else if pytype.is(&PyString::type_object(py)) {
        Ok((
            "string".into(),
            serde_json::Value::String(value.extract::<String>()?),
        ))
    } else if let Ok(pytype) = pytype.downcast::<PyType>() {
        if pytype.is_subclass(&Address::type_object(py))?
            || pytype.is_subclass(&Account::type_object(py))?
        {
            let addr = value.extract::<AddressEnum>()?;
            Ok((
                "address".into(),
                serde_json::Value::String(
                    RevmAddress::try_from(addr)
                        .map_err(|e| PyErr::new::<PyValueError, _>(e.to_string()))?
                        .to_string(),
                ),
            ))
        } else if pytype.is_subclass(&py_objects.wake_integer.bind(py))? {
            let bits = pytype.getattr(intern!(py, "bits"))?.extract::<usize>()?;
            if pytype
                .getattr(intern!(py, "signed"))?
                .downcast::<PyBool>()?
                .is_true()
            {
                let val = value.extract::<BigInt>()?;
                Ok((
                    format!("int{}", bits),
                    serde_json::Value::String(val.to_string()),
                ))
            } else {
                let val = value.extract::<BigUint>()?;
                Ok((
                    format!("uint{}", bits),
                    serde_json::Value::String(val.to_string()),
                ))
            }
        } else if pytype.is_subclass(&py_objects.enums_int_enum.bind(py))? {
            Ok((
                "uint8".into(),
                serde_json::Value::Number(value.extract::<usize>()?.into()),
            ))
        } else if pytype.is_subclass(&py_objects.wake_fixed_bytes.bind(py))? {
            let length = pytype.getattr(intern!(py, "length"))?.extract::<usize>()?;
            Ok((
                format!("bytes{}", length),
                serde_json::Value::String(hex::encode(value.downcast::<PyBytes>()?.as_bytes())),
            ))
        } else if py_objects
            .dataclasses_is_dataclass
            .call(py, (pytype.clone(),), None)?
            .downcast_bound::<PyBool>(py)?
            .is_true()
        {
            process_dataclass(py, value, resolver, py_objects)
        } else {
            Err(PyErr::new::<PyValueError, _>(format!(
                "Unexpected type for EIP-712: {:?}",
                pytype
            )))
        }
    } else {
        // static and dynamic arrays
        let origin = py_objects
            .typing_get_origin
            .call(py, (pytype,), None)?;
        let origin = origin.bind(py);

        let inner_type = py_objects
            .typing_get_args
            .call(py, (pytype,), None)?
            .downcast_bound::<PyTuple>(py)?
            .get_item(0)?;

        let length;
        if origin.is(&PyList::type_object(py)) {
            length = None;
        } else if let Ok(origin) = origin.downcast::<PyType>() {
            if origin.is_subclass(&py_objects.wake_fixed_list.bind(py))? {
                length = Some(origin.getattr(intern!(py, "length"))?.extract::<usize>()?);
            } else {
                return Err(PyErr::new::<PyValueError, _>(format!(
                    "Unexpected type for EIP-712: {:?}",
                    pytype
                )));
            }
        } else {
            return Err(PyErr::new::<PyValueError, _>(format!(
                "Unexpected type for EIP-712: {:?}",
                pytype
            )));
        }

        let data = value.extract::<Vec<Bound<PyAny>>>()?;
        let mut vec = Vec::with_capacity(data.len());
        let mut inner_type_string = None;

        for item in data {
            let (t, v) = convert(py, &item, &inner_type, resolver, py_objects)?;
            inner_type_string = Some(t);
            vec.push(v);
        }

        if let Some(length) = length {
            if vec.len() != length {
                return Err(PyErr::new::<PyValueError, _>(format!(
                    "Expected length {:?} but got {:?} for type {:?}",
                    length,
                    vec.len(),
                    pytype
                )));
            }
            Ok((
                format!(
                    "{}[{}]",
                    inner_type_string.unwrap_or(pytype_to_abi_type(
                        py,
                        &inner_type,
                        resolver,
                        py_objects
                    )?),
                    length
                ),
                serde_json::Value::Array(vec),
            ))
        } else {
            Ok((
                format!(
                    "{}[]",
                    inner_type_string.unwrap_or(pytype_to_abi_type(
                        py,
                        &inner_type,
                        resolver,
                        py_objects
                    )?)
                ),
                serde_json::Value::Array(vec),
            ))
        }
    }
}

fn process_dataclass(
    py: Python,
    obj: &Bound<PyAny>,
    resolver: &mut Resolver,
    py_objects: &mut PyObjects,
) -> PyResult<(String, serde_json::Value)> {
    let type_name = obj.getattr(intern!(py, "original_name")).map_or(
        obj.get_type()
            .getattr(intern!(py, "__name__"))?
            .extract::<String>(),
        |n| n.extract::<String>(),
    )?;

    let hints = py_objects.get_type_hints(py, obj.get_type())?;
    let fields = py_objects
        .dataclasses_fields
        .call(py, (obj.clone(),), None)?;
    let fields = fields.downcast_bound::<PyTuple>(py)?;

    let mut props = Vec::with_capacity(fields.len());
    let mut map = serde_json::Map::with_capacity(fields.len());

    for field in fields.iter() {
        let name = field
            .getattr(intern!(py, "name"))?
            .downcast_into::<PyString>()?;
        let original_name = field
            .getattr(intern!(py, "original_name"))
            .map_or(Ok(name.clone()), |n| n.downcast_into::<PyString>())?;
        let value = obj.getattr(name.clone())?;
        let pytype = hints.get_item(name)?.unwrap();

        let (t, v) = convert(py, &value, &pytype, resolver, py_objects)?;
        map.insert(original_name.to_string(), v);
        props.push(PropertyDef::new_unchecked(t, original_name.to_string()));
    }

    resolver.ingest(TypeDef::new_unchecked(type_name.clone(), props));

    let value = serde_json::Value::Object(map);

    Ok((type_name, value))
}
