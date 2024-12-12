from wake.deployment import *

NODE_URL = "ENTER_NODE_URL_HERE"


@chain.connect(NODE_URL)
def main():
    chain.set_default_accounts(Account.from_alias("deployment"))
