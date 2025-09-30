#!/bin/bash
cmd=$1

usage() {
    echo "run.sh <command> <arguments>"
    echo "Available commands:"
    echo " register_connector          register a new Kafka connector"
    echo " ensure_schema               ensure Postgres schema/table exist (create if missing)"
    echo " register_and_init           register connector then ensure schema/table"
    echo "Available arguments:"
    echo " [connector config path]     path to connector config, for command register_connector only"
}

if [[ -z "$cmd" ]]; then
    echo "Missing command"
    usage
    exit 1
fi

case $cmd in
    register_connector)
        if [[ -z "$2" ]]; then
            echo "Missing connector config path"
            usage
            exit 1
        else
            echo "Registering a new connector from $2"
            # Assign a connector config path such as: kafka_connect_jdbc/configs/connect-timescaledb-sink.json
            curl -i -X POST -H "Accept:application/json" -H 'Content-Type: application/json' http://localhost:8083/connectors -d @$2
        fi
        ;;
    ensure_schema)
        # Load environment variables from .env if present
        if [[ -f ./.env ]]; then
            set -o allexport
            # shellcheck disable=SC1091
            source ./.env
            set +o allexport
        fi

        PG_CONTAINER=${POSTGRES_CONTAINER:-c2c-cdc-postgresql}
        PG_USER=${POSTGRES_USER:-k6}
        PG_DB=${POSTGRES_DB:-k6}

        echo "Ensuring schema and tables exist on Postgres container $PG_CONTAINER (db=$PG_DB user=$PG_USER)"

        # Execute SQL inside the Postgres container
        docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" <<'SQL'
CREATE SCHEMA IF NOT EXISTS c2c;
CREATE TABLE IF NOT EXISTS c2c.trades (
    order_number TEXT PRIMARY KEY,
    adv_no TEXT,
    trade_type TEXT CHECK (trade_type IN ('BUY','SELL')),
    asset VARCHAR(16),
    fiat VARCHAR(16),
    fiat_symbol VARCHAR(16),
    amount NUMERIC(38, 8) CHECK (amount >= 0),
    total_price NUMERIC(38, 8) CHECK (total_price >= 0),
    unit_price NUMERIC(38, 8) CHECK (unit_price >= 0),
    order_status TEXT,
    create_time_ms BIGINT,
    create_time TIMESTAMPTZ,
    commission NUMERIC(38, 8) CHECK (commission >= 0),
    counter_part_nick_name TEXT,
    advertisement_role TEXT,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trades_create_time ON c2c.trades(create_time);
CREATE INDEX IF NOT EXISTS idx_trades_asset_fiat ON c2c.trades(asset, fiat);
CREATE INDEX IF NOT EXISTS idx_trades_trade_type_time ON c2c.trades(trade_type, create_time);
SQL
        ;;
    register_and_init)
        if [[ -z "$2" ]]; then
            echo "Missing connector config path"
            usage
            exit 1
        fi
        "$0" register_connector "$2"
        "$0" ensure_schema
        ;;
    *)
        echo -n "Unknown command: $cmd"
        usage
        exit 1
        ;;
esac