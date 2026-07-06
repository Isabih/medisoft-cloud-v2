#!/bin/bash

set -euo pipefail

# ---------------------------------
# CONFIG
# ---------------------------------
CLOUD_HOST="104.251.216.154"
CLOUD_USER="medisoft"
CLOUD_DIR="/home/medisoft/replication_dumps"
REPL_USER="replica"
MYSQL_CNF="/etc/mysql/mysql.conf.d/mysqld.cnf"

echo
echo "=================================================="
echo " MEDISOFT REPLICATION SETUP v2.1"
echo " Single Health Center Installer"
echo " File/Position Replication (Hardened)"
echo "=================================================="
echo

# ---------------------------------
# CHECK sshpass
# ---------------------------------
if ! command -v sshpass >/dev/null 2>&1; then
    echo "sshpass not found. Installing..."
    if command -v apt >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y sshpass
    else
        echo "Automatic sshpass installation only supports apt-based systems."
        exit 1
    fi
fi

# ---------------------------------
# CHECK / INSTALL TAILSCALE
# ---------------------------------
if ! command -v tailscale >/dev/null 2>&1; then
    echo
    echo "Tailscale not installed. Installing..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

TAILSCALE_IP="$(tailscale ip -4 2>/dev/null || true)"

if [[ -z "$TAILSCALE_IP" ]]; then
    echo
    echo "Tailscale is not connected."
    echo "Running: sudo tailscale up"
    echo

    sudo tailscale up || true

    echo
    echo "If browser login is required, complete it."
    echo "Waiting for Tailscale IP..."
    echo

    for i in {1..12}; do
        sleep 5
        TAILSCALE_IP="$(tailscale ip -4 2>/dev/null || true)"
        if [[ -n "$TAILSCALE_IP" ]]; then
            break
        fi
        echo "Still waiting for Tailscale connection... ($i/12)"
    done
fi

if [[ -z "$TAILSCALE_IP" ]]; then
    echo "ERROR: Could not determine Tailscale IP automatically."
    echo "Please finish Tailscale login, then run the script again."
    exit 1
fi

MASTER_IP="$TAILSCALE_IP"

echo
echo "Detected master IP: $MASTER_IP"

# ---------------------------------
# PASSWORDS
# ---------------------------------
echo
read -s -p "Enter MySQL Password: " MYSQL_PASS
echo
read -s -p "Enter SSH password: " SSH_PASS
echo

MYSQL_LOCAL=(mysql -u root "-p$MYSQL_PASS")
MYSQLDUMP_LOCAL=(mysqldump -u root "-p$MYSQL_PASS")

# ---------------------------------
# LIST DATABASES
# ---------------------------------
echo
echo "Fetching local databases..."
mapfile -t DBS < <("${MYSQL_LOCAL[@]}" -N -e "SHOW DATABASES;" | grep -vE '^(information_schema|performance_schema|mysql|sys)$')

if [[ ${#DBS[@]} -eq 0 ]]; then
    echo "No user databases found."
    exit 1
fi

echo
echo "Available databases:"
for i in "${!DBS[@]}"; do
    printf "%2d) %s\n" "$((i+1))" "${DBS[$i]}"
done

echo
read -p "Select database number: " DBNUM

if ! [[ "$DBNUM" =~ ^[0-9]+$ ]]; then
    echo "Invalid selection."
    exit 1
fi

INDEX=$((DBNUM-1))
if (( INDEX < 0 || INDEX >= ${#DBS[@]} )); then
    echo "Invalid selection."
    exit 1
fi

DBNAME="${DBS[$INDEX]}"

# ---------------------------------
# CHANNEL NAME
# ---------------------------------
CHANNEL="${DBNAME%%_*}"
if [[ -z "$CHANNEL" ]]; then
    CHANNEL="$DBNAME"
fi

# ---------------------------------
# GET FOSAID
# ---------------------------------
echo
echo "Reading FOSAID from ${DBNAME}.address ..."

FOSAID="$("${MYSQL_LOCAL[@]}" -N -e "SELECT fosaid FROM \`${DBNAME}\`.address WHERE fosaid IS NOT NULL LIMIT 1;" 2>/dev/null || true)"

if [[ -z "$FOSAID" ]]; then
    echo "ERROR: Could not read fosaid from \`${DBNAME}\`.address"
    echo "Make sure the selected database contains the address table and a non-null fosaid."
    exit 1
fi

if ! [[ "$FOSAID" =~ ^[0-9]+$ ]]; then
    echo "ERROR: FOSAID '$FOSAID' is not numeric."
    exit 1
fi

SERVER_ID="$FOSAID"

# ---------------------------------
# SUMMARY
# ---------------------------------
echo
echo "=========================================="
echo " REPLICATION CONFIGURATION SUMMARY ✅"
echo "=========================================="
echo "Database       : $DBNAME"
echo "Channel        : $CHANNEL"
echo "Master IP      : $MASTER_IP"
echo "Server ID      : $SERVER_ID   (from ${DBNAME}.address.fosaid)"
echo "Cloud server   : $CLOUD_HOST"
echo "Dump dir       : $CLOUD_DIR"
echo "Replica user   : $REPL_USER"
echo "Local my.cnf   : $MYSQL_CNF"
echo "Mode           : File/Position replication"
echo "=========================================="
echo
echo "⚠ NOTE:"
echo "This setup uses FILE/POSITION replication (not full GTID recovery)."
echo "If source binlogs are purged before replica catches up,"
echo "replication can break and require rebuild."
echo

read -p "Proceed and configure local MySQL automatically? (yes/no): " CONFIRM
if [[ ! "$CONFIRM" =~ ^(yes|y|Y)$ ]]; then
    echo "Cancelled."
    exit 0
fi

# ---------------------------------
# UPDATE LOCAL MYSQL CONFIG
# ---------------------------------
echo
echo "Backing up local MySQL config..."
sudo cp "$MYSQL_CNF" "${MYSQL_CNF}.bak.$(date +%F_%H%M%S)"

echo "Updating local MySQL config..."

sudo python3 - "$MYSQL_CNF" "$SERVER_ID" <<'PY'
import sys, re

path = sys.argv[1]
server_id = sys.argv[2]

required = {
    "bind-address": "0.0.0.0",
    "server-id": server_id,
    "log_bin": "mysql-bin",
    "binlog_format": "ROW",
    "gtid_mode": "ON",
    "enforce_gtid_consistency": "ON",
    "log_replica_updates": "ON",
    "skip_name_resolve": "1",
    "sync_binlog": "1",
    "innodb_flush_log_at_trx_commit": "1",
}

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

out = []
in_mysqld = False
seen = {k: False for k in required}
has_mysqld = False

for line in lines:
    stripped = line.strip()

    if re.match(r'^\[mysqld\]\s*$', stripped):
        has_mysqld = True
        in_mysqld = True
        out.append(line)
        continue

    if in_mysqld and re.match(r'^\[.*\]\s*$', stripped):
        for k, v in required.items():
            if not seen[k]:
                out.append(f"{k} = {v}\n")
                seen[k] = True
        in_mysqld = False
        out.append(line)
        continue

    if in_mysqld:
        replaced = False
        for k, v in required.items():
            if re.match(rf'^\s*{re.escape(k)}\s*=', line):
                out.append(f"{k} = {v}\n")
                seen[k] = True
                replaced = True
                break
        if replaced:
            continue

    out.append(line)

if not has_mysqld:
    out.append("\n[mysqld]\n")
    for k, v in required.items():
        out.append(f"{k} = {v}\n")
elif in_mysqld:
    for k, v in required.items():
        if not seen[k]:
            out.append(f"{k} = {v}\n")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(out)
PY

echo "Restarting local MySQL..."
sudo systemctl restart mysql

MYSQL_LOCAL=(mysql -u root "-p$MYSQL_PASS")
MYSQLDUMP_LOCAL=(mysqldump -u root "-p$MYSQL_PASS")

# ---------------------------------
# VERIFY LOCAL MYSQL CONFIG
# ---------------------------------
echo
echo "Verifying local MySQL settings..."

LOG_BIN="$("${MYSQL_LOCAL[@]}" -N -e "SHOW VARIABLES LIKE 'log_bin';" | awk '{print $2}')"
SERVER_ID_NOW="$("${MYSQL_LOCAL[@]}" -N -e "SHOW VARIABLES LIKE 'server_id';" | awk '{print $2}')"
BINLOG_FORMAT="$("${MYSQL_LOCAL[@]}" -N -e "SHOW VARIABLES LIKE 'binlog_format';" | awk '{print $2}')"
GTID_MODE="$("${MYSQL_LOCAL[@]}" -N -e "SHOW VARIABLES LIKE 'gtid_mode';" | awk '{print $2}')"

if [[ "$LOG_BIN" != "ON" ]]; then
    echo "ERROR: log_bin is not ON."
    exit 1
fi

if [[ "$SERVER_ID_NOW" != "$SERVER_ID" ]]; then
    echo "ERROR: server_id is '$SERVER_ID_NOW' but expected '$SERVER_ID'."
    exit 1
fi

if [[ "$BINLOG_FORMAT" != "ROW" ]]; then
    echo "ERROR: binlog_format must be ROW."
    exit 1
fi

if [[ "$GTID_MODE" != "ON" ]]; then
    echo "ERROR: gtid_mode must be ON."
    exit 1
fi

echo "log_bin       : $LOG_BIN"
echo "server_id     : $SERVER_ID_NOW"
echo "binlog_format : $BINLOG_FORMAT"
echo "gtid_mode     : $GTID_MODE"

# ---------------------------------
# BINLOG RETENTION SAFETY
# ---------------------------------
echo
echo "Checking binlog retention settings..."

RETENTION="$("${MYSQL_LOCAL[@]}" -N -e "SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';" | awk '{print $2}')"

if [[ -z "${RETENTION:-}" || "${RETENTION:-0}" -lt 1209600 ]]; then
    echo "⚠ Binlog retention is LOW (${RETENTION:-unknown} seconds)."
    echo "Setting safer retention (90 days)..."
    "${MYSQL_LOCAL[@]}" -e "SET PERSIST binlog_expire_logs_seconds = 7776000;" || true
    RETENTION="$("${MYSQL_LOCAL[@]}" -N -e "SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';" | awk '{print $2}')"
    echo "✔ Binlog retention updated to $RETENTION seconds."
else
    echo "✔ Binlog retention is safe ($RETENTION seconds)."
fi

echo
echo "Current binary logs on source (first 10):"
"${MYSQL_LOCAL[@]}" -e "SHOW BINARY LOGS;" | head -n 10 || true

# ---------------------------------
# CREATE / FIX REPLICATION USER ON LOCAL
# ---------------------------------
echo
echo "Adjusting password policy (if available)..."

"${MYSQL_LOCAL[@]}" -e "SET GLOBAL validate_password.policy=LOW;" 2>/dev/null || true
"${MYSQL_LOCAL[@]}" -e "SET GLOBAL validate_password.length=6;" 2>/dev/null || true

echo
echo "Ensuring replication user exists on local MySQL..."

"${MYSQL_LOCAL[@]}" <<SQL
CREATE USER IF NOT EXISTS '$REPL_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$MYSQL_PASS';
ALTER USER '$REPL_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$MYSQL_PASS';
GRANT REPLICATION SLAVE ON *.* TO '$REPL_USER'@'%';
FLUSH PRIVILEGES;
SQL

echo "Replication user verified. ✅"

echo
echo "Checking replication user plugin..."

"${MYSQL_LOCAL[@]}" -e "
SELECT user,host,plugin
FROM mysql.user
WHERE user='$REPL_USER';
"

# ---------------------------------
# ENSURE LOCAL GUI ADMIN ACCESS
# ---------------------------------
echo
echo "Ensuring local GUI/admin access..."

"${MYSQL_LOCAL[@]}" <<SQL
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '$MYSQL_PASS';
ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY '$MYSQL_PASS';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;

CREATE USER IF NOT EXISTS 'root'@'::1' IDENTIFIED BY '$MYSQL_PASS';
ALTER USER 'root'@'::1' IDENTIFIED BY '$MYSQL_PASS';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'::1' WITH GRANT OPTION;

FLUSH PRIVILEGES;
SQL

echo "Local GUI/admin access verified. ✅"

# ---------------------------------
# CREATE CLOUD DUMP DIR
# ---------------------------------
echo
echo "Preparing cloud dump directory..."
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" "mkdir -p '$CLOUD_DIR'"

# ---------------------------------
# CAPTURE MASTER STATUS
# ---------------------------------
echo
echo "Capturing master binlog position..."
MASTER_STATUS="$("${MYSQL_LOCAL[@]}" -e "SHOW MASTER STATUS\G")"

BINLOG_FILE="$(echo "$MASTER_STATUS" | awk '/File:/ {print $2}')"
BINLOG_POS="$(echo "$MASTER_STATUS" | awk '/Position:/ {print $2}')"

if [[ -z "$BINLOG_FILE" || -z "$BINLOG_POS" ]]; then
    echo "ERROR: Could not capture master binlog file/position."
    exit 1
fi

echo "Master log file: $BINLOG_FILE"
echo "Master log pos : $BINLOG_POS"

# ---------------------------------
# CREATE DUMP
# ---------------------------------
echo
echo "Creating database dump..."
DUMP_FILE="/tmp/${DBNAME}.sql"

"${MYSQLDUMP_LOCAL[@]}" \
  --single-transaction \
  --quick \
  --routines \
  --triggers \
  --events \
  --source-data=2 \
  --set-gtid-purged=OFF \
  --databases "$DBNAME" > "$DUMP_FILE"

if [[ ! -s "$DUMP_FILE" ]]; then
    echo "ERROR: Dump file was created but is empty."
    exit 1
fi

echo "Dump created: $DUMP_FILE"

# ---------------------------------
# UPLOAD DUMP
# ---------------------------------
echo
echo "Uploading dump to cloud..."
sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no "$DUMP_FILE" "$CLOUD_USER@$CLOUD_HOST:$CLOUD_DIR/"
echo "Upload complete. ✅"

# ---------------------------------
# CHECK CLOUD CHANNEL / DATABASE
# ---------------------------------
echo
echo "Checking cloud replication/database state..."

CHANNEL_EXISTS_RAW="$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" \
"mysql -u root -p'$MYSQL_PASS' -N -e \"SELECT COUNT(*) FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME='$CHANNEL';\" 2>/dev/null || echo 0")"
CHANNEL_EXISTS="$(echo "$CHANNEL_EXISTS_RAW" | tail -n1 | tr -d '[:space:]')"

DB_EXISTS_RAW="$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" \
"mysql -u root -p'$MYSQL_PASS' -N -e \"SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='$DBNAME';\" 2>/dev/null || echo 0")"
DB_EXISTS="$(echo "$DB_EXISTS_RAW" | tail -n1 | tr -d '[:space:]')"

if [[ "$CHANNEL_EXISTS" == "1" ]]; then
    echo
    echo "=========================================="
    echo " EXISTING CHANNEL DETECTED ON CLOUD"
    echo "=========================================="
    echo "Channel  : $CHANNEL"
    echo "Database : $DBNAME"
    echo "Database exists on cloud: $DB_EXISTS"
    echo
    echo "Current channel health/status:"
    echo "------------------------------------------"

    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" \
    "mysql -u root -p'$MYSQL_PASS' -e \"SHOW REPLICA STATUS FOR CHANNEL '$CHANNEL'\\G\" 2>/dev/null | \
    grep -E 'Channel_Name:|Source_Host:|Replica_IO_Running:|Replica_SQL_Running:|Seconds_Behind_Source:|Last_IO_Error:|Last_SQL_Error:|Auto_Position:' || true"

    echo "------------------------------------------"
    echo
    read -p "Channel exists. Continue by RESETTING channel and DROPPING database '$DBNAME'? (yes/no): " OVERWRITE_CONFIRM

    if [[ ! "$OVERWRITE_CONFIRM" =~ ^(yes|y|Y)$ ]]; then
        echo "Stopped by user. No changes made on cloud."
        rm -f "$DUMP_FILE"
        exit 0
    fi

    echo "You chose to continue."
else
    echo
    echo "Channel '$CHANNEL' does not exist on cloud."

    if [[ "$DB_EXISTS" == "1" ]]; then
        echo "Database '$DBNAME' already exists on cloud."
        read -p "Continue by DROPPING and recreating database '$DBNAME'? (yes/no): " DB_CONFIRM

        if [[ ! "$DB_CONFIRM" =~ ^(yes|y|Y)$ ]]; then
            echo "Stopped by user. No changes made on cloud."
            rm -f "$DUMP_FILE"
            exit 0
        fi
    else
        echo "Database '$DBNAME' does not exist on cloud. Setup will continue."
    fi
fi

# ---------------------------------
# PREPARE CLOUD SIDE
# ---------------------------------
echo
echo "Preparing cloud MySQL..."

if [[ "$CHANNEL_EXISTS" == "1" ]]; then
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" \
    "mysql -u root -p'$MYSQL_PASS' -e \"
    STOP REPLICA FOR CHANNEL '$CHANNEL';
    RESET REPLICA ALL FOR CHANNEL '$CHANNEL';
    DROP DATABASE IF EXISTS \\\`$DBNAME\\\`;
    CREATE DATABASE \\\`$DBNAME\\\`;
    \""
else
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" \
    "mysql -u root -p'$MYSQL_PASS' -e \"
    DROP DATABASE IF EXISTS \\\`$DBNAME\\\`;
    CREATE DATABASE \\\`$DBNAME\\\`;
    \""
fi

# ---------------------------------
# IMPORT DUMP ON CLOUD
# ---------------------------------
echo
echo "Importing dump on cloud..."
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" \
"mysql -u root -p'$MYSQL_PASS' < '$CLOUD_DIR/${DBNAME}.sql'"

# ---------------------------------
# CONFIGURE REPLICATION
# ---------------------------------
echo
echo "Configuring replication on cloud..."
sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" \
"mysql -u root -p'$MYSQL_PASS' -e \"
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='$MASTER_IP',
  SOURCE_USER='$REPL_USER',
  SOURCE_PASSWORD='$MYSQL_PASS',
  SOURCE_PORT=3306,
  SOURCE_LOG_FILE='$BINLOG_FILE',
  SOURCE_LOG_POS=$BINLOG_POS
FOR CHANNEL '$CHANNEL';

CHANGE REPLICATION FILTER
  REPLICATE_WILD_DO_TABLE = ('$DBNAME.%')
FOR CHANNEL '$CHANNEL';

START REPLICA FOR CHANNEL '$CHANNEL';
\""

# ---------------------------------
# VERIFY REPLICATION
# ---------------------------------
echo
echo "Checking replication status..."
STATUS="$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$CLOUD_USER@$CLOUD_HOST" \
"mysql -u root -p'$MYSQL_PASS' -e \"SHOW REPLICA STATUS FOR CHANNEL '$CHANNEL'\\G\"")"

echo "$STATUS"

IO="$(echo "$STATUS" | awk '/Replica_IO_Running:/ {print $2}')"
SQLRUN="$(echo "$STATUS" | awk '/Replica_SQL_Running:/ {print $2}')"
AUTO_POS="$(echo "$STATUS" | awk '/Auto_Position:/ {print $2}')"

if [[ "$IO" == "Yes" && "$SQLRUN" == "Yes" ]]; then
    echo
    echo "✔ Replication running correctly. ✅"
    echo "✔ IO thread  : $IO"
    echo "✔ SQL thread : $SQLRUN"
    echo "ℹ Auto pos   : ${AUTO_POS:-0} (expected 0 in v2 mode)"
else
    echo
    echo "⚠ Replication not healthy yet. Review the status above."
    echo "IO thread    : ${IO:-unknown}"
    echo "SQL thread   : ${SQLRUN:-unknown}"
    echo "Auto pos     : ${AUTO_POS:-unknown}"
fi

# ---------------------------------
# CLEANUP
# ---------------------------------0786371675
rm -f "$DUMP_FILE"

echo
echo "=================================================="
echo " REPLICATION SETUP COMPLETED: ✅ medisoft_cloud_v2.1 ✅"
echo " Database : $DBNAME"
echo " Channel  : $CHANNEL"
echo " ServerID : $SERVER_ID"
echo " Master   : $MASTER_IP"
echo " Binlog   : $BINLOG_FILE:$BINLOG_POS"
echo "=================================================="