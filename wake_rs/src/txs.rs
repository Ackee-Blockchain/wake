use pyo3::{exceptions::PyIndexError, prelude::*};

use crate::tx::TransactionAbc;

#[pyclass]
pub struct Txs {
    pub(crate) txs: Vec<Py<TransactionAbc>>,
}

impl Txs {
    pub(crate) fn new() -> Self {
        Self { txs: vec![] }
    }

    pub(crate) fn add_tx(&mut self, tx: Py<TransactionAbc>) {
        self.txs.push(tx);
    }

    pub(crate) fn remove_txs(&mut self, py: Python, journal_index: usize) {
        let left = self.txs.binary_search_by(|tx| {
            tx.borrow(py).journal_index.cmp(&journal_index)
        }).unwrap_or_else(|i| i);

        // Remove all transactions from left onwards (those with journal_index >= journal_index)
        self.txs.truncate(left);
    }
}

#[pymethods]
impl Txs {
    fn __getitem__(&self, py: Python, index: isize) -> PyResult<Py<TransactionAbc>> {
        if index < 0 {
            self.txs.get((self.txs.len() as isize + index) as usize).map(|tx| tx.clone_ref(py)).ok_or(PyErr::new::<PyIndexError, _>(format!("index {} out of range", index)))
        } else {
            self.txs.get(index as usize).map(|tx| tx.clone_ref(py)).ok_or(PyErr::new::<PyIndexError, _>(format!("index {} out of range", index)))
        }
    }
}
