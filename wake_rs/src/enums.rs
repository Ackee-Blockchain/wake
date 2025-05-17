use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::str::FromStr;

use alloy::primitives::U160;
use alloy::primitives::utils::{parse_units, ParseUnits, UnitsError};
use pyo3::{prelude::*, IntoPyObjectExt};
use pyo3::exceptions::PyValueError;
use num_bigint::BigUint;
use revm::primitives::{Address as RevmAddress, I256, U256};

use crate::utils::big_uint_to_u256;
use crate::{account::Account, address::Address};


#[derive(FromPyObject)]
pub enum RawAddressEnum {
    #[pyo3(transparent, annotation = "int")]
    Int(BigUint),
    #[pyo3(transparent, annotation = "str")]
    String(String)
}

#[derive(FromPyObject)]
pub(crate) enum AddressEnum {
    #[pyo3(transparent, annotation = "Account")]
    Account(Py<Account>),
    #[pyo3(transparent, annotation = "Address")]
    Address(Py<Address>),
    #[pyo3(transparent, annotation = "int")]
    Int(BigUint),
    #[pyo3(transparent, annotation = "str")]
    String(String),
}

impl Clone for AddressEnum {
    fn clone(&self) -> Self {
        match self {
            Self::Account(acc) => Python::with_gil(|py| Self::Account(acc.clone_ref(py))),
            Self::Address(addr) => Python::with_gil(|py| Self::Address(addr.clone_ref(py))),
            Self::Int(i) => Self::Int(i.clone()),
            Self::String(s) => Self::String(s.clone())
        }
    }
}

impl<'py> IntoPyObject<'py> for AddressEnum {
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        match self {
            Self::Account(acc) => acc.into_bound_py_any(py),
            Self::Address(addr) => addr.into_bound_py_any(py),
            Self::Int(i) => i.into_bound_py_any(py),
            Self::String(s) => s.into_bound_py_any(py)
        }
    }
}

impl Hash for AddressEnum {
    fn hash<H: Hasher>(&self, state: &mut H) {
        let addr = Python::with_gil(|py| {
            match self {
                Self::Account(acc) => acc.borrow(py).address.borrow(py).0,
                Self::Address(addr) => addr.borrow(py).0,
                Self::Int(i) => U160::from_le_slice(&i.to_bytes_le()).into(),
                Self::String(s) => s.parse().unwrap()
            }
        });
        addr.hash(state);
    }
}

impl PartialEq for AddressEnum {
    fn eq(&self, other: &Self) -> bool {
        Python::with_gil(|py| {
            let self_addr = match self {
                Self::Account(acc) => acc.borrow(py).address.borrow(py).0,
                Self::Address(addr) => addr.borrow(py).0,
                Self::Int(i) => U160::from_le_slice(&i.to_bytes_le()).into(),
                Self::String(s) => s.parse().unwrap()
            };
            let other_addr = match other {
                Self::Account(acc) => acc.borrow(py).address.borrow(py).0,
                Self::Address(addr) => addr.borrow(py).0,
                Self::Int(i) => U160::from_le_slice(&i.to_bytes_le()).into(),
                Self::String(s) => s.parse().unwrap()
            };
            self_addr == other_addr
        })
    }
}

impl Eq for AddressEnum {}

impl TryFrom<AddressEnum> for RevmAddress {
    type Error = PyErr;

    fn try_from(value: AddressEnum) -> Result<RevmAddress, Self::Error> {
        match value {
            AddressEnum::Account(acc) => {
                Ok(Python::with_gil(|py| {
                    acc.borrow(py).address.borrow(py).0
                }))
            }
            AddressEnum::Address(addr) => {
                Ok(Python::with_gil(|py| {
                    addr.borrow(py).0
                }))
            }
            AddressEnum::Int(i) => {
                Ok(RevmAddress::from(U160::from_le_slice(&i.to_bytes_le())))
            }
            AddressEnum::String(s) => s.parse().map_err(|e: <RevmAddress as FromStr>::Err| PyValueError::new_err(e.to_string()))
        }
    }
}

impl From<revm::primitives::Address> for AddressEnum {
    fn from(value: revm::primitives::Address) -> Self {
        Python::with_gil(|py| {
            AddressEnum::Address(Py::new(py, Address::from(value)).unwrap())
        })
    }
}

#[derive(FromPyObject)]
pub(crate) enum ValueEnum {
    #[pyo3(transparent, annotation = "int")]
    Int(BigUint),
    #[pyo3(transparent, annotation = "str")]
    String(String),
}

#[derive(Debug)]
pub enum ParseUnitsError {
    MissingAmount,
    MissingUnits,
    NegativeAmount(I256),
    AmountOverflow,
    UnitsError(UnitsError),
}

impl From<ParseUnitsError> for PyErr {
    fn from(err: ParseUnitsError) -> Self {
        PyValueError::new_err(match err {
            ParseUnitsError::MissingAmount => "Missing amount".to_string(),
            ParseUnitsError::MissingUnits => "Missing units".to_string(),
            ParseUnitsError::NegativeAmount(i) => format!("Negative amount: {}", i),
            ParseUnitsError::AmountOverflow => "Amount overflow".to_string(),
            ParseUnitsError::UnitsError(e) => e.to_string()
        })
    }
}

impl TryInto<BigUint> for ValueEnum {
    type Error = ParseUnitsError;

    fn try_into(self) -> Result<BigUint, Self::Error> {
        match self {
            ValueEnum::Int(i) => Ok(i),
            ValueEnum::String(s) => {
                let mut split = s.split_ascii_whitespace();
                let amount = split.next().ok_or(ParseUnitsError::MissingAmount)?;
                let units = split.next().ok_or(ParseUnitsError::MissingUnits)?;

                match parse_units(amount, units).map_err(ParseUnitsError::UnitsError)? {
                    ParseUnits::U256(u) => Ok(BigUint::from_bytes_le(u.as_le_slice())),
                    ParseUnits::I256(i) => Err(ParseUnitsError::NegativeAmount(i))
                }
            }
        }
    }
}

impl TryInto<U256> for ValueEnum {
    type Error = ParseUnitsError;

    fn try_into(self) -> Result<U256, Self::Error> {
        match self {
            ValueEnum::Int(i) => Ok(big_uint_to_u256(i)),
            ValueEnum::String(s) => {
                let mut split = s.split_ascii_whitespace();
                let amount = split.next().ok_or(ParseUnitsError::MissingAmount)?;
                let units = split.next().ok_or(ParseUnitsError::MissingUnits)?;

                match parse_units(amount, units).map_err(ParseUnitsError::UnitsError)? {
                    ParseUnits::U256(u) => Ok(u),
                    ParseUnits::I256(i) => Err(ParseUnitsError::NegativeAmount(i))
                }
            }
        }
    }
}

impl TryInto<u128> for ValueEnum {
    type Error = ParseUnitsError;

    fn try_into(self) -> Result<u128, Self::Error> {
        match self {
            ValueEnum::Int(i) => Ok(i.try_into().map_err(|_| ParseUnitsError::AmountOverflow)?),
            ValueEnum::String(s) => {
                let mut split = s.split_ascii_whitespace();
                let amount = split.next().ok_or(ParseUnitsError::MissingAmount)?;
                let units = split.next().ok_or(ParseUnitsError::MissingUnits)?;

                match parse_units(amount, units).map_err(ParseUnitsError::UnitsError)? {
                    ParseUnits::U256(u) => {
                        let limbs = u.as_limbs();
                        let lower_128 = (limbs[0] as u128) | ((limbs[1] as u128) << 64);

                        if limbs[2] == 0 && limbs[3] == 0 {
                            Ok(lower_128)
                        } else {
                            Err(ParseUnitsError::AmountOverflow)
                        }
                    }
                    ParseUnits::I256(i) => Err(ParseUnitsError::NegativeAmount(i))
                }
            }
        }
    }
}

pub(crate) enum GasLimitEnum {
    Int(BigUint),
    Max,
    Auto,
}

impl FromPyObject<'_> for GasLimitEnum {
    fn extract_bound(ob: &Bound<'_, PyAny>) -> PyResult<Self> {
        if let Ok(int) = ob.extract::<BigUint>() {
            Ok(Self::Int(int))
        } else {
            let s = ob.extract::<String>()?;
            match s.as_str() {
                "max" => Ok(Self::Max),
                "auto" => Ok(Self::Auto),
                _ => Err(
                    PyValueError::new_err("Invalid gas limit value")
                )
            }
        }
    }
}

pub(crate) enum AccessListEnum {
    Dictionary(HashMap<AddressEnum, Vec<BigUint>>),
    Auto,
}

impl FromPyObject<'_> for AccessListEnum {
    fn extract_bound(ob: &Bound<'_, PyAny>) -> PyResult<Self> {
        if let Ok(dict) = ob.extract::<HashMap<AddressEnum, Vec<BigUint>>>() {
            Ok(Self::Dictionary(dict))
        } else {
            let s = ob.extract::<String>()?;
            match s.as_str() {
                "auto" => Ok(Self::Auto),
                _ => Err(
                    PyValueError::new_err("Invalid access list value")
                )
            }
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum BlockEnum {
    Int(u64),
    Latest,
    Pending,
    Earliest,
    Safe,
    Finalized,
}

impl<'py> IntoPyObject<'py> for BlockEnum {
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        match self {
            Self::Int(i) => i.into_bound_py_any(py),
            Self::Latest => "latest".into_bound_py_any(py),
            Self::Pending => "pending".into_bound_py_any(py),
            Self::Earliest => "earliest".into_bound_py_any(py),
            Self::Safe => "safe".into_bound_py_any(py),
            Self::Finalized => "finalized".into_bound_py_any(py),
        }
    }
}

impl FromPyObject<'_> for BlockEnum {
    fn extract_bound(ob: &Bound<'_, PyAny>) -> PyResult<Self> {
        if let Ok(int) = ob.extract::<u64>() {
            Ok(Self::Int(int))
        } else {
            let s = ob.extract::<String>()?;
            match s.as_str() {
                "latest" => Ok(Self::Latest),
                "pending" => Ok(Self::Pending),
                "earliest" => Ok(Self::Earliest),
                "safe" => Ok(Self::Safe),
                "finalized" => Ok(Self::Finalized),
                _ => Err(
                    PyValueError::new_err("Invalid block value")
                )
            }
        }
    }
}

#[derive(PartialEq)]
pub(crate) enum RequestTypeEnum {
    Tx,
    Call,
    Estimate,
    AccessList,
}

impl FromPyObject<'_> for RequestTypeEnum {
    fn extract_bound(ob: &Bound<'_, PyAny>) -> PyResult<Self> {
        let s = ob.extract::<&str>()?;
        match s {
            "tx" => Ok(Self::Tx),
            "call" => Ok(Self::Call),
            "estimate" => Ok(Self::Estimate),
            "access_list" => Ok(Self::AccessList),
            _ => Err(
                PyValueError::new_err("Invalid request type value")
            )
        }
    }
}
