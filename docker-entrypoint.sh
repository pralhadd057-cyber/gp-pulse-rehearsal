#!/bin/sh
set -e

N_GPS="${GP_PULSE_SEED_N_GPS:-16}"

if [ -n "$GP_PULSE_SEED_CSV" ]; then
    echo "Seeding from CSV: $GP_PULSE_SEED_CSV"
    python3 -m gp_pulse seed --csv "$GP_PULSE_SEED_CSV"
else
    echo "Seeding with $N_GPS synthetic GPs"
    python3 -m gp_pulse seed --n-gps "$N_GPS"
fi

exec python3 -m gp_pulse serve
