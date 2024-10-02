from typing import Any

from IPython.terminal.debugger import TerminalPdb


class CustomPdb(TerminalPdb):
    def __init__(self, program_instance, *args, **kwargs):
        """
        Custom Pdb constructor to accept the stdin and connection.
        """
        super().__init__(*args, **kwargs)  # Initialize the base Pdb class
        self._program_instance = program_instance

    def do_continue(self, arg):
        """
        Override the 'continue' (c) command to perform cleanup after continuing.
        """
        self.cleanup_before_exit()
        return super().do_continue(arg)

    do_c = do_cont = do_continue

    def do_quit(self, arg):
        """
        Override the 'quit' (q) command to perform cleanup before quitting.
        """
        self.cleanup_before_exit()
        return super().do_quit(arg)

    do_q = do_exit = do_quit

    def cleanup_before_exit(self):
        """
        This function performs the cleanup before exiting the debugger.
        """
        self._program_instance._setup_stdio()
        self._program_instance._conn.send(("breakpoint_handled",))
