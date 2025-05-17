use std::collections::HashMap;

use alloy::dyn_abi::{DynSolType, DynSolValue};
use num_bigint::{BigInt, BigUint};
use pyo3::{
    exceptions::PyRuntimeError, intern, prelude::*, types::{PyBool, PyBytes, PyDict, PyList, PyString, PyTuple, PyType}, IntoPyObjectExt, PyTypeInfo
};
use revm::{context::ContextTr, primitives::Log};

use crate::{
    abi_old::{alloy_to_py, AbiError},
    account::Account,
    address::Address,
    chain::Chain,
    contract::Contract,
    inspectors::fqn_inspector::{ErrorMetadata, EventMetadata},
    tx::TransactionAbc,
    utils::PyObjects,
};

pub(crate) fn decode_and_normalize(
    py: Python,
    data: &[u8],
    abi: &Bound<PyDict>,
    pytype: &Bound<PyAny>,
    chain: &Py<Chain>,
    abi_key: &Bound<PyString>,
    py_objects: &mut PyObjects,
) -> PyResult<PyObject> {
    let alloy_type: DynSolType = format!("({})", extract_abi_types(py, &abi, abi_key)?.join(","))
        .parse()
        .unwrap();

    let mut decoded = alloy_type
        .abi_decode_sequence(&data)
        .map_err(|e| AbiError::new_err(e.to_string()))?;

    if let DynSolValue::Tuple(ref tuple) = decoded {
        if tuple.len() == 1 {
            decoded = tuple.into_iter().next().unwrap().clone();
        }
    }

    normalize_output(py, &decoded, pytype, chain.as_any(), py_objects)
}

fn external_or_unknown_error(
    py: Python,
    data: &[u8],
    chain: &Py<Chain>,
    tx: Option<&Bound<TransactionAbc>>,
    metadata: &ErrorMetadata,
    py_objects: &mut PyObjects,
) -> PyResult<PyObject> {
    let chain = chain.bind(py).borrow();
    if chain
        .get_evm()?
        .db_ref()
        .is_contract_forked(&metadata.bytecode_address)
        .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?
    {
        let name_abi = py_objects.wake_get_name_abi.bind(py).call1((
            metadata.bytecode_address.to_string(),
            chain.forked_chain_id.unwrap(),
        ))?;

        if !name_abi.is_none() {
            let name_abi = name_abi.downcast_into::<PyTuple>()?;
            let abi = name_abi.get_item(1)?.downcast_into::<PyDict>()?;

            if let Some(abi) = abi.get_item(PyBytes::new(py, &data[..4]))? {
                let abi = abi.downcast_into::<PyDict>()?;
                let alloy_type: DynSolType = format!(
                    "({})",
                    extract_abi_types(py, &abi, intern!(py, "inputs"))?.join(",")
                )
                .parse()
                .unwrap();

                let decoded = alloy_type.abi_decode_sequence(&data[4..]).unwrap();

                let contract_name = name_abi.get_item(0)?.downcast_into::<PyString>()?;
                let error_name = abi
                    .get_item(intern!(py, "name"))?
                    .unwrap()
                    .downcast_into::<PyString>()?;

                let kwargs = PyDict::new(py);
                if let DynSolValue::Tuple(ref tuple) = decoded {
                    let inputs = abi.get_item(intern!(py, "inputs"))?.unwrap();
                    let inputs_list = inputs.downcast::<PyList>()?;
                    for (input, value) in inputs_list.iter().zip(tuple.iter()) {
                        let input_dict = input.downcast::<PyDict>()?;
                        let input_name = input_dict
                            .get_item(intern!(py, "name"))?
                            .unwrap()
                            .downcast_into::<PyString>()?;

                        kwargs.set_item(input_name, alloy_to_py(py, &value, py_objects)?)?;
                    }
                } else {
                    panic!("Expected tuple");
                }

                let error = py_objects.wake_external_error.call(
                    py,
                    (format!(
                        "{}.{}",
                        contract_name.to_str()?,
                        error_name.to_str()?
                    ),),
                    Some(&kwargs),
                )?;

                if let Some(tx) = tx {
                    error.setattr(py, "tx", tx)?;
                }

                return Ok(error);
            }
        }
    }

    new_unknown_error(py, data, tx, py_objects)
}

pub(crate) fn resolve_error(
    py: Python,
    data: &[u8],
    chain: &Py<Chain>,
    tx: Option<&Bound<TransactionAbc>>,
    errors_metadata: &HashMap<[u8; 4], ErrorMetadata>,
    py_objects: &mut PyObjects,
) -> PyResult<PyObject> {
    if data.len() < 4 {
        return new_unknown_error(py, data, tx, py_objects);
    }

    let errors = py_objects
        .wake_errors
        .bind(py)
        .get_item(PyBytes::new(py, &data[..4]))?;

    if let Some(errors) = errors {
        let errors = errors.downcast_into::<PyDict>()?;
        let selector: [u8; 4] = data[..4].try_into().unwrap();

        let fqn = if selector == [0x08, 0xc3, 0x79, 0xa0] || selector == [0x4e, 0x48, 0x7b, 0x71] {
            PyString::new(py, "").into_any()
        } else if let Some(metadata) = errors_metadata.get(&selector) {
            if let Some(fqn) = py_objects
                .wake_contracts_by_metadata
                .bind(py)
                .get_item(PyBytes::new(py, &metadata.metadata))?
            {
                fqn
            } else {
                return external_or_unknown_error(py, data, chain, tx, metadata, py_objects);
            }
        } else {
            return new_unknown_error(py, data, tx, py_objects);
        };

        let tmp = errors.get_item(fqn)?.unwrap().downcast_into::<PyTuple>()?;
        let module_name = tmp.get_item(0)?.downcast_into::<PyString>()?;
        let path = tmp.get_item(1)?.downcast_into::<PyTuple>()?;

        let mut obj = py.import(module_name)?.into_any();

        for attr in path.iter() {
            let attr = attr.downcast::<PyString>()?;
            obj = obj.getattr(attr)?;
        }

        let abi = obj
            .getattr(intern!(py, "_abi"))?
            .downcast_into::<PyDict>()?;

        let alloy_type: DynSolType = format!(
            "({})",
            extract_abi_types(py, &abi, intern!(py, "inputs"))?.join(",")
        )
        .parse()
        .unwrap();

        let decoded = alloy_type.abi_decode_sequence(&data[4..]).unwrap();
        let err = normalize_output(py, &decoded, &obj, chain.as_any(), py_objects)?;

        if let Some(tx) = tx {
            err.setattr(py, "tx", tx)?;
        }

        Ok(err)
    } else {
        if let Some(metadata) = errors_metadata.get(&data[..4]) {
            return external_or_unknown_error(py, data, chain, tx, metadata, py_objects);
        } else {
            return new_unknown_error(py, data, tx, py_objects);
        }
    }
}

pub(crate) fn new_unknown_event(
    py: Python,
    log: &Log,
    chain: &Py<Chain>,
    py_objects: &PyObjects,
) -> PyResult<PyObject> {
    let topics: Vec<Bound<PyBytes>> = log
        .topics()
        .iter()
        .map(|t| PyBytes::new(py, t.as_slice()))
        .collect();
    let event = py_objects.wake_unknown_event.call(
        py,
        (topics, PyBytes::new(py, &log.data.data)),
        None,
    )?;
    event.setattr(
        py,
        "origin",
        Account::from_address_native(py, log.address, chain.clone_ref(py))?,
    )?;
    Ok(event)
}

pub(crate) fn new_unknown_error(
    py: Python,
    data: &[u8],
    tx: Option<&Bound<TransactionAbc>>,
    py_objects: &mut PyObjects,
) -> PyResult<PyObject> {
    let err = py_objects.wake_unknown_revert_exception.call(
        py,
        (PyBytes::new(py, data),),
        None,
    )?;

    if let Some(tx) = tx {
        err.setattr(py, "tx", tx)?;
    }

    Ok(err)
}

pub(crate) fn external_or_unknown_event(
    py: Python,
    log: &Log,
    chain: &Py<Chain>,
    metadata: &EventMetadata,
    py_objects: &mut PyObjects,
) -> PyResult<PyObject> {
    if let Some(bytecode_address) = metadata.bytecode_address {
        let chain = chain.bind(py).borrow();
        if chain
            .get_evm()?
            .db_ref()
            .is_contract_forked(&bytecode_address)
            .map_err(|e| PyErr::new::<PyRuntimeError, _>(e.to_string()))?
        {
            let name_abi = py_objects
                .wake_get_name_abi
                .bind(py)
                .call1((bytecode_address.to_string(), chain.forked_chain_id.unwrap()))?;

            if !name_abi.is_none() {
                let name_abi = name_abi.downcast_into::<PyTuple>()?;
                let abi = name_abi.get_item(1)?.downcast_into::<PyDict>()?;

                if let Some(abi) =
                    abi.get_item(PyBytes::new(py, log.topics()[0].as_slice()))?
                {
                    let values = decode_event(py, abi.downcast::<PyDict>()?, log)?;

                    let contract_name = name_abi.get_item(0)?.downcast_into::<PyString>()?;
                    let event_name = abi
                        .get_item(intern!(py, "name"))?
                        .downcast_into::<PyString>()?;

                    let inputs = abi.get_item(intern!(py, "inputs"))?;
                    let inputs_list = inputs.downcast::<PyList>()?;

                    let kwargs = PyDict::new(py);
                    for (input, value) in inputs_list.iter().zip(values.iter()) {
                        let input_dict = input.downcast::<PyDict>()?;
                        let input_name = input_dict
                            .get_item(intern!(py, "name"))?
                            .unwrap()
                            .downcast_into::<PyString>()?;

                        kwargs.set_item(input_name, alloy_to_py(py, &value, py_objects)?)?;
                    }

                    let event = py_objects.wake_external_event.call(
                        py,
                        (format!(
                            "{}.{}",
                            contract_name.to_str()?,
                            event_name.to_str()?
                        ),),
                        Some(&kwargs),
                    )?;
                    event.setattr(
                        py,
                        "origin",
                        Account::from_address_native(py, log.address, chain.into())?,
                    )?;
                    return Ok(event);
                }
            }
        }
    }

    new_unknown_event(py, log, chain, py_objects)
}

fn decode_event(py: Python, abi: &Bound<PyDict>, log: &Log) -> PyResult<Vec<DynSolValue>> {
    let inputs = abi.get_item(intern!(py, "inputs"))?.unwrap();
    let inputs_list = inputs.downcast::<PyList>()?;

    let mut types = Vec::with_capacity(inputs_list.len());
    for input in inputs_list.iter() {
        let input_dict = input.downcast::<PyDict>()?;
        let input_indexed = input_dict
            .get_item(intern!(py, "indexed"))?
            .unwrap()
            .downcast_into::<PyBool>()?;

        if !input_indexed.is_true() {
            collapse_if_tuple(py, input_dict, &mut types)?;
        }
    }

    let alloy_type: DynSolType = format!("({})", types.join(",")).parse().unwrap();
    let decoded = alloy_type.abi_decode_sequence(&log.data.data).unwrap();

    if let DynSolValue::Tuple(mut tuple) = decoded {
        let mut values = Vec::with_capacity(tuple.len() + log.topics().len());
        let mut topic_index = 1;

        for input in inputs_list.iter() {
            let input_dict = input.downcast::<PyDict>()?;
            let input_indexed = input_dict
                .get_item(intern!(py, "indexed"))?
                .unwrap()
                .downcast_into::<PyBool>()?;

            if input_indexed.is_true() {
                let input_type = input_dict.get_item(intern!(py, "type"))?.unwrap();
                let input_type = input_type.extract::<&str>()?;
                let input_internal_type = input_dict.get_item(intern!(py, "internalType"))?;
                let input_internal_type = if let Some(input_internal_type) = input_internal_type {
                    Some(input_internal_type.extract::<String>()?)
                } else {
                    None
                };

                if input_type == "string"
                    || input_type == "bytes"
                    || input_type.ends_with("]")
                    || input_internal_type.is_some_and(|s| s.starts_with("struct "))
                {
                    values.push(DynSolValue::FixedBytes(log.topics()[topic_index], 32));
                } else {
                    let t: DynSolType = input_type.parse().unwrap();
                    values.push(t.abi_decode(log.topics()[topic_index].as_slice()).unwrap());
                }
                topic_index += 1;
            } else {
                values.push(tuple.remove(0));
            }
        }

        Ok(values)
    } else {
        panic!("Expected tuple");
    }
}

pub(crate) fn resolve_event(
    py: Python,
    log: &Log,
    chain: &Py<Chain>,
    metadata: &EventMetadata,
    py_objects: &mut PyObjects,
) -> PyResult<PyObject> {
    if log.topics().len() == 0 {
        return new_unknown_event(py, log, chain, py_objects);
    }
    let events = py_objects
        .wake_events
        .bind(py)
        .get_item(PyBytes::new(py, log.topics()[0].as_slice()))?;

    if let Some(events) = events {
        let events = events.downcast_into::<PyDict>()?;

        let fqn = if let Some(fqn) = py_objects
            .wake_contracts_by_metadata
            .bind(py)
            .get_item(PyBytes::new(py, &metadata.metadata))?
        {
            fqn
        } else {
            return external_or_unknown_event(py, log, chain, metadata, py_objects);
        };

        let tmp = match events.get_item(fqn)? {
            Some(item) => item.downcast_into::<PyTuple>()?,
            None => {
                // see https://github.com/ethereum/solidity/issues/15752
                return external_or_unknown_event(py, log, chain, metadata, py_objects);
            }
        };

        let module_name = tmp.get_item(0)?.downcast_into::<PyString>()?;
        let path = tmp.get_item(1)?.downcast_into::<PyTuple>()?;

        let mut obj = py.import(module_name)?.into_any();

        for attr in path.iter() {
            let attr = attr.downcast::<PyString>()?;
            obj = obj.getattr(attr)?;
        }

        let abi = obj
            .getattr(intern!(py, "_abi"))?
            .downcast_into::<PyDict>()?;
        let values = decode_event(py, &abi, log)?;

        let event = normalize_output(
            py,
            &DynSolValue::Tuple(values),
            &obj,
            chain.as_any(),
            py_objects,
        )?;
        event.setattr(
            py,
            "origin",
            Account::from_address_native(py, log.address, chain.clone_ref(py))?,
        )?;
        Ok(event)
    } else {
        external_or_unknown_event(py, log, chain, metadata, py_objects)
    }
}

pub(crate) fn normalize_output(
    py: Python,
    value: &DynSolValue,
    pytype: &Bound<PyAny>,
    chain: &Py<PyAny>, // called from abi possibly with non-native Chain
    py_objects: &mut PyObjects,
) -> PyResult<PyObject> {
    // TODO None
    match value {
        DynSolValue::Address(v) => {
            // may be Address, Account, or Contract
            let pytype = pytype.downcast::<PyType>()?;

            if pytype.is_subclass(&Contract::type_object(py))? {
                return Ok(pytype.call((Address::from(*v), chain), None)?.into());
            } else if pytype.is_subclass(&Account::type_object(py))? {
                return Ok(
                    Py::new(py, Account::from_revm_address(py, *v, chain.clone_ref(py))?)?
                        .into(),
                );
            } else {
                Address::from(*v).into_py_any(py)
            }
        }
        DynSolValue::Bytes(v) => Ok(PyBytes::new(py, v.as_slice()).into()),
        DynSolValue::Int(v, _) => {
            let int = BigInt::from_signed_bytes_le(&v.to_le_bytes::<32>());
            Ok(pytype.call1((int,))?.into())
        }
        DynSolValue::Uint(v, _) => {
            // either enum or uintX
            let uint = BigUint::from_bytes_le(v.as_le_slice());
            Ok(pytype.call1((uint,))?.into())
        }
        DynSolValue::Bool(v) => v.into_py_any(py),
        DynSolValue::String(v) => v.into_py_any(py),
        DynSolValue::FixedBytes(v, size) => Ok(pytype
            .call1((PyBytes::new(py, &v[..*size]),))?
            .into()),
        DynSolValue::Array(v) => {
            let inner_type = py_objects
                .typing_get_args
                .call1(py, (pytype,))?
                .downcast_bound::<PyTuple>(py)?
                .get_item(0)?;

            let mut vec = Vec::with_capacity(v.len());

            for item in v {
                vec.push(normalize_output(py, item, &inner_type, chain, py_objects)?);
            }

            Ok(PyList::new(py, vec)?.into())
        }
        DynSolValue::FixedArray(v) => {
            let inner_type = py_objects
                .typing_get_args
                .call1(py, (pytype,))?
                .downcast_bound::<PyTuple>(py)?
                .get_item(0)?;

            let mut vec = Vec::with_capacity(v.len());

            for item in v {
                vec.push(normalize_output(py, item, &inner_type, chain, py_objects)?);
            }

            Ok(pytype.call1((PyTuple::new(py, vec)?,))?.into())
        }
        DynSolValue::Tuple(v) => {
            // either tuple or dataclass

            if py_objects
                .dataclasses_is_dataclass
                .call1(py, (pytype,))?
                .downcast_bound::<PyBool>(py)?
                .is_true()
            {
                let fields = py_objects.dataclasses_fields.call1(py, (pytype,))?;
                let fields = fields.downcast_bound::<PyTuple>(py)?;
                let type_hints =
                    py_objects.get_type_hints(py, pytype.clone().downcast_into::<PyType>()?)?;

                let mut field_types = Vec::with_capacity(fields.len());
                for field in fields.iter() {
                    if field
                        .getattr(intern!(py, "init"))?
                        .downcast_into::<PyBool>()?
                        .is_true()
                    {
                        field_types.push(
                            type_hints
                                .get_item(field.getattr("name")?.downcast_into::<PyString>()?)?
                                .unwrap(),
                        );
                    }
                }

                let mut values = Vec::with_capacity(v.len());

                assert_eq!(field_types.len(), v.len());

                for (value, field_type) in v.iter().zip(field_types.iter()) {
                    values.push(normalize_output(py, value, field_type, chain, py_objects)?);
                }

                Ok(pytype
                    .call(PyTuple::new(py, values)?, None)?
                    .into())
            } else {
                let args = py_objects.typing_get_args.call1(py, (pytype,))?;
                let types = args.downcast_bound::<PyTuple>(py)?;
                let mut vec = Vec::with_capacity(v.len());

                for (item, inner_type) in v.iter().zip(types.iter()) {
                    vec.push(normalize_output(py, item, &inner_type, chain, py_objects)?);
                }

                Ok(PyTuple::new(py, vec)?.into())
            }
        }
        DynSolValue::Function(_) => {
            todo!()
        }
        DynSolValue::CustomStruct {
            name: _,
            prop_names: _,
            tuple: _,
        } => panic!("Custom struct not supported"),
    }
}

pub(crate) fn collapse_if_tuple(
    py: Python,
    abi: &Bound<PyDict>,
    types: &mut Vec<String>,
) -> PyResult<()> {
    let input_type = abi
        .get_item(intern!(py, "type"))?
        .unwrap()
        .downcast_into::<PyString>()?;
    let input_type = input_type.to_str()?;

    if input_type.starts_with("tuple") {
        let components = abi
            .get_item(intern!(py, "components"))?
            .unwrap()
            .downcast_into::<PyList>()?;
        let mut tuple_types = Vec::with_capacity(components.len());

        for component in components.iter() {
            let component_dict = component.downcast::<PyDict>()?;
            collapse_if_tuple(py, component_dict, &mut tuple_types)?;
        }
        types.push(format!(
            "({}){}",
            tuple_types.join(","),
            input_type.strip_prefix("tuple").unwrap()
        ));
    } else {
        if let Some(internal_type) = abi.get_item(intern!(py, "internalType"))? {
            let internal_type = internal_type.downcast_into::<PyString>()?;
            let internal_type = internal_type.to_str()?;

            // fix library ABI if needed
            if internal_type.starts_with("contract ") {
                let address_type = if let Some(bracket_index) = internal_type.find('[') {
                    format!("address{}", &internal_type[bracket_index..])
                } else {
                    "address".to_string()
                };
                types.push(address_type);
            } else if internal_type.starts_with("enum ") {
                let enum_type = if let Some(bracket_index) = internal_type.find('[') {
                    format!("uint8{}", &internal_type[bracket_index..])
                } else {
                    "uint8".to_string()
                };
                types.push(enum_type);
            } else {
                types.push(input_type.to_string());
            }
        } else {
            types.push(input_type.to_string());
        }
    }

    Ok(())
}

pub(crate) fn extract_abi_types(
    py: Python,
    abi: &Bound<PyDict>,
    key: &Bound<PyString>,
) -> PyResult<Vec<String>> {
    let inputs = abi.get_item(key)?.unwrap();
    let inputs_list = inputs.downcast::<PyList>()?;
    let mut types = Vec::with_capacity(inputs_list.len());

    for input in inputs_list.iter() {
        let input_dict = input.downcast::<PyDict>()?;
        collapse_if_tuple(py, input_dict, &mut types)?;
    }

    Ok(types)
}
