import decimal

from app.lib.values import Value, decimal_value_to_satoshi

from ..logging import logger
from ..models import DbKey, db
from .node import NodeService
from .wallet import WalletService
from . import store as store_service


class PayoutService:
    def __init__(self, wallet_service=None, node_service=None):
        self.wallet = wallet_service or WalletService()
        self.node = node_service or NodeService()

    def make_multipayout(self, payout_list, coin_fee, store_id=None):
        logger.warning(f'make_multipayout wallets {payout_list}')
        logger.warning(f'make_multipayout {coin_fee}')
        fee_per_kb = Value.sat_per_vbyte_to_sat_per_kb(coin_fee)
        logger.warning(f'make_multipayout fee_per_kb {fee_per_kb}')
        store_id = store_service.parse_store_id(store_id)
        store_keys = store_service.store_address_keys(store_id)
        if not store_keys:
            raise Exception(f"No keys found for store_id={store_id}")
        input_key_ids = [key.id for key in store_keys]
        change_key = store_service.pick_change_key(store_keys)
        if not change_key:
            raise Exception(f"No change key found for store_id={store_id}")

        transfers = []
        for payout in payout_list:
            address = self._payout_dest(payout)
            if not self.wallet.is_valid_address(address):
                raise Exception(f"Address {address} is not valid address")
            amount = decimal.Decimal(str(payout['amount']))
            transfers.append({
                "dest": address,
                "amount": amount,
                "satoshi": decimal_value_to_satoshi(amount),
            })

        network_fee = decimal.Decimal(str(self.node.get_transaction_price()))
        logger.warning("make_multipayout network_fee get_transaction_price %s", network_fee)
        network_fee_btc_per_kb = Value.sat_per_vbyte_to_sat_per_kb(network_fee)
        logger.warning(f'make_multipayout network_fee_btc_per_kb {network_fee_btc_per_kb}')

        network_fee_per_kb = fee_per_kb or network_fee_btc_per_kb
        logger.warning(f'make_multipayout network_fee_per_kb {network_fee_per_kb}')

        # One Bitcoin tx with all payment outputs (sendmany-style), not one tx per dest.
        hd_wallet = self.wallet.current_wallet(store_id=store_id)
        if not hd_wallet:
            raise Exception(f"No wallet found for store_id={store_id}")
        output_arr = [(t["dest"], t["satoshi"]) for t in transfers]
        try:
            tx = hd_wallet.send(
                output_arr,
                fee_per_kb=network_fee_per_kb,
                input_key_id=input_key_ids,
                change_key_id=change_key.id,
            )
            tx.send()
            txid = str(tx)
            payout_results = [
                {
                    "dest": t["dest"],
                    "amount": float(t["amount"]),
                    "status": "success",
                    "txids": [txid],
                }
                for t in transfers
            ]
        except Exception as e:
            logger.warning(f"Submit failed: {e}")
            payout_results = [
                {
                    "dest": t["dest"],
                    "amount": float(t["amount"]),
                    "status": "error",
                    "error": str(e),
                }
                for t in transfers
            ]

        logger.warning(f'payout_results wallets {payout_results}')
        return payout_results

    def assert_sources_belong_to_store(self, payout_list, store_id):
        store_id = store_service.parse_store_id(store_id)
        for payout in payout_list:
            source = payout.get("source") if isinstance(payout, dict) else None
            if not source:
                continue
            key = store_service._query_first(
                db.session.query(DbKey).filter(DbKey.address == source)
            )
            if key and key.wallet:
                actual_store_id = key.wallet.store_id or store_service.DEFAULT_STORE_ID
                if actual_store_id != store_id:
                    raise Exception(
                        f"Source address '{source}' does not belong to store_id={store_id}"
                    )

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

            key = store_service._query_first(
                db.session.query(DbKey).filter(DbKey.address == source)
            )
            if not key:
                raise Exception(f"Source address '{source}' not found")

            store_id = key.wallet.store_id if key.wallet is not None else None
            hd_wallet = self.wallet.current_wallet(store_id=store_id)
            if not hd_wallet:
                raise Exception(f"No wallet found for source address '{source}'")
            tx = hd_wallet.sweep(dest, input_key_id=key.id)
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
