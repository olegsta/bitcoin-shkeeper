from unittest.mock import MagicMock, patch

from app.services.transaction import TransactionLookupService


class TestGetTransactionKeepsReceiveOnly:
    @patch.object(TransactionLookupService, "get_txs_by_txid")
    def test_skips_external_send_outputs(self, get_txs):
        send_out = MagicMock(key_id=None, output_n=0, address="tb1qdest", value=99859)
        change_out = MagicMock(key_id=7, output_n=1, address="tb1qchange", value=1000)
        tx = MagicMock(confirmations=5, outputs=[send_out, change_out])
        get_txs.return_value = [tx]

        result = TransactionLookupService().get_transaction("ab" * 32)

        assert [d["address"] for d in result["details"]] == ["tb1qchange"]
        assert result["details"][0]["category"] == "receive"
        assert result["confirmations"] == 5

    @patch.object(TransactionLookupService, "get_txs_by_txid")
    def test_send_all_without_change_keeps_confirmations(self, get_txs):
        send_out = MagicMock(key_id=None, output_n=0, address="tb1qdest", value=99859)
        tx = MagicMock(confirmations=5, outputs=[send_out])
        get_txs.return_value = [tx]

        result = TransactionLookupService().get_transaction("cd" * 32)

        assert result["details"] == []
        assert result["confirmations"] == 5

    @patch("app.services.transaction.NodeService")
    @patch.object(TransactionLookupService, "get_txs_by_txid")
    def test_missing_wallet_tx_uses_node_confirmations(self, get_txs, node_cls):
        get_txs.return_value = []
        node_cls.return_value.get_confirmations.return_value = 5

        result = TransactionLookupService().get_transaction("ef" * 32)

        assert result["details"] == []
        assert result["confirmations"] == 5
        node_cls.return_value.get_confirmations.assert_called_once_with("ef" * 32)

    @patch("app.services.transaction.NodeService")
    @patch.object(TransactionLookupService, "get_txs_by_txid")
    def test_missing_wallet_tx_unknown_on_node(self, get_txs, node_cls):
        get_txs.return_value = []
        node_cls.return_value.get_confirmations.return_value = None

        assert TransactionLookupService().get_transaction("aa" * 32) is None
