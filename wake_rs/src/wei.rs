use pyo3::prelude::*;


#[pyclass]
struct Wei {
    value: u64,
}

// TODO implement += for string
#[pymethods]
impl Wei {
    #[new]
    fn new(value: u64) -> Self {
        Self { value }
    }

    fn __int__(&self) -> PyResult<u64> {
        Ok(self.value)
    }

    fn __str__(&self) -> PyResult<String> {
        Ok(self.value.to_string())
    }

    fn __repr__(&self) -> PyResult<String> {
        Ok(format!("Wei({})", self.value))
    }
}
