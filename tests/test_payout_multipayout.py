from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.payout import PayoutService
from app.services.store import pick_change_key


class _Key:
    def __init__(self, key_id, address="", change=0, used=False):
        self.id = key_id
        self.address = address
        self.change = change
        self.used = used


def test_pick_change_key_prefers_unused_change():
    keys = [
        _Key(1, "bc1qrecv", change=0),
        _Key(2, "bc1qchg1", change=1, used=True),
        _Key(3, "bc1qchg2", change=1, used=False),
    ]
    assert pick_change_key(keys).id == 3


def test_pick_change_key_falls_back_to_receive():
    keys = [_Key(1, "bc1qrecv", change=0), _Key(2, "", change=0)]
    assert pick_change_key(keys).address == "bc1qrecv"


class TestMakeMultipayoutSingleTx:
    @patch("app.services.payout.decimal_value_to_satoshi", side_effect=lambda a: int(Decimal(str(a)) * 100_000_000))
    @patch("app.services.payout.store_service")
    def test_all_outputs_in_one_send(self, store_service, _to_sats):
        store_service.parse_store_id.side_effect = lambda v: int(v) if v is not None else 1
        key_a = MagicMock(id=10, change=0, address="bc1qa")
        key_change = MagicMock(id=11, change=1, address="bc1qc", used=False)
        store_service.store_address_keys.return_value = [key_a, key_change]
        store_service.pick_change_key.return_value = key_change

        tx = MagicMock()
        tx.__str__ = MagicMock(return_value="txid-shared")
        wallet_hd = MagicMock()
        wallet_hd.send.return_value = tx

        wallet = MagicMock()
        wallet.is_valid_address.return_value = True
        wallet.current_wallet.return_value = wallet_hd

        node = MagicMock()
        node.get_transaction_price.return_value = Decimal("0.00001")

        svc = PayoutService(wallet_service=wallet, node_service=node)
        results = svc.make_multipayout(
            [
                {"dest": "bc1qfee", "amount": "0.1"},
                {"dest": "bc1qcold", "amount": "0.9"},
            ],
            coin_fee=Decimal("1"),
            store_id=2,
        )

        wallet_hd.send.assert_called_once()
        wallet.current_wallet.assert_called_once_with(store_id=2)
        output_arr = wallet_hd.send.call_args.args[0]
        assert output_arr == [
            ("bc1qfee", 10_000_000),
            ("bc1qcold", 90_000_000),
        ]
        assert wallet_hd.send.call_args.kwargs["input_key_id"] == [10, 11]
        assert wallet_hd.send.call_args.kwargs["change_key_id"] == 11
        tx.send.assert_called_once()

        assert len(results) == 2
        assert results[0]["txids"] == ["txid-shared"]
        assert results[1]["txids"] == ["txid-shared"]
        assert results[0]["status"] == "success"
        assert results[1]["dest"] == "bc1qcold"
        node.get_transaction_price.assert_called_once()


class TestAssertSourcesBelongToStore:
    def _key(self, store_id):
        key = MagicMock()
        key.wallet = MagicMock(store_id=store_id)
        return key

    @patch("app.services.payout.db")
    @patch("app.services.payout.store_service")
    def test_accepts_matching_source_store(self, store_service, _db):
        store_service.parse_store_id.side_effect = lambda v: int(v) if v is not None else 1
        store_service.DEFAULT_STORE_ID = 1
        store_service._query_first.return_value = self._key(2)

        PayoutService().assert_sources_belong_to_store(
            [{"source": "bc1qsrc", "dest": "bc1qdst"}], 2
        )

    @patch("app.services.payout.db")
    @patch("app.services.payout.store_service")
    def test_rejects_source_from_another_store(self, store_service, _db):
        store_service.parse_store_id.side_effect = lambda v: int(v) if v is not None else 1
        store_service.DEFAULT_STORE_ID = 1
        store_service._query_first.return_value = self._key(1)

        try:
            PayoutService().assert_sources_belong_to_store(
                [{"source": "bc1qsrc", "dest": "bc1qdst"}], 2
            )
        except Exception as exc:
            assert str(exc) == "Source address 'bc1qsrc' does not belong to store_id=2"
        else:
            raise AssertionError("expected source store mismatch to raise")

    @patch("app.services.payout.db")
    @patch("app.services.payout.store_service")
    def test_skips_missing_source_and_unknown_key(self, store_service, _db):
        store_service.parse_store_id.side_effect = lambda v: int(v) if v is not None else 1
        store_service._query_first.return_value = None

        PayoutService().assert_sources_belong_to_store(
            [{"dest": "bc1qdst"}, {"source": "bc1qunknown"}], 2
        )
