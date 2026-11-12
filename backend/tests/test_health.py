from app.main import read_root, get_telegram_config

def test_root():
    res = read_root()
    assert res["status"] == "online"
    assert "service" in res

def test_telegram_config():
    res = get_telegram_config()
    assert hasattr(res, "enabled")
    assert hasattr(res, "configured")
