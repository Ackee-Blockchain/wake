use std::collections::HashMap;

use revm::{
    context::{transaction::AccessList, ContextTr},
    inspector::JournalExt,
    interpreter::{CallInputs, CallOutcome, Interpreter},
    primitives::Log,
    Inspector,
};
use revm_inspectors::access_list::AccessListInspector as RevmAccessListInspector;

use super::fqn_inspector::{ErrorMetadata, FqnInspector};

pub(crate) struct AccessListInspector {
    inner: RevmAccessListInspector,
    fqn_inspector: FqnInspector,
}

impl AccessListInspector {
    pub fn new(
        access_list: AccessList,
    ) -> Self {
        Self {
            inner: RevmAccessListInspector::new(access_list),
            fqn_inspector: FqnInspector::new(),
        }
    }

    pub fn into_access_list(self) -> AccessList {
        self.inner.into_access_list()
    }

    pub fn into_errors_metadata(self) -> HashMap<[u8; 4], ErrorMetadata> {
        self.fqn_inspector.into_errors_metadata()
    }
}

impl<CTX: ContextTr<Journal: JournalExt>> Inspector<CTX> for AccessListInspector {
    fn log(&mut self, interp: &mut Interpreter, context: &mut CTX, log: Log) {
        self.fqn_inspector.log(interp, context, log);
    }

    fn call_end(&mut self, context: &mut CTX, inputs: &CallInputs, outcome: &mut CallOutcome) {
        self.fqn_inspector.call_end(context, inputs, outcome)
    }

    fn step(&mut self, interp: &mut Interpreter, context: &mut CTX) {
        self.inner.step(interp, context);
    }
}
