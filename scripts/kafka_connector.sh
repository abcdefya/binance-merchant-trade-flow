#!/bin/bash
set -e  # Exit on error

cmd=$1

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Auto-detect if running inside container or on host
if [ -f /.dockerenv ]; then
    # Running inside container → use service name
    DEBEZIUM_URL=${DEBEZIUM_URL:-http://debezium:8083}
    echo -e "${YELLOW}Detected: Running inside container${NC}"
else
    # Running on host → use localhost
    DEBEZIUM_URL=${DEBEZIUM_URL:-http://localhost:8083}
    echo -e "${YELLOW}Detected: Running on host machine${NC}"
fi

usage() {
    echo "kafka_connector.sh <command> <arguments>"
    echo ""
    echo "Available commands:"
    echo "  register_connector <config>  Register a new Kafka connector"
    echo "  list_connectors              List all registered connectors"
    echo "  status <name>                Get connector status"
    echo "  delete_connector <name>      Delete a connector"
    echo "  restart_connector <name>     Restart a connector"
    echo "  ensure_schema                Create Postgres schema/table if not exists"
    echo "  register_and_init <config>   Create schema + register connector"
    echo ""
    echo "Arguments:"
    echo "  <config>  Path to connector config JSON file"
    echo "  <name>    Connector name"
    echo ""
    echo "Environment variables:"
    echo "  DEBEZIUM_URL                 Debezium REST API URL (default: auto-detect)"
    echo ""
    echo "Examples:"
    echo "  ./scripts/kafka_connector.sh list_connectors"
    echo "  ./scripts/kafka_connector.sh register_connector configs/debezium-c2c-connector.json"
    echo "  ./scripts/kafka_connector.sh status c2c-postgres-connector"
}

check_debezium() {
    echo -e "${YELLOW}Checking Debezium connectivity at $DEBEZIUM_URL...${NC}"
    if curl -s -f "$DEBEZIUM_URL/connectors" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Debezium is reachable${NC}"
        return 0
    else
        echo -e "${RED}✗ Cannot connect to Debezium at $DEBEZIUM_URL${NC}"
        echo "Make sure:"
        echo "  1. Debezium container is running: docker-compose -f docker-compose-lakehouse.yml ps debezium"
        echo "  2. Port 8083 is accessible"
        echo "  3. Try: curl $DEBEZIUM_URL/connectors"
        return 1
    fi
}

if [[ -z "$cmd" ]]; then
    echo -e "${RED}Missing command${NC}"
    usage
    exit 1
fi

case $cmd in
    register_connector)
        if [[ -z "$2" ]]; then
            echo -e "${RED}Missing connector config path${NC}"
            usage
            exit 1
        fi
        
        if [[ ! -f "$2" ]]; then
            echo -e "${RED}Config file not found: $2${NC}"
            exit 1
        fi
        
        check_debezium || exit 1
        
        echo -e "${YELLOW}Registering connector from $2...${NC}"
        response=$(curl -s -w "\n%{http_code}" -X POST \
            -H "Accept:application/json" \
            -H "Content-Type: application/json" \
            "$DEBEZIUM_URL/connectors" \
            -d @"$2")
        
        http_code=$(echo "$response" | tail -n1)
        body=$(echo "$response" | sed '$d')
        
        if [[ $http_code -ge 200 && $http_code -lt 300 ]]; then
            echo -e "${GREEN}✓ Connector registered successfully!${NC}"
            echo "$body" | jq '.' 2>/dev/null || echo "$body"
        else
            echo -e "${RED}✗ Failed to register connector (HTTP $http_code)${NC}"
            echo "$body" | jq '.' 2>/dev/null || echo "$body"
            exit 1
        fi
        ;;
    
    list_connectors)
        check_debezium || exit 1
        
        echo -e "${YELLOW}Listing all connectors...${NC}"
        connectors=$(curl -s "$DEBEZIUM_URL/connectors")
        
        if [[ $(echo "$connectors" | jq '. | length') -eq 0 ]]; then
            echo -e "${YELLOW}No connectors registered${NC}"
        else
            echo "$connectors" | jq -r '.[]' | while read -r conn; do
                status=$(curl -s "$DEBEZIUM_URL/connectors/$conn/status" | jq -r '.connector.state')
                if [[ "$status" == "RUNNING" ]]; then
                    echo -e "  ${GREEN}●${NC} $conn (${GREEN}$status${NC})"
                else
                    echo -e "  ${RED}●${NC} $conn (${RED}$status${NC})"
                fi
            done
        fi
        ;;
    
    status)
        if [[ -z "$2" ]]; then
            echo -e "${RED}Missing connector name${NC}"
            usage
            exit 1
        fi
        
        check_debezium || exit 1
        
        echo -e "${YELLOW}Getting status for connector: $2${NC}"
        status=$(curl -s "$DEBEZIUM_URL/connectors/$2/status")
        
        if [[ $(echo "$status" | jq -r '.error_code' 2>/dev/null) == "404" ]]; then
            echo -e "${RED}✗ Connector not found: $2${NC}"
            exit 1
        fi
        
        echo "$status" | jq '.'
        ;;
    
    delete_connector)
        if [[ -z "$2" ]]; then
            echo -e "${RED}Missing connector name${NC}"
            usage
            exit 1
        fi
        
        check_debezium || exit 1
        
        echo -e "${YELLOW}Deleting connector: $2${NC}"
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$DEBEZIUM_URL/connectors/$2")
        
        http_code=$(echo "$response" | tail -n1)
        
        if [[ $http_code -eq 204 ]]; then
            echo -e "${GREEN}✓ Connector deleted successfully${NC}"
        else
            echo -e "${RED}✗ Failed to delete connector (HTTP $http_code)${NC}"
            echo "$response" | sed '$d'
            exit 1
        fi
        ;;
    
    restart_connector)
        if [[ -z "$2" ]]; then
            echo -e "${RED}Missing connector name${NC}"
            usage
            exit 1
        fi
        
        check_debezium || exit 1
        
        echo -e "${YELLOW}Restarting connector: $2${NC}"
        response=$(curl -s -w "\n%{http_code}" -X POST "$DEBEZIUM_URL/connectors/$2/restart")
        
        http_code=$(echo "$response" | tail -n1)
        
        if [[ $http_code -eq 204 || $http_code -eq 202 ]]; then
            echo -e "${GREEN}✓ Connector restart initiated${NC}"
        else
            echo -e "${RED}✗ Failed to restart connector (HTTP $http_code)${NC}"
            exit 1
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
        PG_USER=${POSTGRES_USER:-loncak}
        PG_DB=${POSTGRES_DB:-trading}

        echo -e "${YELLOW}Ensuring schema and tables exist on PostgreSQL...${NC}"
        echo "Container: $PG_CONTAINER"
        echo "Database: $PG_DB"
        echo "User: $PG_USER"
        
        # Check if container exists
        if ! docker ps --format '{{.Names}}' | grep -q "^$PG_CONTAINER$"; then
            echo -e "${RED}✗ PostgreSQL container not found: $PG_CONTAINER${NC}"
            echo "Available containers:"
            docker ps --format "  - {{.Names}}"
            exit 1
        fi

        # Execute SQL inside the Postgres container
        docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" <<'SQL'
-- Create schema
CREATE SCHEMA IF NOT EXISTS c2c;

-- Create trades table
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
    commission NUMERIC(38, 8) CHECK (commission >= 0),
    counter_part_nick_name TEXT,
    advertisement_role TEXT,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_trades_order_status ON c2c.trades(order_status);
CREATE INDEX IF NOT EXISTS idx_trades_create_time ON c2c.trades(create_time_ms);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_trades_updated_at ON c2c.trades;
CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON c2c.trades
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Show table info
\d c2c.trades

SQL
        
        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}✓ Schema and table created successfully${NC}"
        else
            echo -e "${RED}✗ Failed to create schema/table${NC}"
            exit 1
        fi
        ;;
    
    register_and_init)
        if [[ -z "$2" ]]; then
            echo -e "${RED}Missing connector config path${NC}"
            usage
            exit 1
        fi
        
        echo -e "${GREEN}Step 1/2: Creating schema and table...${NC}"
        "$0" ensure_schema
        
        echo ""
        echo -e "${GREEN}Step 2/2: Registering connector...${NC}"
        "$0" register_connector "$2"
        
        echo ""
        echo -e "${GREEN}✓ Setup complete!${NC}"
        echo "Next steps:"
        echo "  1. Check connector status: $0 status c2c-postgres-connector"
        echo "  2. Monitor Kafka topic: docker exec c2c-cdc-broker kafka-console-consumer --bootstrap-server localhost:9092 --topic binance.c2c.trades --from-beginning"
        ;;
    
    *)
        echo -e "${RED}Unknown command: $cmd${NC}"
        usage
        exit 1
        ;;
esac