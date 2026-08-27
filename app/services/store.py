from sqlalchemy.exc import PendingRollbackError

from ..logging import logger
from ..models import DbKey, DbWallet, db

DEFAULT_STORE_ID = 1


def parse_store_id(value, required=False):
    if value is None:
        if required:
            raise ValueError("store_id is required")
        return DEFAULT_STORE_ID
    if isinstance(value, bool):
        raise ValueError(f"Invalid store_id {value!r}")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"Invalid store_id {value!r}")
        return value
    raw = str(value).strip()
    if not raw:
        if required:
            raise ValueError("store_id is required")
        return DEFAULT_STORE_ID
    if raw.lower() == "default":
        return DEFAULT_STORE_ID
    try:
        store_id = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid store_id {value!r}") from exc
    if store_id <= 0:
        raise ValueError(f"Invalid store_id {value!r}")
    return store_id


def _query_first(query):
    """Recover a Flask-SQLAlchemy Session left in a failed transaction."""
    try:
        return query.first()
    except PendingRollbackError:
        logger.warning("Invalid DB transaction; rolling back and retrying query")
        db.session.rollback()
        return query.first()


def _query_all(query):
    try:
        return query.all()
    except PendingRollbackError:
        logger.warning("Invalid DB transaction; rolling back and retrying query")
        db.session.rollback()
        return query.all()


def store_wallet(store_id=None):
    store_id = parse_store_id(store_id)
    return _query_first(
        DbWallet.query.filter_by(store_id=store_id)
        .filter(DbWallet.parent_id.is_(None))
        .order_by(DbWallet.id.asc())
    )


def store_address_keys(store_id=None):
    """Keys that have a spendable address (exclude HD intermediates)."""
    store_id = parse_store_id(store_id)
    return _query_all(
        DbKey.query.join(DbWallet, DbKey.wallet_id == DbWallet.id)
        .filter(
            DbWallet.store_id == store_id,
            DbKey.address.isnot(None),
            DbKey.address != "",
        )
        .order_by(DbKey.id.asc())
    )


def pick_change_key(keys):
    """Prefer unused change-chain address; fall back to any address key."""
    address_keys = [key for key in keys if key.address]
    if not address_keys:
        return keys[0] if keys else None
    change_keys = [key for key in address_keys if key.change == 1]
    unused_change = next((key for key in change_keys if not key.used), None)
    if unused_change:
        return unused_change
    if change_keys:
        return change_keys[0]
    return address_keys[0]
