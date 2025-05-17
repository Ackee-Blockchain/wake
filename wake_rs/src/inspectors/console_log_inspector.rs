use std::str::FromStr;

use revm::{
    context::ContextTr, inspector::JournalExt, interpreter::{CallInputs, CallOutcome}, primitives::{Address, Bytes}, Inspector
};

pub(crate) struct ConsoleLogInspector {
    console_address: Address,
    inputs: Vec<Bytes>,
}

impl ConsoleLogInspector {
    pub fn new() -> Self {
        Self {
            console_address: Address::from_str("000000000000000000636F6e736F6c652e6c6f67").unwrap(),
            inputs: Vec::new(),
        }
    }

    pub fn into_inputs(self) -> Vec<Bytes> {
        self.inputs
    }
}

impl<CTX: ContextTr<Journal: JournalExt>> Inspector<CTX> for ConsoleLogInspector {
    fn call(&mut self, _context: &mut CTX, inputs: &mut CallInputs) -> Option<CallOutcome> {
        if inputs.is_static
            && inputs.target_address == self.console_address
            && inputs.input.len() >= 4
        {
            self.inputs.push(inputs.input.clone());
        }

        None
    }
}
