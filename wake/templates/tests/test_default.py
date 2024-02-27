from wake.testing import *

# Print failing tx call trace
# def revert_handler(e: TransactionRevertedError):
#     if e.tx is not None:
#         print(e.tx.call_trace)

@default_chain.connect()
# @on_revert(revert_handler)
def test_default():
    pass
