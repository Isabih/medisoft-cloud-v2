from datetime import datetime
from app.services.io_diagnostics_v4 import diagnose


def replica(io="Connecting", errno=0, message=""):
    return {"io_running": io, "last_io_error": message,
            "source_host": "100.1.2.3", "raw": {"Last_IO_Errno": errno, "Source_Port": 3306}}


def test_authentication_error_is_confirmed():
    d = diagnose(replica(errno=1045))
    assert d["cause_code"] == "authentication_rejected"
    assert d["confidence"] == "confirmed"


def test_missing_replica_status_is_not_off():
    d = diagnose({"io_running": "Unknown", "last_io_error": "access denied", "raw": {}})
    assert d["io_state"] == "unknown"
    assert d["confidence"] == "unknown"


def test_connecting_with_reachable_source_remains_unconfirmed():
    d = diagnose(replica(), probe={"status": "reachable"})
    assert d["cause_code"] == "connecting_unconfirmed"
    assert d["confidence"] == "unknown"


def test_cloud_tcp_failure_is_confirmed_not_vpn_root_cause():
    d = diagnose(replica(), probe={"status": "unreachable"})
    assert d["cause_code"] == "source_tcp_unreachable"
    assert d["confidence"] == "confirmed"


def test_stale_agent_report_does_not_claim_internet_failure():
    d = diagnose(replica(), {"created_at": datetime(2020, 1, 1), "internet_status": "offline"})
    assert d["checks"]["internet"] == "unknown"
    assert d["cause_code"] == "connecting_unconfirmed"


def test_io_online_is_not_full_replication_recovery():
    d = diagnose(replica(io="Yes"))
    assert d["cause_code"] == "io_running"
    assert "SQL" in d["suggested_solution"]
