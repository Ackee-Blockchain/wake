import pdb
import sys

class CustomPdb(pdb.Pdb):
    def __init__(self, prev_stdin, conn, *args, **kwargs):
        """
        Custom Pdb constructor to accept the stdin and connection.
        """
        super().__init__(*args, **kwargs)  # Initialize the base Pdb class
        self.prev_stdin = prev_stdin  # Store the original stdin
        self.conn = conn  # Store the connection for parent communication

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
        print("Performing cleanup before exiting the debugger...")
        sys.stdin = self.prev_stdin  # Restore stdin to its original state
        self.conn.send(("breakpoint_handled",))  