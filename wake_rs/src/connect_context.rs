use pyo3::types::PyFunction;
use pyo3::{prelude::*, types::PyCFunction};

use crate::chain::Chain;

#[pyclass]
pub struct ConnectContext {
    chain: Py<Chain>,
    // connect params
    accounts_count: u16,
    chain_id: Option<u64>,
    fork_url: Option<String>,
    hardfork: Option<String>,
    // min_gas_price: Option<u64>,
    // block_base_fee_per_gas: Option<u64>,
}

#[pymethods]
impl ConnectContext {
    #[new]
    pub(crate) fn new(
        chain: Py<Chain>,
        accounts_count: u16,
        chain_id: Option<u64>,
        fork_url: Option<String>,
        hardfork: Option<String>,
    ) -> Self {
        Self {
            chain,
            accounts_count,
            chain_id,
            fork_url,
            hardfork,
        }
    }

    fn __enter__(&self, py: Python) -> PyResult<()> {
        Chain::connect(
            self.chain.clone(),
            py,
            self.accounts_count,
            self.chain_id,
            self.fork_url.as_ref().map(|u| u.as_str()),
            self.hardfork.as_ref().map(|h| {
                // capitalize first letter
                let mut chars = h.chars();
                chars.next().unwrap().to_uppercase().collect::<String>() + &chars.as_str()
            }).as_deref(),
        );
        Ok(())
    }

    fn __call__(slf: Py<Self>, py: Python, func: Py<PyAny>) -> PyResult<Bound<PyCFunction>> {
        let ret = PyCFunction::new_closure_bound(py, None, None, move |args, kwargs| {
            Python::with_gil(|py| -> PyResult<_> {
                slf.borrow(py).__enter__(py)?;
                let result = func.call_bound(py, args, kwargs.map(|k| k))?;
                slf.borrow(py).__exit__(py, None, None, None)?;
                Ok(result)
            })
        }).unwrap();
        Ok(ret)
    }

    fn __exit__(
        &self,
        py: Python,
        exc_type: Option<&Bound<PyAny>>,
        exc_value: Option<&Bound<PyAny>>,
        traceback: Option<&Bound<PyAny>>,
    ) -> PyResult<()> {
        let chain = self.chain.borrow_mut(py);
        //chain.disconnect()?;
        Ok(())
    }
}
