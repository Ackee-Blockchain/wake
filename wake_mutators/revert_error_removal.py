from wake.mutators.api import Mutator
from wake.ir.statements.revert_statement import RevertStatement


class RevertErrorRemoval(Mutator):
    """Replace revert Error(...) with revert()."""

    name = "revert_error_removal"
    description = "Replace revert Error(...) with revert()"

    def visit_revert_statement(self, node: RevertStatement):
        print(node.source)
        self._add(
            node=node,
            original=node.source,
            replacement="revert()",
            description="Remove revert error",
        )
