from app.lib.values import Value

from ..models import DbTransaction, db


class TransactionLookupService:
    def get_tx_by_txid(self, txid_hex):
        txid_bytes = bytes.fromhex(txid_hex)
        return db.session.query(DbTransaction).filter_by(txid=txid_bytes).one_or_none()

    def get_transaction(self, txid_hex):
        tx = self.get_tx_by_txid(txid_hex)
        if not tx:
            return None

        details = []
        for out in tx.outputs:
            if out.key_id is None:
                continue
            details.append({
                'address': out.address,
                'amount': Value.from_satoshi(out.value).value,
                'category': 'receive',
            })

        return {
            'txid': txid_hex,
            'confirmations': getattr(tx, 'confirmations', 0),
            'details': details,
        }
