FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gp_pulse ./gp_pulse
COPY frontend ./frontend

ENV GP_PULSE_API_HOST=0.0.0.0
ENV GP_PULSE_API_PORT=8000
ENV GP_PULSE_DB_PATH=/data/gp_pulse.sqlite3

VOLUME ["/data"]
EXPOSE 8000

# Seed with synthetic data on first run, then serve. Override
# GP_PULSE_SEED_N_GPS or mount a CSV and set GP_PULSE_SEED_CSV to use
# real data instead.
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
