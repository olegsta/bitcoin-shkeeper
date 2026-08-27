from .config import config
from .services import NodeService, PayoutService, TransactionLookupService, WalletService


class CoinWallet:
    def __init__(self) -> None:
        self.client = config["FULLNODE_URL"]
        self._node = NodeService()
        self._wallet = WalletService()
        self._transactions = TransactionLookupService()
        self._payouts = PayoutService(wallet_service=self._wallet, node_service=self._node)

    def get_tx_by_txid(self, txid_hex):
        return self._transactions.get_tx_by_txid(txid_hex)

    def get_transaction(self, txid_hex):
        return self._transactions.get_transaction(txid_hex)

    def delta_synced_block(self):
        return self._node.delta_synced_block()

    def getblockchaininfo(self):
        return self._node.getblockchaininfo()

    def get_last_block_number(self):
        return self._node.get_last_block_number()

    def get_transaction_price(self):
        return self._node.get_transaction_price()

    def get_fee_deposit_account(self):
        return self._wallet.get_fee_deposit_account()

    def current_wallet(self):
        return self._wallet.current_wallet()

    def wallet(self):
        return self._wallet.wallet()

    def get_deposit_account_balance(self):
        return self._wallet.get_deposit_account_balance()

    def db_wallet(self):
        return self._wallet.db_wallet()

    def wallet_name(self):
        return self._wallet.wallet_name()

    def get_dump(self):
        return self._wallet.get_dump()

    def get_all_addresses(self):
        return self._wallet.get_all_addresses()

    def get_all_accounts(self):
        return self._wallet.get_all_accounts()

    def generate_wallet_name(self):
        return self._wallet.generate_wallet_name()

    def generate_address(self):
        return self._wallet.generate_address()

    def witness_type(self):
        return self._wallet.witness_type()

    def make_multipayout(self, payout_list, coin_fee):
        return self._payouts.make_multipayout(payout_list, coin_fee)

    def withdraw_to_external_wallet_task(self, payout_list):
        return self._payouts.withdraw_to_external_wallet_task(payout_list)

    def is_valid_address(self, address: str) -> bool:
        return self._wallet.is_valid_address(address)
