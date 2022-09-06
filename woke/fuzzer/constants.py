#tab space width for indentation
TAB_WIDTH = 4

#TODO move to constants file
DEFAULT_IMPORTS: str = """
import random 
from dataclasses import dataclass 
from typing import List, NewType, Optional, overload, Union

from woke.fuzzer.contract import Contract

from eth_typing import AnyAddress, HexStr
from web3 import Web3, WebsocketProvider, HTTPProvider
from web3.method import Method
from web3.types import TxParams, Address, RPCEndpoint
"""
