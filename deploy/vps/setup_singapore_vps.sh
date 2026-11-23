#!/usr/bin/env bash
# Repeatable setup script for the Alpha_mining Binance 1m Collector on a Debian/Ubuntu Singapore VPS.
# Usage:
#   chmod +x deploy/vps/setup_singapore_vps.sh
#   ./deploy/vps/setup_singapore_vps.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
VENV_DIR="${VENV_DIR:-${REPO_DIR}/.venv-collector}"
CONFIG_PATH="${CONFIG_PATH:-${REPO_DIR}/config/collector/binance_1m_collector.json}"

echo "[1/5] Checking Python 3.11+ and rclone..."
python3 --version
if ! command -v rclone >/dev/null 2>&1; then
  echo "WARNING: rclone is not installed yet. Install with: sudo apt-get update && sudo apt-get install -y rclone"
  echo "         Then configure remote 'gdrive' via: rclone config"
else
  rclone version | head -n 2
fi

echo "[2/5] Creating virtual environment at ${VENV_DIR}..."
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${REPO_DIR}/deploy/vps/requirements-collector.txt"

echo "[3/5] Validating collector configuration..."
"${VENV_DIR}/bin/python" "${REPO_DIR}/scripts/collect_binance_1m.py" \
  --config "${CONFIG_PATH}" \
  --base-dir "${REPO_DIR}" \
  validate-config

echo "[4/5] Running 1-tick live smoke test (Options + Spot + USD-M & COIN-M Delivery Futures)..."
"${VENV_DIR}/bin/python" "${REPO_DIR}/scripts/collect_binance_1m.py" \
  --config "${CONFIG_PATH}" \
  --base-dir "${REPO_DIR}" \
  once

echo "[5/5] Next steps to enable 24/7 systemd service:"
cat <<EOF
  1. Ensure rclone remote 'gdrive' works:
       rclone lsd gdrive:00_Katherine_Workspace/01_Alpha_Mining/datasets
  2. Copy and customize deploy/vps/binance-1m-collector.service (adjust User/Group/WorkingDirectory if needed):
       sudo cp "${REPO_DIR}/deploy/vps/binance-1m-collector.service" /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now binance-1m-collector.service
  3. Monitor logs and collector health:
       journalctl -u binance-1m-collector.service -f
       ${VENV_DIR}/bin/python ${REPO_DIR}/scripts/collect_binance_1m.py status
EOF
