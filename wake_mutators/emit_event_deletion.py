from wake.mutators.api import Mutator
from wake.ir.statements.emit_statement import EmitStatement


class EmitEventDeletion(Mutator):
    """Remove emit statements."""

    name = "emit_event_deletion"
    description = "Remove emit statements"

    def visit_emit_statement(self, node: EmitStatement):
        self._add(
            node=node,
            original=node.source,
            replacement="true",
            description="Remove emit statement",
        )
