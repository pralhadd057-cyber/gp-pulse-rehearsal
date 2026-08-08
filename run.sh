#!/bin/sh
# One-command local run: seed synthetic data, then start the API + dashboard.
# Usage: ./run.sh [n_gps]
set -e
N_GPS="${1:-16}"

echo "Installing dependencies (pandas, numpy)..."
pip install -q -r requirements.txt

echo "Seeding $N_GPS synthetic GPs..."
python3 -m gp_pulse seed --n-gps "$N_GPS" --time

echo "Starting server..."
python3 -m gp_pulse serve
