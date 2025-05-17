use pyo3::prelude::*;
use std::sync::Mutex;

use lazy_static::lazy_static;
use tokio::runtime::Runtime;

use crate::chain::Chain;

lazy_static! {
    pub(crate) static ref DEFAULT_CHAIN: Mutex<Option<Py<Chain>>> = Mutex::new(None);
    pub(crate) static ref TOKIO_RUNTIME: Runtime = Runtime::new().unwrap();
}
