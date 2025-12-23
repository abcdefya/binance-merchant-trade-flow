#!/bin/bash

# Script to start all services in correct order
# Usage: ./scripts/start-all.sh

set -e

echo "🚀 Starting Binance C2C Trading Flow..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Start Lakehouse (creates network)
echo -e "${YELLOW}Step 1: Starting Lakehouse services...${NC}"
docker-compose -f docker-compose-lakehouse.yml up -d

# Wait for PostgreSQL to be healthy
echo -e "${YELLOW}Waiting for PostgreSQL to be healthy...${NC}"
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if docker exec c2c-cdc-postgresql pg_isready -U loncak -d trading > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PostgreSQL is healthy${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo "Attempt $attempt/$max_attempts..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "❌ PostgreSQL failed to start"
    exit 1
fi

# Step 2: Verify network
echo ""
echo -e "${YELLOW}Step 2: Verifying Docker network...${NC}"
if docker network inspect binance-merchant-trading-flow_default > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Network 'binance-merchant-trading-flow_default' exists${NC}"
else
    echo "❌ Network not found"
    exit 1
fi

# Step 3: Start Airflow
echo ""
echo -e "${YELLOW}Step 3: Starting Airflow services...${NC}"
docker-compose up -d

# Wait for Airflow to be healthy
echo -e "${YELLOW}Waiting for Airflow to be healthy...${NC}"
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Airflow is healthy${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo "Attempt $attempt/$max_attempts..."
    sleep 3
done

# Summary
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ All services started successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "📊 Service URLs:"
echo "  • Airflow UI:        http://localhost:8080"
echo "  • Kafka Control:     http://localhost:9021"
echo "  • Flink UI:          http://localhost:8081"
echo "  • MinIO Console:     http://localhost:9001"
echo "  • Debezium UI:       http://localhost:8086"
echo "  • Trino:             http://localhost:8084"
echo ""
echo "🔐 Credentials:"
echo "  • Airflow:           airflow / airflow"
echo "  • MinIO:             Check .env file"
echo ""
echo "🔍 Check status:"
echo "  docker-compose ps"
echo "  docker-compose -f docker-compose-lakehouse.yml ps"
echo ""
echo "📝 View logs:"
echo "  docker-compose logs -f airflow-scheduler"
echo "  docker-compose -f docker-compose-lakehouse.yml logs -f postgresql"
echo ""

