#!/bin/bash

# Script to stop all services in correct order
# Usage: ./scripts/stop-all.sh

set -e

echo "🛑 Stopping Binance C2C Trading Flow..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Stop Airflow (must stop first as it depends on lakehouse network)
echo -e "${YELLOW}Step 1: Stopping Airflow services...${NC}"
docker-compose down
echo -e "${GREEN}✓ Airflow stopped${NC}"

# Step 2: Stop Lakehouse
echo ""
echo -e "${YELLOW}Step 2: Stopping Lakehouse services...${NC}"
docker-compose -f docker-compose-lakehouse.yml down
echo -e "${GREEN}✓ Lakehouse stopped${NC}"

# Summary
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ All services stopped successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "💡 To remove volumes (WARNING: will delete data):"
echo "  docker-compose down -v"
echo "  docker-compose -f docker-compose-lakehouse.yml down -v"
echo ""
echo "💡 To start again:"
echo "  ./scripts/start-all.sh"
echo ""

