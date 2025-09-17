use std::collections::HashMap;
use std::sync::Arc;

use pyo3::{intern, prelude::*};
use pyo3::types::{PyBytes, PyDict, PyList, PyType};

use crate::account::Account;
use crate::chain::Chain;
use crate::contract::Contract;
use crate::enums::{
    AccessListEnum, AddressEnum, BlockEnum, GasLimitEnum, RequestTypeEnum, ValueEnum,
};
use crate::tx::TransactionAbc;
use crate::utils::get_py_objects;

#[pyclass(extends=Contract, subclass)]
pub struct Library {}

#[pymethods]
impl Library {
    #[pyo3(signature = (address, chain=None))]
    #[new]
    fn new(
        py: Python,
        address: AddressEnum,
        chain: Option<Py<PyAny>>,
    ) -> PyResult<PyClassInitializer<Self>> {
        Ok(PyClassInitializer::from(Contract::new(py, address, chain)?).add_subclass(Library {}))
    }

    #[pyo3(signature = (request_type, arguments, return_tx, return_type, from_, value, gas_limit, libraries, chain, gas_price, max_fee_per_gas, max_priority_fee_per_gas, access_list, authorization_list, block, confirmations, revert))]
    #[classmethod]
    fn _deploy(
        cls: &Bound<PyType>,
        py: Python,
        request_type: RequestTypeEnum,
        arguments: Vec<Bound<'_, PyAny>>,
        return_tx: bool,
        return_type: Bound<PyAny>,
        from_: Option<AddressEnum>,
        value: ValueEnum,
        gas_limit: Option<GasLimitEnum>,
        libraries: HashMap<Vec<u8>, Py<PyAny>>,
        chain: Option<Py<PyAny>>,
        gas_price: Option<ValueEnum>,
        max_fee_per_gas: Option<ValueEnum>,
        max_priority_fee_per_gas: Option<ValueEnum>,
        access_list: Option<AccessListEnum>,
        authorization_list: Option<Vec<Bound<'_, PyDict>>>,
        block: Option<BlockEnum>,
        confirmations: Option<u64>,
        revert: bool,
    ) -> PyResult<PyObject> {
        let chain = match chain {
            Some(chain) => chain,
            None => {
                let py_objects = get_py_objects(py);
                py_objects.wake_detect_default_chain.call0(py)?
            }
        };

        let ret = Contract::_deploy(
            cls,
            py,
            request_type,
            arguments,
            return_tx,
            return_type,
            from_,
            value,
            gas_limit,
            libraries,
            Some(chain.clone_ref(py)),
            gas_price,
            max_fee_per_gas,
            max_priority_fee_per_gas,
            access_list,
            authorization_list,
            block,
            confirmations,
            revert,
        )?;

        if confirmations != Some(0) {
            let lib_id = cls.getattr(intern!(py, "_library_id"))?.downcast_into::<PyBytes>()?;

            if let Ok(chain) = chain.downcast_bound::<Chain>(py) {
                let addr = if return_tx {
                    TransactionAbc::return_value(
                        ret.downcast_bound::<TransactionAbc>(py).unwrap(),
                        py
                    ).unwrap().downcast_bound::<Account>(py).unwrap().borrow().address.borrow(py).0
                } else {
                    ret.downcast_bound::<Account>(py).unwrap().borrow().address.borrow(py).0
                };

                Arc::make_mut(&mut chain.borrow_mut().deployed_libraries).insert(lib_id.as_bytes().try_into().unwrap(), addr);
            } else {
                let lib = if return_tx {
                    ret.getattr(py, intern!(py, "return_value"))?
                } else {
                    ret.clone_ref(py)
                };
                chain.bind(py).getattr(intern!(py, "_deployed_libraries"))?.get_item(lib_id)?.downcast_into::<PyList>()?.append(lib)?;
            }
        }

        Ok(ret)
    }
}
