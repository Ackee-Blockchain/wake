use std::collections::HashMap;

use revm::{
    context::{ContextTr, JournalTr},
    inspector::JournalExt,
    interpreter::{
        CallInputs, CallOutcome, CreateInputs, CreateOutcome, EOFCreateInputs, InstructionResult,
        Interpreter,
    },
    primitives::{Address, Bytes, Log},
    state::Bytecode,
    Inspector,
};

pub enum EventMetadata {
    Create(Bytes),
    Call(CallEventMetadata),
}

pub struct CallEventMetadata {
    pub metadata: Vec<u8>,
    pub bytecode_address: Option<Address>,
}

pub enum ErrorMetadata {
    Create(Bytes),
    Call(CallErrorMetadata),
}

pub struct CallErrorMetadata {
    pub metadata: Vec<u8>,
    pub bytecode_address: Address,
}

pub struct FqnInspector {
    pub events_metadata: HashMap<Log, EventMetadata>,
    pub errors_metadata: HashMap<[u8; 4], ErrorMetadata>,

    /// Stack of bytecode addresses.
    ///
    /// Bytecode address is only used to resolve external events in the case of forking
    /// Since CREATE / EOFCREATE can only be performed with local (not forked) contracts,
    /// we can use None in create subcalls
    bytecode_addresses: Vec<Option<Address>>,

    /// Stack of init code.
    ///
    /// Used to resolve events (logs) emitted during a CREATE / EOFCREATE.
    init_code_stack: Vec<Option<Bytes>>,
}

impl FqnInspector {
    pub fn new() -> Self {
        Self {
            events_metadata: HashMap::new(),
            errors_metadata: HashMap::new(),
            bytecode_addresses: Vec::new(),
            init_code_stack: Vec::new(),
        }
    }

    pub fn into_errors_metadata(self) -> HashMap<[u8; 4], ErrorMetadata> {
        self.errors_metadata
    }

    fn extract_metadata<'a>(&self, bytecode: &'a [u8]) -> Option<&'a [u8]> {
        if bytecode.len() < 2 {
            return None;
        }

        // introduce hard constant to prevent inefficiency with contracts without metadata
        const MAX_METADATA_LENGTH: usize = 60;
        let metadata_length =
            u16::from_be_bytes(bytecode[bytecode.len() - 2..].try_into().unwrap()) as usize;

        if metadata_length <= MAX_METADATA_LENGTH {
            Some(&bytecode[bytecode.len() - metadata_length - 2..bytecode.len() - 2])
        } else {
            None
        }
    }

    pub fn get_metadata<CTX: ContextTr<Journal: JournalExt>>(
        &self,
        address: Address,
        context: &mut CTX,
    ) -> Option<Vec<u8>> {
        let journal = context.journal();
        let bytecode = &journal.load_account_code(address).ok()?.data.info.code;

        match bytecode {
            Some(Bytecode::LegacyAnalyzed(analyzed)) => self
                .extract_metadata(analyzed.original_byte_slice())
                .map(|m| m.to_vec()),
            Some(Bytecode::Eip7702(eip7702)) => {
                let delegated_address = eip7702.delegated_address;
                let code = journal.code(delegated_address).ok()?;
                self.extract_metadata(code.as_ref())
                    .map(|m| m.to_vec())
            }
            Some(Bytecode::Eof(_)) => todo!(),
            _ => None,
        }
    }
}

impl<CTX: ContextTr<Journal: JournalExt>> Inspector<CTX> for FqnInspector {
    fn log(&mut self, interp: &mut Interpreter, _context: &mut CTX, log: Log) {
        if let Some(init_code) = self.init_code_stack.last().unwrap() {
            self.events_metadata.insert(
                log.clone(),
                EventMetadata::Create(init_code.clone()),
            );
        } else {
            let bytecode = interp.bytecode.original_byte_slice();
            if bytecode.len() >= 2 {
                let metadata = self.extract_metadata(bytecode).unwrap_or_default();
                self.events_metadata.insert(
                    log.clone(),
                    EventMetadata::Call(CallEventMetadata {
                        metadata: metadata.to_vec(),
                        bytecode_address: self.bytecode_addresses.last().unwrap().clone(),
                    }),
                );
            }
        }
    }

    fn create(&mut self, _context: &mut CTX, inputs: &mut CreateInputs) -> Option<CreateOutcome> {
        self.bytecode_addresses.push(None);
        self.init_code_stack.push(Some(inputs.init_code.clone()));
        None
    }

    fn create_end(
        &mut self,
        _context: &mut CTX,
        inputs: &CreateInputs,
        outcome: &mut CreateOutcome,
    ) {
        self.bytecode_addresses.pop();
        self.init_code_stack.pop();

        if outcome.result.result == InstructionResult::Revert && outcome.result.output.len() >= 4 {
            let selector: [u8; 4] = (&outcome.result.output[..4]).try_into().unwrap();

            self.errors_metadata
                .entry(selector)
                .or_insert(ErrorMetadata::Create(inputs.init_code.clone()));
        }
    }

    fn eofcreate(
        &mut self,
        _context: &mut CTX,
        _inputs: &mut EOFCreateInputs,
    ) -> Option<CreateOutcome> {
        self.bytecode_addresses.push(None);
        todo!();
    }

    fn eofcreate_end(
        &mut self,
        _context: &mut CTX,
        _inputs: &EOFCreateInputs,
        _outcome: &mut CreateOutcome,
    ) {
        self.bytecode_addresses.pop();
        self.init_code_stack.pop();
    }

    fn call(&mut self, _context: &mut CTX, inputs: &mut CallInputs) -> Option<CallOutcome> {
        self.bytecode_addresses.push(Some(inputs.bytecode_address));
        self.init_code_stack.push(None);

        None
    }

    fn call_end(&mut self, context: &mut CTX, inputs: &CallInputs, outcome: &mut CallOutcome) {
        self.bytecode_addresses.pop();
        self.init_code_stack.pop();

        if outcome.result.result == InstructionResult::Revert && outcome.result.output.len() >= 4 {
            let selector: [u8; 4] = (&outcome.result.output[..4]).try_into().unwrap();

            if let Ok(state_load) = context.journal().code(inputs.bytecode_address) {
                let code = state_load.data;
                if code.len() >= 2 {
                    let metadata = self.extract_metadata(code.as_ref()).unwrap_or_default();
                    self.errors_metadata
                        .entry(selector)
                        .or_insert(ErrorMetadata::Call(CallErrorMetadata {
                            metadata: metadata.to_vec(),
                            bytecode_address: inputs.bytecode_address,
                        }));
                }
            }
        }
    }
}
