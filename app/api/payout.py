import decimal

from flask import g, request
from sqlalchemy.exc import PendingRollbackError

from app.celery_app import celery
from app.config import COIN, config
from app.db_import import db
from app.lib.values import decimal_value_to_satoshi, sat_per_kb_to_sat_per_vbyte
from app.logging import logger
from app.services import NodeService

from ..tasks import make_multipayout, withdraw_to_external_wallet_task
from . import api


def _ensure_payouts_enabled():
    if config['PAYOUTS_DISABLED'] == 1:
        logger.warning("Payout was disabled")
        raise Exception("Payout was disabled")


def _load_payout_list():
    try:
        payout_list = request.get_json(force=True)
    except Exception as e:
        raise Exception(f"Bad JSON in payout list: {e}")

    if not payout_list:
        raise Exception(f"Payout list is empty!")
    return payout_list


def _require_known_coin():
    if g.symbol != COIN:
        raise Exception(f"{g.symbol} is not defined in config, cannot make payout")


def _enqueue_multipayout(payout_list, fee):
    _require_known_coin()
    task = make_multipayout.s(g.symbol, payout_list, fee).apply_async()
    return {'task_id': task.id}


@api.post('/calc-tx-fee/<decimal:amount>')
def calc_tx_fee(amount):
    if g.symbol == COIN:
        fee = decimal_value_to_satoshi(NodeService().get_transaction_price())
        return {'accounts_num': 1, 'fee': float(fee), 'fee_satoshi': sat_per_kb_to_sat_per_vbyte(fee)}
    return {'status': 'error', 'msg': 'unknown crypto'}


@api.post('/multipayout')
def multipayout():
    _ensure_payouts_enabled()
    payout_list = _load_payout_list()

    for transfer in payout_list:
        try:
            transfer['amount'] = decimal.Decimal(transfer['amount'])
        except Exception as e:
            raise Exception(f"Bad amount in {transfer}: {e}")

        if transfer['amount'] <= 0:
            raise Exception(f"Payout amount should be a positive number: {transfer}")

    return _enqueue_multipayout(payout_list, decimal.Decimal(config['NETWORK_FEE']))


@api.post('/withdraw_to_external_wallet')
def withdraw_to_external_wallet():
    payout_list = _load_payout_list()
    _require_known_coin()
    task = withdraw_to_external_wallet_task.s(g.symbol, payout_list).apply_async()
    return {'task_id': task.id}


@api.post('/payout/<to>/<decimal:amount>/<fee>')
def payout(to, amount, fee):
    logger.warning(f'starting payout {amount}, to {to}')
    _ensure_payouts_enabled()
    payout_list = [{"dest": to, "amount": amount}]
    fee_value = decimal.Decimal(fee) if fee else decimal.Decimal(config['NETWORK_FEE'])
    return _enqueue_multipayout(payout_list, fee_value)


@api.post('/task/<id>')
def get_task(id):
    task = celery.AsyncResult(id)
    try:
        result = task.result
    except PendingRollbackError:
        db.session.rollback()
        result = task.result

    logger.warning(f"response task {task} result {result}")
    if isinstance(result, list):
        for r in result:
            if r.get("status") == "error":
                return {
                    "status": "FAILURE",
                    "result": r.get("error"),
                }
    if isinstance(result, Exception):
        return {"status": "FAILURE", "result": str(result)}
    return {'status': task.status, 'result': result}
