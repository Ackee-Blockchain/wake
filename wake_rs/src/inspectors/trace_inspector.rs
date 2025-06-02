use num_bigint::BigUint;
use pyo3::{prelude::*, types::PyBytes};
use revm::{
    context::{ContextTr, CreateScheme, JournalTr},
    inspector::JournalExt,
    interpreter::{CallInputs, CallOutcome, CallScheme, CallValue, InstructionResult, Interpreter},
    primitives::{Address as RevmAddress, Log},
    state::Bytecode,
    Inspector,
};

use crate::address::Address;

#[pyclass]
#[derive(Clone)]
pub(crate) struct NativeLog {
    topics: Vec<Vec<u8>>,
    data: Vec<u8>,
}

#[pymethods]
impl NativeLog {
    #[getter]
    fn get_topics<'py>(&self, py: Python<'py>) -> Vec<Bound<'py, PyBytes>> {
        self.topics
            .iter()
            .map(|t| PyBytes::new(py, &t))
            .collect()
    }

    #[getter]
    fn get_data<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.data)
    }
}

#[pyclass]
#[derive(Clone)]
pub(crate) struct NativeTrace {
    metadata: Option<Vec<u8>>,
    input: Vec<u8>,
    #[pyo3(get)]
    target_address: Address,
    #[pyo3(get)]
    kind: String,
    #[pyo3(get)]
    value: BigUint,
    #[pyo3(get)]
    gas_limit: u64,

    output: Vec<u8>,
    #[pyo3(get)]
    success: bool,
    #[pyo3(get)]
    result: String,

    #[pyo3(get)]
    logs: Vec<NativeLog>,
    #[pyo3(get)]
    subtraces: Vec<NativeTrace>,
}

#[pymethods]
impl NativeTrace {
    #[getter]
    fn get_metadata<'py>(&self, py: Python<'py>) -> Option<Bound<'py, PyBytes>> {
        self.metadata.as_ref().map(|m| PyBytes::new(py, m))
    }

    #[getter]
    fn get_input<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.input)
    }

    #[getter]
    fn get_output<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.output)
    }
}

pub(crate) struct TraceInspector {
    root_trace: Option<NativeTrace>,
    current_traces: Vec<NativeTrace>,
}

impl TraceInspector {
    pub fn new() -> Self {
        Self {
            root_trace: None,
            current_traces: Vec::new(),
        }
    }

    pub fn into_root_trace(self) -> NativeTrace {
        self.root_trace.unwrap()
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

    fn get_metadata<CTX: ContextTr<Journal: JournalExt>>(
        &self,
        address: RevmAddress,
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

impl<CTX: ContextTr<Journal: JournalExt>> Inspector<CTX> for TraceInspector {
    fn log(&mut self, _: &mut Interpreter, _: &mut CTX, log: Log) {
        let current_trace = self.current_traces.last_mut().unwrap();
        current_trace.logs.push(NativeLog {
            topics: log.data.topics().iter().map(|t| t.to_vec()).collect(),
            data: log.data.data.to_vec(),
        });
    }

    fn create(
        &mut self,
        context: &mut CTX,
        inputs: &mut revm::interpreter::CreateInputs,
    ) -> Option<revm::interpreter::CreateOutcome> {
        let nonce = context
            .journal()
            .load_account(inputs.caller)
            .ok()?
            .data
            .info
            .nonce;

        let trace = NativeTrace {
            metadata: None,
            input: inputs.init_code.to_vec(),
            target_address: inputs.created_address(nonce).into(),
            kind: match inputs.scheme {
                CreateScheme::Create => "Create".to_string(),
                CreateScheme::Create2 { salt: _ } => "Create2".to_string(),
            },
            value: BigUint::from_bytes_le(inputs.value.as_le_slice()),
            gas_limit: inputs.gas_limit,
            output: Vec::new(),
            success: false,
            result: "".to_string(),
            logs: Vec::new(),
            subtraces: Vec::new(),
        };
        self.current_traces.push(trace);

        None
    }

    fn create_end(
        &mut self,
        _: &mut CTX,
        _: &revm::interpreter::CreateInputs,
        outcome: &mut revm::interpreter::CreateOutcome,
    ) {
        let mut trace = self.current_traces.pop().unwrap();

        trace.output = outcome.output().to_vec();
        trace.success = outcome.result.is_ok();
        trace.result = instruction_result_to_string(outcome.result.result);

        if let Some(last_trace) = self.current_traces.last_mut() {
            last_trace.subtraces.push(trace);
        } else {
            self.root_trace = Some(trace);
        }
    }

    fn eofcreate(
        &mut self,
        _: &mut CTX,
        _: &mut revm::interpreter::EOFCreateInputs,
    ) -> Option<revm::interpreter::CreateOutcome> {
        todo!()
    }

    fn eofcreate_end(
        &mut self,
        _: &mut CTX,
        _: &revm::interpreter::EOFCreateInputs,
        _: &mut revm::interpreter::CreateOutcome,
    ) {
        todo!()
    }

    fn call(&mut self, context: &mut CTX, inputs: &mut CallInputs) -> Option<CallOutcome> {
        let trace = NativeTrace {
            metadata: self.get_metadata(inputs.bytecode_address, context),
            input: inputs.input.to_vec(),
            target_address: inputs.bytecode_address.into(),
            kind: call_scheme_to_string(inputs.scheme),
            value: match inputs.value {
                CallValue::Transfer(value) => BigUint::from_bytes_le(value.as_le_slice()),
                CallValue::Apparent(_) => BigUint::ZERO,
            },
            gas_limit: inputs.gas_limit,
            output: Vec::new(),
            success: false,
            result: "".to_string(),
            logs: Vec::new(),
            subtraces: Vec::new(),
        };
        self.current_traces.push(trace);

        None
    }

    fn call_end(&mut self, _: &mut CTX, _: &CallInputs, outcome: &mut CallOutcome) {
        let mut trace = self.current_traces.pop().unwrap();

        trace.output = outcome.output().to_vec();
        trace.success = outcome.result.is_ok();
        trace.result = instruction_result_to_string(outcome.result.result);

        if let Some(last_trace) = self.current_traces.last_mut() {
            last_trace.subtraces.push(trace);
        } else {
            self.root_trace = Some(trace);
        }
    }
}

fn call_scheme_to_string(scheme: CallScheme) -> String {
    match scheme {
        CallScheme::Call => "Call".to_string(),
        CallScheme::CallCode => "CallCode".to_string(),
        CallScheme::DelegateCall => "DelegateCall".to_string(),
        CallScheme::StaticCall => "StaticCall".to_string(),
        CallScheme::ExtCall => "ExtCall".to_string(),
        CallScheme::ExtStaticCall => "ExtStaticCall".to_string(),
        CallScheme::ExtDelegateCall => "ExtDelegateCall".to_string(),
    }
}

fn instruction_result_to_string(result: InstructionResult) -> String {
    match result {
        InstructionResult::Continue => "Continue".to_string(),
        InstructionResult::Stop => "Stop".to_string(),
        InstructionResult::Return => "Return".to_string(),
        InstructionResult::SelfDestruct => "SelfDestruct".to_string(),
        InstructionResult::ReturnContract => "ReturnContract".to_string(),
        InstructionResult::Revert => "Revert".to_string(),
        InstructionResult::CallTooDeep => "CallTooDeep".to_string(),
        InstructionResult::OutOfFunds => "OutOfFunds".to_string(),
        InstructionResult::CreateInitCodeStartingEF00 => "CreateInitCodeStartingEF00".to_string(),
        InstructionResult::InvalidEOFInitCode => "InvalidEOFInitCode".to_string(),
        InstructionResult::InvalidExtDelegateCallTarget => {
            "InvalidExtDelegateCallTarget".to_string()
        }
        InstructionResult::CallOrCreate => "CallOrCreate".to_string(),
        InstructionResult::OutOfGas => "OutOfGas".to_string(),
        InstructionResult::MemoryOOG => "MemoryOOG".to_string(),
        InstructionResult::MemoryLimitOOG => "MemoryLimitOOG".to_string(),
        InstructionResult::PrecompileOOG => "PrecompileOOG".to_string(),
        InstructionResult::InvalidOperandOOG => "InvalidOperandOOG".to_string(),
        InstructionResult::ReentrancySentryOOG => "ReentrancySentryOOG".to_string(),
        InstructionResult::OpcodeNotFound => "OpcodeNotFound".to_string(),
        InstructionResult::CallNotAllowedInsideStatic => "CallNotAllowedInsideStatic".to_string(),
        InstructionResult::StateChangeDuringStaticCall => "StateChangeDuringStaticCall".to_string(),
        InstructionResult::InvalidFEOpcode => "InvalidFEOpcode".to_string(),
        InstructionResult::InvalidJump => "InvalidJump".to_string(),
        InstructionResult::NotActivated => "NotActivated".to_string(),
        InstructionResult::StackUnderflow => "StackUnderflow".to_string(),
        InstructionResult::StackOverflow => "StackOverflow".to_string(),
        InstructionResult::OutOfOffset => "OutOfOffset".to_string(),
        InstructionResult::CreateCollision => "CreateCollision".to_string(),
        InstructionResult::OverflowPayment => "OverflowPayment".to_string(),
        InstructionResult::PrecompileError => "PrecompileError".to_string(),
        InstructionResult::NonceOverflow => "NonceOverflow".to_string(),
        InstructionResult::CreateContractSizeLimit => "CreateContractSizeLimit".to_string(),
        InstructionResult::CreateContractStartingWithEF => {
            "CreateContractStartingWithEF".to_string()
        }
        InstructionResult::CreateInitCodeSizeLimit => "CreateInitCodeSizeLimit".to_string(),
        InstructionResult::FatalExternalError => "FatalExternalError".to_string(),
        InstructionResult::ReturnContractInNotInitEOF => "ReturnContractInNotInitEOF".to_string(),
        InstructionResult::EOFOpcodeDisabledInLegacy => "EOFOpcodeDisabledInLegacy".to_string(),
        InstructionResult::SubRoutineStackOverflow => "SubRoutineStackOverflow".to_string(),
        InstructionResult::EofAuxDataOverflow => "EofAuxDataOverflow".to_string(),
        InstructionResult::EofAuxDataTooSmall => "EofAuxDataTooSmall".to_string(),
        InstructionResult::InvalidEXTCALLTarget => "InvalidEXTCALLTarget".to_string(),
    }
}
