import random
import time
import uuid

import sqlalchemy

from app.lib.values import Value
from app.lib.wallets import Wallet, WalletKey
from app.unlock_acc import get_account_password
from app.utils import BTCUtils, DOGEUtils, LTCUtils

from ..config import COIN, config
from ..logging import logger
from ..models import DbWallet, db

_WALLET_GENERATE_RETRIES = 3
_DB_QUERY_RETRIES = 3

_WALLET_NAME_ADJECTIVES = [
    "brave", "lucky", "silent", "quick", "happy",
    "clever", "bold", "wise", "calm", "fierce",
]
_WALLET_NAME_ANIMALS = [
    "fox", "tiger", "eagle", "wolf", "panther",
    "lion", "hawk", "bear", "cobra", "rhino",
]

_ADDRESS_VALIDATORS = {
    "BTC": BTCUtils.is_valid_btc_address,
    "LTC": LTCUtils.is_valid_ltc_address,
    "DOGE": DOGEUtils.is_valid_doge_address,
}


class WalletService:
    def current_wallet(self):
        return Wallet(self.wallet_name())

    def wallet(self):
        if not get_account_password():
            return
        return Wallet(self.wallet_name())

    def db_wallet(self):
        return db.session.query(DbWallet).first()

    def wallet_name(self):
        if not get_account_password():
            return
        dbw = self.db_wallet()
        if dbw is None:
            dbw = self._ensure_db_wallet()
        return dbw.name

    def witness_type(self):
        return 'legacy' if COIN == "DOGE" else 'segwit'

    def generate_wallet_name(self):
        adj = random.choice(_WALLET_NAME_ADJECTIVES)
        animal = random.choice(_WALLET_NAME_ANIMALS)
        unique = uuid.uuid4().hex[:6]
        return f"{adj}-{animal}-{unique}"

    def get_fee_deposit_account(self):
        wallet = self.current_wallet()
        if not wallet:
            wallet = self._create_wallet()

        current_index_path = wallet.current_index_path()
        keys = wallet.keys_for_path(path=f"m/84'/{current_index_path}'/0'/0/0")
        return keys[0].address

    def get_deposit_account_balance(self):
        amount = self.wallet().balance()
        return Value.from_satoshi(amount).value

    def get_dump(self):
        logger.warning('Start dumping wallets')
        return {
            key.address: {
                'public_address': key.address,
                'private': key.private.hex(),
                'wif': key.wif.decode('utf-8'),
                'public': key.public.hex(),
            }
            for key in self.current_wallet().keys()
        }

    def get_all_addresses(self):
        wallet_list = self._query_all_wallets()
        return [wallet.pub_address for wallet in wallet_list]

    def get_all_accounts(self):
        wallet = self.current_wallet()
        current_index_path = wallet.current_index_path()
        segwit_prefix = f"m/84'/{current_index_path}'/0'/0/"
        return [
            key.address for key in wallet.keys()
            if key.path.startswith(segwit_prefix) or key.path.startswith("m/0'/0'/")
        ]

    def generate_address(self):
        logger.warning("generate_address started for coin=%s network=%s", COIN, config['COIN_NETWORK'])
        wallet, address_index = self._prepare_wallet_for_new_address()
        if COIN == "DOGE":
            return self._generate_doge_address()
        return self._generate_hd_address(wallet, address_index)

    def is_valid_address(self, address: str) -> bool:
        validator = _ADDRESS_VALIDATORS.get(COIN)
        if validator is None:
            raise ValueError(f"Unknown coin type: {COIN}")
        return validator(address)

    def _create_wallet(self, wallet_name=None):
        return Wallet.create(
            wallet_name or self.generate_wallet_name(),
            network=config['COIN_NETWORK'],
            witness_type=self.witness_type(),
            scheme="single" if COIN == "DOGE" else "bip32",
            encoding="base58" if COIN == "DOGE" else "bech32",
        )

    def _ensure_db_wallet(self):
        for attempt in range(1, _WALLET_GENERATE_RETRIES + 1):
            try:
                self.generate_address()
                db.session.commit()
                return self.db_wallet()
            except sqlalchemy.exc.SQLAlchemyError as e:
                db.session.rollback()
                wait_time = 2 * attempt
                print(f"SQLAlchemy error detected: {e}. Retrying in {wait_time}s (attempt {attempt})")
                time.sleep(wait_time)
        raise RuntimeError(
            f"Could not generate wallet after {_WALLET_GENERATE_RETRIES} attempts due to repeated errors"
        )

    def _query_all_wallets(self):
        for i in range(_DB_QUERY_RETRIES):
            try:
                return Wallet.query.all()
            except:
                db.session.rollback()
                if i >= _DB_QUERY_RETRIES - 1:
                    raise Exception("There was exception during query to the database, try again later")

    def _prepare_wallet_for_new_address(self):
        if db.session.query(DbWallet).count() == 0:
            wallet = self._create_wallet()
            logger.warning("Wallet created for %s", COIN)
            return wallet, 1

        wallet = self.current_wallet()
        db_wallet = self.db_wallet()
        address_index = db_wallet.generated_address_count + 1
        db_wallet.generated_address_count = address_index
        db.session.commit()
        logger.warning(
            "generate_address %s: wallet=%s purpose=%s migrated=%s index=%s",
            COIN,
            db_wallet.name,
            wallet.purpose,
            db_wallet.migrated,
            address_index,
        )
        return wallet, address_index

    def _generate_doge_address(self):
        from app.lib.keys import HDKey

        new_key = HDKey(network=config['COIN_NETWORK'], witness_type='legacy')
        db_wallet = self.db_wallet()
        wallet_key = WalletKey.from_key(
            name=f"{db_wallet.name}_{db_wallet.generated_address_count}",
            wallet_id=db_wallet.id,
            session=db.session,
            key=new_key,
        )
        db.session.commit()
        return wallet_key.address

    def _generate_hd_address(self, wallet, address_index):
        if wallet.purpose == 0:
            path = f"m/0'/0/{address_index}"
            path_old = f"m/0'/1/{address_index}"
            keys = self._keys_for_path(wallet, path)
            self._keys_for_path(wallet, path_old)
        else:
            current_index_path = wallet.current_index_path()
            path = f"m/84'/{current_index_path}'/0'/0/{address_index}"
            change_path = f"m/84'/{current_index_path}'/0'/1/{address_index}"
            self._keys_for_path(wallet, change_path)
            keys = self._keys_for_path(wallet, path)

        keys_count = len(keys) if keys else 0
        logger.warning("generate_address %s: path=%s keys_count=%s", COIN, path, keys_count)
        if not keys:
            logger.warning(f"No keys returned for path {path}")
            return None

        address = keys[0].address
        logger.warning("generate_address finished for coin=%s address=%s", COIN, address)
        return address

    def _keys_for_path(self, wallet, path):
        return wallet.keys_for_path(
            path=path,
            witness_type=self.witness_type(),
            account_id=0,
            network=config['COIN_NETWORK'],
        )
