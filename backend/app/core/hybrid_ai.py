import json
from typing import Any, List, Optional


def _norm_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _norm_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_yes(value: Any) -> bool:
    return _norm_str(value).lower() in {"yes", "on", "online", "ok", "healthy", "connected", "running", "true", "1"}


def _safe_get(obj: Any, field: str, default: Any = None) -> Any:
    return getattr(obj, field, default) if obj is not None else default


def _build_result(
    severity: str,
    diagnosis_code: str,
    title: str,
    summary: str,
    probable_cause: str,
    recommended_actions: List[str],
    confidence: float,
) -> dict:
    return {
        "severity": severity,
        "diagnosis_code": diagnosis_code,
        "title": title,
        "summary": summary,
        "probable_cause": probable_cause,
        "recommended_actions_json": json.dumps(recommended_actions),
        "confidence": confidence,
    }


def analyze_hybrid(source: Optional[Any], cloud: Optional[Any]) -> dict:
    """
    Hybrid diagnosis using:
    - local/source agent report
    - cloud replica report

    Returns exactly the keys expected by your router:
    severity, diagnosis_code, title, summary,
    probable_cause, recommended_actions_json, confidence
    """

    if not source and not cloud:
        return _build_result(
            severity="critical",
            diagnosis_code="NO_DATA",
            title="No monitoring data received",
            summary="Neither source agent report nor cloud replica report is available for this health center.",
            probable_cause="The local monitoring agent may be offline and the cloud replica checker has no recent record.",
            recommended_actions=[
                "Check whether the local monitoring agent is installed and running.",
                "Verify the cloud guardian/replica reporting service.",
                "Confirm this health center is correctly registered in the monitoring system.",
            ],
            confidence=0.98,
        )

    if source and not cloud:
        mysql_status = _norm_str(_safe_get(source, "mysql_status")).lower()
        internet_status = _norm_str(_safe_get(source, "internet_status")).lower()
        cloud_connection = _norm_str(_safe_get(source, "cloud_connection")).lower()

        if mysql_status != "online":
            return _build_result(
                severity="critical",
                diagnosis_code="SOURCE_MYSQL_DOWN",
                title="Local MySQL is offline",
                summary="The local source server reported that MySQL is not online, and no matching cloud report was found.",
                probable_cause="The local database service may be stopped, crashed, or unreachable.",
                recommended_actions=[
                    "Restart MySQL on the local server.",
                    "Check local server logs and service status.",
                    "Verify disk space and database availability.",
                ],
                confidence=0.95,
            )

        if internet_status != "online":
            return _build_result(
                severity="critical",
                diagnosis_code="SOURCE_INTERNET_DOWN",
                title="Local server internet is offline",
                summary="The source agent reported internet connectivity failure, and cloud replica status is missing.",
                probable_cause="The health center server may have lost internet access or VPN connectivity.",
                recommended_actions=[
                    "Check ISP/router connection on the health center server.",
                    "Verify Tailscale/VPN connectivity.",
                    "Test outbound connectivity from the local server.",
                ],
                confidence=0.94,
            )

        if cloud_connection != "online":
            return _build_result(
                severity="warning",
                diagnosis_code="SOURCE_CLOUD_DISCONNECTED",
                title="Cloud connection problem",
                summary="The local source server is running, but cloud connection status is not healthy and cloud replica status is unavailable.",
                probable_cause="The local agent can run locally, but cannot reach the cloud backend or replication endpoint properly.",
                recommended_actions=[
                    "Check backend/API reachability from the local server.",
                    "Verify firewall, DNS, and VPN/Tailscale routing.",
                    "Inspect cloud-side service availability.",
                ],
                confidence=0.88,
            )

        return _build_result(
            severity="warning",
            diagnosis_code="CLOUD_REPORT_MISSING",
            title="Cloud replica report missing",
            summary="The source server appears healthy, but there is no corresponding cloud replica report yet.",
            probable_cause="The cloud monitoring/replica checker may not have reported recently, or the channel mapping may be incorrect.",
            recommended_actions=[
                "Check the cloud guardian service.",
                "Verify channel name and foss_id mapping on cloud.",
                "Confirm the cloud server is collecting replica status.",
            ],
            confidence=0.80,
        )

    if cloud and not source:
        io_running = _is_yes(_safe_get(cloud, "io_running"))
        sql_running = _is_yes(_safe_get(cloud, "sql_running"))
        last_io_error = _norm_str(_safe_get(cloud, "last_io_error"))
        last_sql_error = _norm_str(_safe_get(cloud, "last_sql_error"))

        if not io_running and "Authentication requires secure connection" in last_io_error:
            return _build_result(
                severity="critical",
                diagnosis_code="REPLICA_AUTH_PLUGIN",
                title="Replica authentication/plugin issue",
                summary="The cloud replica cannot authenticate to the source because secure connection or plugin requirements are not satisfied.",
                probable_cause="Replication user/plugin mismatch, often caching_sha2_password vs mysql_native_password, or SSL requirement mismatch.",
                recommended_actions=[
                    "Check the source replication user authentication plugin.",
                    "Switch to mysql_native_password if appropriate.",
                    "Verify replica connection settings and credentials.",
                ],
                confidence=0.97,
            )

        if not io_running:
            return _build_result(
                severity="critical",
                diagnosis_code="REPLICA_IO_DOWN",
                title="Replica IO thread is down",
                summary="The cloud replica report shows the IO thread is not running, so events are not being fetched from the source.",
                probable_cause="Source host unreachable, wrong credentials, VPN/Tailscale problem, or source MySQL not listening.",
                recommended_actions=[
                    "Check source host connectivity from the cloud server.",
                    "Verify replication credentials.",
                    "Confirm MySQL is reachable on the source server.",
                ],
                confidence=0.95,
            )

        if not sql_running:
            return _build_result(
                severity="critical",
                diagnosis_code="REPLICA_SQL_DOWN",
                title="Replica SQL thread is down",
                summary="The cloud replica report shows the SQL thread is stopped, so relay events are not being applied.",
                probable_cause="Replication apply error such as unknown database, duplicate entry, or missing object.",
                recommended_actions=[
                    "Inspect last_sql_error in the cloud replica report.",
                    "Check worker errors in replication_applier_status_by_worker.",
                    "Repair the channel or recreate the replica if needed.",
                ],
                confidence=0.96,
            )

        return _build_result(
            severity="warning",
            diagnosis_code="SOURCE_REPORT_MISSING",
            title="Source report missing",
            summary="Cloud replication appears available, but there is no recent local/source agent report.",
            probable_cause="The local agent may be offline or unable to send status to the backend.",
            recommended_actions=[
                "Check the local monitoring agent service.",
                "Verify backend reachability from the local server.",
                "Confirm the source server is powered on and reporting.",
            ],
            confidence=0.78,
        )

    # both source and cloud exist
    mysql_status = _norm_str(_safe_get(source, "mysql_status")).lower()
    internet_status = _norm_str(_safe_get(source, "internet_status")).lower()
    cloud_connection = _norm_str(_safe_get(source, "cloud_connection")).lower()

    cpu_usage = _norm_float(_safe_get(source, "cpu_usage"), 0)
    ram_usage = _norm_float(_safe_get(source, "ram_usage"), 0)
    disk_usage = _norm_float(_safe_get(source, "disk_usage"), 0)

    source_config_ok = bool(_safe_get(source, "source_config_ok", False))
    connected_replicas = int(_safe_get(source, "connected_replicas", 0) or 0)

    io_running = _is_yes(_safe_get(cloud, "io_running"))
    sql_running = _is_yes(_safe_get(cloud, "sql_running"))
    seconds_behind = _norm_float(_safe_get(cloud, "seconds_behind"), 0)
    last_io_error = _norm_str(_safe_get(cloud, "last_io_error"))
    last_sql_error = _norm_str(_safe_get(cloud, "last_sql_error"))

    # 1. Source server itself unhealthy
    if mysql_status != "online":
        return _build_result(
            severity="critical",
            diagnosis_code="SOURCE_MYSQL_DOWN",
            title="Source MySQL is offline",
            summary="The source server reports MySQL is not online, so replication cannot work normally.",
            probable_cause="Local MySQL service stopped, crashed, or became inaccessible.",
            recommended_actions=[
                "Restart MySQL on the source server.",
                "Check MySQL error logs.",
                "Verify local database integrity and service status.",
            ],
            confidence=0.98,
        )

    if internet_status != "online":
        return _build_result(
            severity="critical",
            diagnosis_code="SOURCE_INTERNET_DOWN",
            title="Source internet connectivity failure",
            summary="The source server has no healthy internet connectivity, which can break cloud communication and replication reachability.",
            probable_cause="ISP/router outage, VPN/Tailscale interruption, or network misconfiguration.",
            recommended_actions=[
                "Check network uplink and router.",
                "Verify Tailscale/VPN connectivity.",
                "Test outbound internet from the source server.",
            ],
            confidence=0.96,
        )

    if cloud_connection != "online":
        return _build_result(
            severity="warning",
            diagnosis_code="SOURCE_CLOUD_LINK_WARN",
            title="Source cloud connection warning",
            summary="The local source agent can run, but cloud connection is not fully healthy.",
            probable_cause="Intermittent network path issue between local source and cloud services.",
            recommended_actions=[
                "Test API/backend reachability from the source server.",
                "Inspect firewall and VPN routes.",
                "Monitor whether the issue is intermittent or constant.",
            ],
            confidence=0.84,
        )

    # 2. Local resource pressure
    if disk_usage >= 95:
        return _build_result(
            severity="critical",
            diagnosis_code="SOURCE_DISK_CRITICAL",
            title="Source disk usage is critical",
            summary=f"The source server disk usage is critically high at {disk_usage:.1f}%.",
            probable_cause="Insufficient free disk space may affect MySQL and replication stability.",
            recommended_actions=[
                "Free disk space immediately.",
                "Rotate or clean old logs and dumps.",
                "Check backup files and temporary files on the source server.",
            ],
            confidence=0.94,
        )

    if cpu_usage >= 90 or ram_usage >= 90:
        return _build_result(
            severity="warning",
            diagnosis_code="SOURCE_RESOURCE_PRESSURE",
            title="Source server resource pressure",
            summary=f"The source server shows high resource usage (CPU {cpu_usage:.1f}%, RAM {ram_usage:.1f}%).",
            probable_cause="High load on the local server may delay replication and monitoring responsiveness.",
            recommended_actions=[
                "Inspect top resource-consuming processes.",
                "Check MySQL workload and local services.",
                "Monitor whether usage remains high over time.",
            ],
            confidence=0.82,
        )

    # 3. Replication config/source-side configuration
    if not source_config_ok:
        return _build_result(
            severity="critical",
            diagnosis_code="SOURCE_CONFIG_INVALID",
            title="Source replication configuration is invalid",
            summary="The source agent indicates replication/source configuration is not correct.",
            probable_cause="MySQL source settings, binlog, GTID, or server-id may be missing or misconfigured.",
            recommended_actions=[
                "Check server-id, log_bin, GTID mode, and binlog_format on source.",
                "Verify replication user exists and has correct privileges.",
                "Re-run replication setup script if needed.",
            ],
            confidence=0.95,
        )

    # 4. Cloud replica thread failures
    if not io_running and "Authentication requires secure connection" in last_io_error:
        return _build_result(
            severity="critical",
            diagnosis_code="REPLICA_AUTH_PLUGIN",
            title="Replica authentication/plugin issue",
            summary="The replica IO thread is stopped because secure connection or plugin requirements are not satisfied.",
            probable_cause="Authentication plugin mismatch or SSL requirement mismatch between source and replica.",
            recommended_actions=[
                "Check replication user plugin on source.",
                "Use mysql_native_password if that fits your environment.",
                "Verify replica connection parameters and credentials.",
            ],
            confidence=0.99,
        )

    if not io_running:
        return _build_result(
            severity="critical",
            diagnosis_code="REPLICA_IO_DOWN",
            title="Replica IO thread is down",
            summary="The cloud replica IO thread is not running, so changes are not being fetched from source.",
            probable_cause="Network path failure, wrong credentials, source unreachable, or source MySQL not listening.",
            recommended_actions=[
                "Check source host connectivity from cloud.",
                "Verify source MySQL is reachable on port 3306.",
                "Confirm replication credentials and source host value.",
            ],
            confidence=0.96,
        )

    if not sql_running:
        if "Unknown database" in last_sql_error:
            return _build_result(
                severity="critical",
                diagnosis_code="REPLICA_UNKNOWN_DATABASE",
                title="Replica SQL stopped بسبب unknown database",
                summary="The replica SQL thread stopped because an expected database does not exist on the replica side.",
                probable_cause="Database naming mismatch, missing placeholder DB, or incorrect channel/database mapping.",
                recommended_actions=[
                    "Check the exact database name in the SQL error.",
                    "Create the expected database if it is safe and correct.",
                    "Verify source DB naming versus cloud channel mapping.",
                ],
                confidence=0.98,
            )

        if "Can't drop database" in last_sql_error and "doesn't exist" in last_sql_error:
            return _build_result(
                severity="warning",
                diagnosis_code="REPLICA_DROP_DB_MISSING",
                title="Replica SQL stopped on missing DROP DATABASE target",
                summary="The replica attempted to drop a database that does not exist locally.",
                probable_cause="A safe skip may be enough because the intended final state already exists.",
                recommended_actions=[
                    "Confirm the missing database is truly expected to be absent.",
                    "Skip the failing event if safe.",
                    "Recheck SQL thread after repair.",
                ],
                confidence=0.90,
            )

        return _build_result(
            severity="critical",
            diagnosis_code="REPLICA_SQL_DOWN",
            title="Replica SQL thread is down",
            summary="The cloud replica SQL thread is stopped due to an apply error.",
            probable_cause="Replication applier failure such as duplicate entry, missing object, or invalid schema state.",
            recommended_actions=[
                "Inspect last_sql_error and worker errors.",
                "Repair or recreate the replica channel if necessary.",
                "Validate source and cloud schema consistency.",
            ],
            confidence=0.95,
        )

    # 5. Lag / partial health
    if seconds_behind >= 3600:
        return _build_result(
            severity="critical",
            diagnosis_code="REPLICA_LAG_CRITICAL",
            title="Replication lag is critical",
            summary=f"Replication lag is very high at {seconds_behind:.0f} seconds.",
            probable_cause="Slow apply rate, heavy source load, or prior recovery delay.",
            recommended_actions=[
                "Check cloud replica performance.",
                "Review source workload and relay log apply speed.",
                "Investigate whether lag is growing or shrinking.",
            ],
            confidence=0.91,
        )

    if seconds_behind >= 300:
        return _build_result(
            severity="warning",
            diagnosis_code="REPLICA_LAG_WARNING",
            title="Replication lag is elevated",
            summary=f"Replication lag is elevated at {seconds_behind:.0f} seconds.",
            probable_cause="The replica is healthy but is not fully caught up.",
            recommended_actions=[
                "Monitor lag trend over time.",
                "Check source load and cloud replica resource usage.",
                "Verify no intermittent SQL/IO interruptions are occurring.",
            ],
            confidence=0.83,
        )

    # 6. Source sees no connected replicas
    if connected_replicas <= 0:
        return _build_result(
            severity="warning",
            diagnosis_code="SOURCE_NO_CONNECTED_REPLICA",
            title="Source sees no connected replica",
            summary="The source report indicates no connected replicas, even though cloud report exists.",
            probable_cause="Replica connection may be intermittent, recently restarted, or not visible at source at report time.",
            recommended_actions=[
                "Check source SHOW REPLICAS / processlist at the same time as cloud report.",
                "Compare source and cloud report timestamps.",
                "Monitor whether the condition persists.",
            ],
            confidence=0.70,
        )

    # 7. Healthy
    return _build_result(
        severity="info",
        diagnosis_code="HEALTHY",
        title="Source and cloud replication are healthy",
        summary="Source server, cloud replica, and core monitoring signals appear healthy.",
        probable_cause="No active fault detected.",
        recommended_actions=[
            "Continue routine monitoring.",
            "Keep backups and guardian checks active.",
            "Review trends periodically for lag and resource growth.",
        ],
        confidence=0.99,
    )