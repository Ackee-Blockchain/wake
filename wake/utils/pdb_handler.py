import sys

from rich import print as rich_print


def breakpoint_handler(frame=None, context=None, cond=True):
    import inspect
    from ipdb.__main__ import _init_pdb, wrap_sys_excepthook

    if not cond:
        return
    wrap_sys_excepthook()
    if frame is None:
        frame = sys._getframe().f_back
    p = _init_pdb(context)
    p.default = lambda line: default_handler(p, line)
    x = p.set_trace(frame)
    if x and hasattr(p, 'shell'):
        x.shell.restore_sys_module_state()


def default_handler(self, line):
    # If line starts with '!', strip it and remove leading/trailing whitespace
    if line[:1] == '!':
        line = line[1:].strip()

    locals = self.curframe_locals
    globals = self.curframe.f_globals

    try:
        # Compile the input line as a single interactive statement
        code = compile(line, "<stdin>", "single")

        # Save current I/O and displayhook
        save_stdout = sys.stdout
        save_stdin = sys.stdin
        save_displayhook = sys.displayhook

        try:
            # Redirect I/O to use the debugger's streams
            sys.stdin = self.stdin
            sys.stdout = self.stdout
            sys.displayhook = self.displayhook

            try:
                result = eval(line, globals, locals)
                if result is not None:
                    rich_print(result)
                    locals['_'] = result
            except SyntaxError:
                # Execute the compiled code in the current frame's context
                exec(code, globals, locals)

        finally:
            # Restore original I/O and displayhook
            sys.stdout = save_stdout
            sys.stdin = save_stdin
            sys.displayhook = save_displayhook

    except:
        # Handle and report any exceptions
        self._error_exc()
