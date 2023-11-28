from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Union

from wake.ir.enums import ModifiesStateFlag

from ..statements.block import Block
from ..utils import IrInitTuple
from .parameter_list import ParameterList

if TYPE_CHECKING:
    from ..expressions.abc import ExpressionAbc
    from ..statements.abc import StatementAbc
    from ..statements.try_statement import TryStatement
    from ..yul.abc import YulAbc

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcTryCatchClause


class TryCatchClause(SolidityAbc):
    """
    !!! example
        All the following are try/catch clauses in the example below:

        - `:::solidity returns(uint x) {}`,
        - `:::solidity catch Error(string memory reason) {}`,
        - `:::solidity catch Panic(uint errorCode) {}`,
        - `:::solidity catch (bytes memory lowLevelData) {}`.

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

    _block: Block
    _error_name: str
    _parameters: Optional[ParameterList]

    def __init__(
        self,
        init: IrInitTuple,
        try_catch_clause: SolcTryCatchClause,
        parent: TryStatement,
    ):
        super().__init__(init, try_catch_clause, parent)
        self._block = Block(init, try_catch_clause.block, self)
        self._error_name = try_catch_clause.error_name

        if try_catch_clause.parameters is None:
            self._parameters = None
        else:
            self._parameters = ParameterList(init, try_catch_clause.parameters, self)

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._block
        if self._parameters is not None:
            yield from self._parameters

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
        return self._block

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

            - is empty for the first (try) clause,
            - is `Error` for the second (catch) clause,
            - is `Panic` for the third (catch) clause,
            - is empty for the fourth (catch) clause.

        Returns:
            Error name of the try/catch clause.
        """
        return self._error_name

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
        return self._parameters

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(
        self,
    ) -> Set[Tuple[Union[ExpressionAbc, StatementAbc, YulAbc], ModifiesStateFlag]]:
        return self.block.modifies_state
