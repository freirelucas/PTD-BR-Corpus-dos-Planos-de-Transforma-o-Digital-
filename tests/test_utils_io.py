"""Testes para utilitários de I/O e rede do cell 03_utils.

Cobre as funções até então sem teste: state_fingerprint (pura), safe_request
(rede, mockada), save_checkpoint/load_checkpoint (disco, via tmp_path).
"""
from unittest.mock import MagicMock, patch


# ---------------------- state_fingerprint ----------------------

def test_state_fingerprint_deterministic(cells):
    sf = cells["state_fingerprint"]
    a = sf([1, 2, {"x": 3}])
    b = sf([1, 2, {"x": 3}])
    assert a == b and isinstance(a, str) and len(a) == 12


def test_state_fingerprint_distinguishes(cells):
    sf = cells["state_fingerprint"]
    assert sf([1, 2, 3]) != sf([1, 2, 4])


# ---------------------- safe_request (rede mockada) ----------------------

def test_safe_request_returns_response_on_200(cells):
    resp = MagicMock()
    resp.status_code = 200
    with patch.object(cells["requests"], "get", return_value=resp) as g:
        out = cells["safe_request"]("http://exemplo", max_retries=1, delay=0)
    assert out is resp
    g.assert_called_once()


def test_safe_request_returns_none_on_persistent_error(cells):
    exc = cells["requests"].RequestException("boom")
    with patch.object(cells["requests"], "get", side_effect=exc):
        out = cells["safe_request"]("http://exemplo", max_retries=1, delay=0)
    assert out is None


# ---------------------- save_checkpoint / load_checkpoint ----------------------

def test_checkpoint_roundtrip(cells, tmp_path, monkeypatch):
    monkeypatch.setitem(cells["DIRS"], "checkpoints", str(tmp_path))
    cells["save_checkpoint"]({"a": 1, "b": [2, 3]}, "ckpt")
    assert cells["load_checkpoint"]("ckpt") == {"a": 1, "b": [2, 3]}


def test_checkpoint_missing_returns_none(cells, tmp_path, monkeypatch):
    monkeypatch.setitem(cells["DIRS"], "checkpoints", str(tmp_path))
    assert cells["load_checkpoint"]("inexistente") is None


def test_checkpoint_fingerprint_match(cells, tmp_path, monkeypatch):
    monkeypatch.setitem(cells["DIRS"], "checkpoints", str(tmp_path))
    cells["save_checkpoint"]([1, 2], "fp_ok", fingerprint="abc123")
    assert cells["load_checkpoint"]("fp_ok", "abc123") == [1, 2]


def test_checkpoint_fingerprint_mismatch_invalidates(cells, tmp_path, monkeypatch):
    monkeypatch.setitem(cells["DIRS"], "checkpoints", str(tmp_path))
    cells["save_checkpoint"]([1, 2], "fp_bad", fingerprint="abc123")
    # Fingerprint divergente → invalida e retorna None.
    assert cells["load_checkpoint"]("fp_bad", "outro") is None
    # E o checkpoint foi removido.
    assert cells["load_checkpoint"]("fp_bad") is None
