#!/bin/bash
set -e

echo "Waiting for primary to be ready..."
until pg_isready -h postgres_primary -U twitter; do
  sleep 2
done

if [ ! -f "$PGDATA/PG_VERSION" ]; then
  rm -rf "$PGDATA"/*
  pg_basebackup -h postgres_primary -U replicator -D "$PGDATA" -Fp -Xs -P -R
  echo "hot_standby = on" >> "$PGDATA/postgresql.conf"
  chown -R postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"
fi
