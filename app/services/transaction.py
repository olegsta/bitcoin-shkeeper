from app.lib.values import Value

from ..models import DbTransaction, db


class TransactionLookupService:
    def get_txs_by_txid(self, txid_hex):
        txid_bytes = bytes.fromhex(txid_hex)
        return (
            db.session.query(DbTransaction)
            .filter_by(txid=txid_bytes)
            .order_by(DbTransaction.id.asc())
            .all()
        )

    def get_tx_by_txid(self, txid_hex):
        txs = self.get_txs_by_txid(txid_hex)
        return txs[0] if txs else None

    def get_transaction(self, txid_hex):
        txs = self.get_txs_by_txid(txid_hex)
        if not txs:
            return None

        details = []
        seen_outputs = set()
        confirmations = 0
        for tx in txs:
            confirmations = max(confirmations, getattr(tx, "confirmations", 0) or 0)
            for out in tx.outputs:
                if out.key_id is None:
                    continue
                dedupe_key = (out.key_id, out.output_n)
                if dedupe_key in seen_outputs:
                    continue
                seen_outputs.add(dedupe_key)
                details.append({
                    "address": out.address,
                    "amount": Value.from_satoshi(out.value).value,
                    "category": "receive",
                })

        return {
            "txid": txid_hex,
            "confirmations": confirmations,
            "details": details,
        }
