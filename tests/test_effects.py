import pytest
from spek.effects.python import EffectChecker


def test_detects_network_call():
    code = """
def fetch(id):
    return requests.get(f"http://x/{id}")
"""
    effects = EffectChecker().check(code, "fetch")
    assert "net" in effects


def test_detects_db_call():
    code = """
def get_user(id):
    return db.execute("select * from users where id=?", id)
"""
    effects = EffectChecker().check(code, "get_user")
    assert "db" in effects
