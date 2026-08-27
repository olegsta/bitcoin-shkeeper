from flask import g, jsonify

from app.logging import logger
from app.services import NodeService, TransactionLookupService, WalletService
from app.utils import block_during_migration

from . import api


@api.post("/generate-address")
@block_during_migration
def generate_new_address():
    logger.warning("generate-address request started for symbol=%s", g.symbol)
    new_address = WalletService().generate_address()
    logger.warning("generate-address request result symbol=%s address=%s", g.symbol, new_address)
    if not new_address:
        logger.error("Failed to generate address for symbol=%s", g.symbol)
        return jsonify({
            'status': 'error',
            'message': 'Failed to generate address'
        }), 500
    return {'status': 'success', 'address': new_address}


@api.post('/balance')
def get_balance():
    balance = WalletService().get_deposit_account_balance()
    return {'status': 'success', 'balance': balance}


@api.post('/status')
@block_during_migration
def get_status():
    delta_blocks = NodeService().delta_synced_block()
    return {'status': 'success', 'delta_blocks': delta_blocks}


@api.post('/transaction/<txid>')
def get_transaction(txid):
    transaction = TransactionLookupService().get_transaction(txid)
    if not transaction:
        logger.error(f"Cannot receive outputs {txid}: {transaction}")
        return []

    confirmations = transaction.get("confirmations") or 1
    related_transactions = [
        [
            detail.get("address"),
            detail.get('amount', 0),
            confirmations,
            detail.get("category", "change"),
        ]
        for detail in transaction.get("details", [])
    ]

    if not related_transactions:
        logger.warning(f"txid {txid} is not related to any known address for {g.symbol}")
        return []

    logger.warning(related_transactions)
    return related_transactions


@api.post('/dump')
def dump():
    return WalletService().get_dump()


@api.post('/fee-deposit-account')
def get_fee_deposit_account():
    return {'account': "", 'balance': 0}


@api.post('/get_all_addresses')
def get_all_addresses():
    return WalletService().get_all_accounts()
