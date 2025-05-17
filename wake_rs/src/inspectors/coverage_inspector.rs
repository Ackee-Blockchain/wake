use std::{collections::HashMap, sync::Mutex, time::Duration};

use blake2::{digest::consts::U32, Blake2b, Digest};
use lazy_static::lazy_static;
use pyo3::sync::GILOnceCell;
use pyo3::{prelude::*, types::PyFunction};
use revm::context::ContextTr;
use revm::inspector::JournalExt;
use revm::interpreter::interpreter_types::Jumps;
use revm::interpreter::{
    CallInputs, CallOutcome, CreateInputs, CreateOutcome, EOFCreateInputs, Interpreter,
};
use revm::primitives::Log;
use revm::{primitives::Bytes, Inspector};
use rust_lapper::{Interval, Lapper};

use super::fqn_inspector::FqnInspector;

// Type alias for a creation code segment
type CreationCodeSegment = (usize, Vec<u8>);

// Type alias for a creation code entry
type CreationCodeEntry = (Vec<CreationCodeSegment>, String);

type AstId = (u32, u32);

type Pc = u32;

fn is_solidity_statement(kind: &str) -> bool {
    matches!(
        kind,
        "Break"
            | "Continue"
            | "DoWhileStatement"
            | "EmitStatement"
            | "ExpressionStatement"
            | "ForStatement"
            | "IfStatement"
            | "InlineAssembly"
            | "PlaceholderStatement"
            | "Return"
            | "RevertStatement"
            | "TryStatement"
            | "VariableDeclarationStatement"
            | "WhileStatement"
    )
}

fn is_yul_statement(kind: &str) -> bool {
    matches!(
        kind,
        "YulAssignment"
            | "YulBlock"
            | "YulBreak"
            | "YulContinue"
            | "YulExpressionStatement"
            | "YulForLoop"
            | "YulFunctionDefinition"
            | "YulIf"
            | "YulLeave"
            | "YulSwitch"
            | "YulVariableDeclaration"
    )
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum AstKind {
    Statement,
    YulStatement,
    FunctionDefinition,
    ModifierDefinition,
    ContractDefinition,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct SimplifiedAstNode {
    //id: AstId,
    kind: AstKind,
    original_kind: String,
    byte_offsets: (u32, u32),
    ast_tree_depth: u32,
    source: String,
}

pub(crate) struct CoverageHelpers {
    fqn_by_metadata: HashMap<Vec<u8>, String>,
    // list of pairs of (creation code segments, contract_fqn)
    // where creation code segments is a tuple of (length, BLAKE2b hash)
    init_code_index: Vec<CreationCodeEntry>,
    ast_laps: HashMap<String, Lapper<u32, SimplifiedAstNode>>,
    pc_map: HashMap<String, HashMap<Pc, (String, u32, u32)>>,
    deployment_pc_map: HashMap<String, HashMap<Pc, (String, u32, u32)>>,
    sync_timeout: Duration,

    callback_function: Option<Py<PyFunction>>,
}

static mut COVERAGE_HELPERS: GILOnceCell<CoverageHelpers> = GILOnceCell::new();

#[allow(static_mut_refs)]
#[pyfunction]
pub(crate) fn set_coverage_callback(py: Python<'_>, callback: Py<PyFunction>) {
    get_coverage_helpers(py);
    unsafe {
        COVERAGE_HELPERS.get_mut().unwrap().callback_function = Some(callback);
    }
}

#[allow(static_mut_refs)]
pub(crate) fn get_coverage_helpers(py: Python<'_>) -> &'static CoverageHelpers {
    unsafe {
        COVERAGE_HELPERS.get_or_init(py, || {
            let fqn_by_metadata = py
                .import("wake.development.core")
                .unwrap()
                .getattr("contracts_by_metadata")
                .unwrap()
                .extract::<HashMap<Vec<u8>, String>>()
                .unwrap();

            let init_code_index = py
                .import("wake.development.core")
                .unwrap()
                .getattr("creation_code_index")
                .unwrap()
                .extract::<Vec<(Vec<CreationCodeSegment>, String)>>()
                .unwrap();

            let pc_map = py
                .import("wake.testing.native_coverage")
                .unwrap()
                .getattr("pc_map")
                .unwrap()
                .extract::<HashMap<String, HashMap<Pc, (String, u32, u32)>>>()
                .unwrap();

            let deployment_pc_map = py
                .import("wake.testing.native_coverage")
                .unwrap()
                .getattr("deployment_pc_map")
                .unwrap()
                .extract::<HashMap<String, HashMap<Pc, (String, u32, u32)>>>()
                .unwrap();

            let flattened_ast = py
                .import("wake.testing.native_coverage")
                .unwrap()
                .getattr("flattened_ast")
                .unwrap()
                .extract::<HashMap<String, Vec<(String, u32, u32, u32, String)>>>()
                .unwrap();

            let mut ast_laps = HashMap::default();
            for (fqn, ast_nodes) in flattened_ast.iter() {
                let intervals = ast_nodes
                    .iter()
                    .filter_map(|(kind, start, end, depth, source)| {
                        let new_kind = match kind.as_str() {
                            kind if is_solidity_statement(kind) => Some(AstKind::Statement),
                            kind if is_yul_statement(kind) => Some(AstKind::YulStatement),
                            "FunctionDefinition" => Some(AstKind::FunctionDefinition),
                            "ModifierDefinition" => Some(AstKind::ModifierDefinition),
                            "ContractDefinition" => Some(AstKind::ContractDefinition),
                            _ => None,
                        };

                        match new_kind {
                            Some(new_kind) => Some(Interval {
                                start: *start,
                                stop: *end,
                                val: SimplifiedAstNode {
                                    kind: new_kind,
                                    original_kind: kind.clone(),
                                    byte_offsets: (*start, *end),
                                    ast_tree_depth: *depth,
                                    source: source.clone(),
                                },
                            }),
                            None => None,
                        }
                    })
                    .collect();

                ast_laps.insert(fqn.clone(), Lapper::new(intervals));
            }

            let sync_timeout = py
                .import("wake.testing.native_coverage")
                .unwrap()
                .getattr("sync_timeout")
                .unwrap()
                .extract::<f64>()
                .unwrap();

            CoverageHelpers {
                fqn_by_metadata,
                init_code_index,
                ast_laps,
                pc_map,
                deployment_pc_map,
                sync_timeout: Duration::from_secs_f64(sync_timeout),
                callback_function: None,
            }
        })
    }
}

lazy_static! {
    static ref STATEMENT_COVERAGE: Mutex<HashMap<String, HashMap<AstId, u32>>> =
        Mutex::new(HashMap::new());
    static ref LAST_SYNC: Mutex<std::time::Instant> = Mutex::new(std::time::Instant::now());
}

#[pyfunction]
pub fn sync_coverage(py: Python<'_>) -> PyResult<()> {
    if let Some(callback) = &get_coverage_helpers(py).callback_function {
        let guard = STATEMENT_COVERAGE.lock().unwrap();

        callback.call1(py, (guard.clone(),))?;
    }

    Ok(())
}

pub(crate) struct CoverageInspector {
    coverage_helpers: &'static CoverageHelpers,

    last_statement: HashMap<(u32, u32), (AstId, Pc)>,
    statement_coverage: HashMap<String, HashMap<AstId, u32>>,
    fqn_stack: Vec<Option<String>>,
    pc_map_stack: Vec<Option<&'static HashMap<Pc, (String, u32, u32)>>>,

    pub fqn_inspector: FqnInspector,
}

impl CoverageInspector {
    pub fn new() -> Self {
        let ret = Self {
            coverage_helpers: Python::with_gil(|py| get_coverage_helpers(py)),
            statement_coverage: HashMap::default(),
            last_statement: HashMap::new(),
            fqn_stack: Vec::new(),
            pc_map_stack: Vec::new(),
            fqn_inspector: FqnInspector::new(),
        };
        ret
    }

    fn get_fqn_from_creation_code(&self, init_code: &Bytes) -> Option<String> {
        let mut hasher: Blake2b<U32> = Blake2b::new();

        for (segments, fqn) in self.coverage_helpers.init_code_index.iter() {
            let (length, hash) = segments.first().unwrap();
            if *length > init_code.len() {
                continue;
            }

            Digest::update(&mut hasher, init_code.slice(0..*length));
            if Digest::finalize_reset(&mut hasher).as_slice() != hash {
                continue;
            }

            let mut found = true;
            let mut offset = *length;

            for (length, hash) in segments.iter().skip(1) {
                if offset + *length > init_code.len() - offset {
                    found = false;
                    break;
                }

                Digest::update(
                    &mut hasher,
                    init_code.slice(offset + 20..offset + 20 + *length),
                );
                if Digest::finalize_reset(&mut hasher).as_slice() != hash {
                    found = false;
                    break;
                }

                offset += *length;
            }

            if found {
                return Some(fqn.clone());
            }
        }

        None
    }

    pub fn update_coverage(&mut self, py: Python<'_>) -> PyResult<()> {
        let mut guard = STATEMENT_COVERAGE.lock().unwrap();

        for (source_unit_name, coverage) in self.statement_coverage.iter() {
            for (ast_id, count) in coverage.iter() {
                guard
                    .entry(source_unit_name.clone())
                    .or_insert(HashMap::new())
                    .entry(ast_id.clone())
                    .and_modify(|e| *e += *count)
                    .or_insert(*count);
            }
        }

        let now = std::time::Instant::now();
        let mut last_sync = LAST_SYNC.lock().unwrap();

        if let Some(callback) = &self.coverage_helpers.callback_function {
            if now.duration_since(*last_sync) >= self.coverage_helpers.sync_timeout {
                callback.call1(py, (guard.clone(),))?;

                *last_sync = now;
            }
        }

        Ok(())
    }
}

impl<CTX: ContextTr<Journal: JournalExt>> Inspector<CTX> for CoverageInspector {
    fn call(&mut self, context: &mut CTX, inputs: &mut CallInputs) -> Option<CallOutcome> {
        let fqn = self.fqn_inspector.get_metadata(inputs.bytecode_address, context)
            .and_then(|metadata| self.coverage_helpers.fqn_by_metadata.get(&metadata).cloned());

        match &fqn {
            Some(fqn) => {
                self.fqn_stack.push(Some(fqn.clone()));
                self.pc_map_stack
                    .push(self.coverage_helpers.pc_map.get(fqn));
            }
            None => {
                self.fqn_stack.push(None);
                self.pc_map_stack.push(None);
            }
        }

        self.fqn_inspector.call(context, inputs)
    }

    fn call_end(&mut self, context: &mut CTX, inputs: &CallInputs, outcome: &mut CallOutcome) {
        self.fqn_stack.pop().unwrap();
        self.pc_map_stack.pop().unwrap();

        self.fqn_inspector.call_end(context, inputs, outcome)
    }

    fn log(&mut self, interp: &mut Interpreter, context: &mut CTX, log: Log) {
        self.fqn_inspector.log(interp, context, log)
    }

    fn create(&mut self, context: &mut CTX, inputs: &mut CreateInputs) -> Option<CreateOutcome> {
        let fqn = self.get_fqn_from_creation_code(&inputs.init_code);
        match &fqn {
            Some(fqn) => {
                self.fqn_stack.push(Some(fqn.clone()));
                self.pc_map_stack
                    .push(self.coverage_helpers.deployment_pc_map.get(fqn));
            }
            None => {
                self.fqn_stack.push(None);
                self.pc_map_stack.push(None);
            }
        }

        self.fqn_inspector.create(context, inputs)
    }

    fn create_end(
        &mut self,
        context: &mut CTX,
        inputs: &CreateInputs,
        outcome: &mut CreateOutcome,
    ) {
        self.fqn_stack.pop().unwrap();
        self.pc_map_stack.pop().unwrap();

        self.fqn_inspector.create_end(context, inputs, outcome)
    }

    fn eofcreate(
        &mut self,
        _context: &mut CTX,
        _inputs: &mut EOFCreateInputs,
    ) -> Option<CreateOutcome> {
        todo!()
    }

    fn eofcreate_end(
        &mut self,
        _context: &mut CTX,
        _inputs: &EOFCreateInputs,
        _outcome: &mut CreateOutcome,
    ) {
        todo!()
    }

    fn step(&mut self, interp: &mut Interpreter, _context: &mut CTX) {
        let pc = interp.bytecode.pc() as u32;

        let pc_map_record = match self.pc_map_stack.last().unwrap() {
            Some(pc_map) => match pc_map.get(&pc) {
                Some(record) => record,
                None => {
                    return;
                }
            },
            None => {
                return;
            }
        };
        let ast_nodes = match self.coverage_helpers.ast_laps.get(&pc_map_record.0) {
            Some(ast_lap) => ast_lap.find(pc_map_record.1, pc_map_record.2),
            None => {
                return;
            }
        };

        let mut function: Option<&SimplifiedAstNode> = None;
        let mut modifier: Option<&SimplifiedAstNode> = None;
        let mut statement: Option<&SimplifiedAstNode> = None;
        let mut yul_statement: Option<&SimplifiedAstNode> = None;
        for node in ast_nodes {
            match node.val.kind {
                AstKind::FunctionDefinition => {
                    if function.is_some()
                        || modifier.is_some()
                        || (pc_map_record.1, pc_map_record.2) == node.val.byte_offsets
                    {
                        // multiple functions/modifiers matching the pc
                        return;
                    } else {
                        function = Some(&node.val);
                    }
                }
                AstKind::ModifierDefinition => {
                    if function.is_some()
                        || modifier.is_some()
                        || (pc_map_record.1, pc_map_record.2) == node.val.byte_offsets
                    {
                        // multiple functions/modifiers matching the pc
                        return;
                    } else {
                        modifier = Some(&node.val);
                    }
                }
                AstKind::Statement => {
                    if statement.is_some() {
                        // multiple statements matching the pc
                        return;
                    }

                    statement = Some(&node.val);
                }
                AstKind::YulStatement => {
                    if yul_statement.is_some() {
                        // multiple yul statements matching the pc
                        return;
                    }

                    yul_statement = Some(&node.val);
                }
                AstKind::ContractDefinition => {
                    if (pc_map_record.1, pc_map_record.2) == node.val.byte_offsets {
                        return;
                    }
                }
            }
        }

        let declaration = if let Some(function) = function {
            function.byte_offsets
        } else if let Some(modifier) = modifier {
            modifier.byte_offsets
        } else {
            return;
        };

        if let Some(yul_statement) = yul_statement {
            if self
                .last_statement
                .get(&declaration)
                .is_none_or(|s| s.0 != yul_statement.byte_offsets || s.1 >= pc)
            {
                *self
                    .statement_coverage
                    .entry(pc_map_record.0.clone())
                    .or_insert(HashMap::new())
                    .entry(yul_statement.byte_offsets)
                    .or_insert(0) += 1;

                self.last_statement
                    .insert(declaration, (yul_statement.byte_offsets, pc));
            }
        } else if let Some(statement) = statement {
            if self
                .last_statement
                .get(&declaration)
                .is_none_or(|s| s.0 != statement.byte_offsets || s.1 >= pc)
            {
                *self
                    .statement_coverage
                    .entry(pc_map_record.0.clone())
                    .or_insert(HashMap::new())
                    .entry(statement.byte_offsets)
                    .or_insert(0) += 1;

                self.last_statement
                    .insert(declaration, (statement.byte_offsets, pc));
            }
        }
    }
}
