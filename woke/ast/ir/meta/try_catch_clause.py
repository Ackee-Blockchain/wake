from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple

from ...enums import ModifiesStateFlag
from ..statement.block import Block
from ..utils import IrInitTuple
from .parameter_list import ParameterList

if TYPE_CHECKING:
    from ..statement.try_statement import TryStatement

from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.nodes import SolcTryCatchClause


class TryCatchClause(SolidityAbc):
    """
    !!! example
        - `:::solidity returns(uint x) {}`,
        - `:::solidity catch Error(string memory reason) {}`,
        - `:::solidity catch Panic(uint errorCode) {}`,
        - `:::solidity catch (bytes memory lowLevelData) {}` are all try/catch clauses in the following example:
        ```solidity
        contract C {
            function foo() public view {
                try this.bar(10) returns(uint x) {}
                catch Error(string memory reason) {}
                catch Panic(uint errorCode) {}
                catch (bytes memory lowLevelData) {}
            }

            function bar(uint x) external pure returns(uint) {
                return x;
            }
        }
        ```
    """
    _ast_node: SolcTryCatchClause
    _parent: TryStatement

    __block: Block
    __error_name: str
    __parameters: Optional[ParameterList]

    def __init__(
        self,
        init: IrInitTuple,
        try_catch_clause: SolcTryCatchClause,
        parent: TryStatement,
    ):
        super().__init__(init, try_catch_clause, parent)
        self.__block = Block(init, try_catch_clause.block, self)
        self.__error_name = try_catch_clause.error_name

        if try_catch_clause.parameters is None:
            self.__parameters = None
        else:
            self.__parameters = ParameterList(init, try_catch_clause.parameters, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self.__block
        if self.__parameters is not None:
            yield from self.__parameters

    @property
    def parent(self) -> TryStatement:
        """
        Returns:
            Parent IR node.
        """
        return self._parent

    @property
    def block(self) -> Block:
        """
        Returns:
            Body of the try/catch clause.
        """
        return self.__block

    @property
    def error_name(self) -> str:
        """
        !!! example
            For the following snippet:
            ```solidity
            try this.f() returns (uint256) {
                // ...
            } catch Error(string memory reason) {
                // ...
            } catch Panic(uint errorCode) {
                // ...
            } catch (bytes memory lowLevelData) {
                // ...
            }
            ```

            - the `error_name` of the first (try) clause is empty,
            - the `error_name` of the second (catch) clause is `Error`,
            - the `error_name` of the third (catch) clause is `Panic`,
            - the `error_name` of the fourth (catch) clause is empty.
        Returns:
            Error name of the try/catch clause.
        """
        return self.__error_name

    @property
    def parameters(self) -> Optional[ParameterList]:
        """
        Can be `None` if the try clause does not have return parameters or if the catch clause does not accept parameters.
        !!! example
            Both clauses in the following example do not have parameters:
            ```solidity
            try this.f() {
                // ...
            } catch {
                // ...
            }
            ```

        !!! example
            `:::solidity (uint x)`, `:::solidity (string memory reason)`, `:::solidity (uint errorCode)` and `:::solidity (bytes memory lowLevelData)` are the parameters of the try/catch clauses in the following example:
            ```solidity
            try this.f() returns (uint x) {
                // ...
            } catch Error(string memory reason) {
                // ...
            } catch Panic(uint errorCode) {
                // ...
            } catch (bytes memory lowLevelData) {
                // ...
            }
            ```

        Returns:
            Return parameters in the case of a try clause, or error parameters in the case of a catch clause.
        """
        return self.__parameters

    @property
    @lru_cache(maxsize=None)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        return self.block.modifies_state
