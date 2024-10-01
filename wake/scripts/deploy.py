from wake.deployment import *

NODE_URL = "ENTER_NODE_URL_HERE"


@default_chain.connect(NODE_URL)
def main():
    default_chain.set_default_accounts(Account.from_alias("deployment"))
