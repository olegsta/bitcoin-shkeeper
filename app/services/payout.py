import decimal

from app.lib.values import Value, decimal_value_to_satoshi

from ..logging import logger
from ..models import DbKey, db
from .node import NodeService
from .wallet import WalletService


class PayoutService:
    def __init__(self, wallet_service=None, node_service=None):
        self.wallet = wallet_service or WalletService()
        self.node = node_service or NodeService()

    def make_multipayout(self, payout_list, coin_fee):
        logger.warning(f'make_multipayout wallets {payout_list}')
        logger.warning(f'make_multipayout {coin_fee}')
        fee_per_kb = Value.sat_per_vbyte_to_sat_per_kb(coin_fee)
        logger.warning(f'make_multipayout fee_per_kb {fee_per_kb}')

        for payout in payout_list:
            address = self._payout_dest(payout)
            if not self.wallet.is_valid_address(address):
                raise Exception(f"Address {address} is not valid address")

        should_pay = decimal.Decimal('0')
        for payout in payout_list:
            should_pay += decimal.Decimal(str(payout['amount']))

        network_fee = decimal.Decimal(str(self.node.get_transaction_price()))
        logger.warning(f'make_multipayout network_fee get_transaction_price {self.node.get_transaction_price()}')
        network_fee_btc_per_kb = Value.sat_per_vbyte_to_sat_per_kb(network_fee)
        logger.warning(f'make_multipayout network_fee_btc_per_kb {network_fee_btc_per_kb}')

        network_fee_per_kb = fee_per_kb or network_fee_btc_per_kb
        logger.warning(f'make_multipayout network_fee_per_kb {network_fee_per_kb}')

        payout_results = []
        for payout in payout_list:
            satoshi_amount = decimal_value_to_satoshi(payout['amount'])
            address = self._payout_dest(payout)
            tx = self.wallet.current_wallet().send_to(address, satoshi_amount, fee_per_kb=network_fee_per_kb)
            payout_results.append(self._send_payout_tx(
                tx,
                success_fields={
                    "dest": address,
                    "amount": float(payout['amount']),
                },
                error_fields={
                    "dest": address,
                    "amount": float(payout['amount']),
                },
                error_log=lambda exc: f"Submit failed: {exc}",
            ))

        logger.warning(f'payout_results wallets {payout_results}')
        return payout_results

    def withdraw_to_external_wallet_task(self, payout_list):
        logger.warning(f'withdraw_to_external_wallet_task wallets {payout_list}')
        payout_results = []

        for payout in payout_list:
            source = payout.get('source')
            dest = payout.get('dest')

            if not source or not self.wallet.is_valid_address(source):
                raise Exception(f"Source address '{source}' is not valid in payout {payout}")
            if not dest or not self.wallet.is_valid_address(dest):
                raise Exception(f"Destination address '{dest}' is not valid in payout {payout}")

            key = db.session.query(DbKey).filter(DbKey.address == source).first()
            if not key:
                raise Exception(f"Source address '{source}' not found")

            tx = self.wallet.current_wallet().sweep(dest, input_key_id=key.id)
            payout_results.append(self._send_payout_tx(
                tx,
                success_fields={
                    "source": source,
                    "dest": dest,
                },
                error_fields={
                    "source": source,
                    "dest": dest,
                },
                error_log=lambda exc, src=source, dst=dest: f"Submit failed for {src} -> {dst}: {exc}",
            ))

        logger.warning(f'payout_results wallets {payout_results}')
        return payout_results

    def _payout_dest(self, payout):
        return payout.get('dest') or payout.get('destination')

    def _send_payout_tx(self, tx, success_fields, error_fields, error_log):
        try:
            tx.send()
            return {
                **success_fields,
                "status": "success",
                "txids": [str(tx)],
            }
        except Exception as e:
            logger.warning(error_log(e))
            return {
                **error_fields,
                "status": "error",
                "error": str(e),
            }
