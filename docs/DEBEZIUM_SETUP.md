# 🔧 Debezium CDC Setup Guide

## 📋 Prerequisites

1. **Services Running:**
   ```bash
   docker-compose -f docker-compose-lakehouse.yml up -d
   ```

2. **Check Services:**
   ```bash
   docker-compose -f docker-compose-lakehouse.yml ps
   
   # Expected running:
   # - c2c-cdc-postgresql
   # - c2c-cdc-broker
   # - c2c-cdc-debezium
   # - c2c-cdc-zookeeper
   ```

3. **Tools Required:**
   - `curl` (for REST API calls)
   - `jq` (for JSON parsing) - Optional but recommended
   - `docker` (for container management)

## 🚀 Quick Start

### **Step 1: Make Script Executable**

```bash
chmod +x scripts/kafka_connector.sh
```

### **Step 2: Setup Schema & Register Connector (All-in-One)**

```bash
./scripts/kafka_connector.sh register_and_init configs/debezium-c2c-connector.json
```

**Expected Output:**
```
Detected: Running on host machine
Step 1/2: Creating schema and table...
Ensuring schema and tables exist on PostgreSQL...
Container: c2c-cdc-postgresql
Database: trading
User: loncak
✓ Schema and table created successfully

Step 2/2: Registering connector...
Checking Debezium connectivity at http://localhost:8083...
✓ Debezium is reachable
Registering connector from configs/debezium-c2c-connector.json...
✓ Connector registered successfully!
{
  "name": "c2c-postgres-connector",
  "config": {...}
}

✓ Setup complete!
```

---

## 📚 Available Commands

### **1. List All Connectors**

```bash
./scripts/kafka_connector.sh list_connectors
```

**Output:**
```
Listing all connectors...
  ● c2c-postgres-connector (RUNNING)
```

### **2. Check Connector Status**

```bash
./scripts/kafka_connector.sh status c2c-postgres-connector
```

**Output:**
```json
{
  "name": "c2c-postgres-connector",
  "connector": {
    "state": "RUNNING",
    "worker_id": "debezium:8083"
  },
  "tasks": [
    {
      "id": 0,
      "state": "RUNNING",
      "worker_id": "debezium:8083"
    }
  ]
}
```

### **3. Restart Connector**

```bash
./scripts/kafka_connector.sh restart_connector c2c-postgres-connector
```

### **4. Delete Connector**

```bash
./scripts/kafka_connector.sh delete_connector c2c-postgres-connector
```

### **5. Create Schema/Table Only**

```bash
./scripts/kafka_connector.sh ensure_schema
```

### **6. Register Connector Only**

```bash
./scripts/kafka_connector.sh register_connector configs/debezium-c2c-connector.json
```

---

## 🧪 Testing CDC Pipeline

### **Test 1: Insert New Record**

```bash
docker exec -it c2c-cdc-postgresql psql -U loncak -d trading <<'SQL'
INSERT INTO c2c.trades (
    order_number, 
    order_status, 
    amount, 
    total_price, 
    unit_price
) VALUES (
    'TEST-001', 
    'PENDING', 
    1000.50, 
    25000000, 
    24937.53
);
SQL
```

### **Test 2: Update Record**

```bash
docker exec -it c2c-cdc-postgresql psql -U loncak -d trading <<'SQL'
UPDATE c2c.trades 
SET order_status = 'COMPLETED' 
WHERE order_number = 'TEST-001';
SQL
```

### **Test 3: Check Kafka Topic**

```bash
# List topics
docker exec c2c-cdc-broker kafka-topics \
  --list \
  --bootstrap-server localhost:9092 | grep binance

# Expected: binance.c2c.trades

# Consume messages
docker exec c2c-cdc-broker kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic binance.c2c.trades \
  --from-beginning \
  --max-messages 5
```

**Expected CDC Event:**
```json
{
  "order_number": "TEST-001",
  "order_status": "COMPLETED",
  "amount": 1000.50,
  "total_price": 25000000,
  "unit_price": 24937.53,
  "__op": "u",
  "__table": "trades",
  "__source_ts_ms": 1698485400123
}
```

### **Test 4: Monitor in Debezium UI**

Open browser: http://localhost:8086

---

## 🔍 Troubleshooting

### **Issue 1: "Cannot connect to Debezium"**

```bash
# Check if Debezium is running
docker ps | grep debezium

# Check logs
docker logs c2c-cdc-debezium

# Restart Debezium
docker restart c2c-cdc-debezium

# Wait 30 seconds then retry
sleep 30
./scripts/kafka_connector.sh list_connectors
```

### **Issue 2: "PostgreSQL container not found"**

```bash
# List running containers
docker ps --format "{{.Names}}"

# If using different container name, set env var
export POSTGRES_CONTAINER=your-postgres-container-name
./scripts/kafka_connector.sh ensure_schema
```

### **Issue 3: Connector Status = FAILED**

```bash
# Get detailed status
./scripts/kafka_connector.sh status c2c-postgres-connector

# Check logs
docker logs c2c-cdc-debezium | tail -50

# Common issues:
# 1. PostgreSQL WAL not enabled
#    → Check: wal_level = logical in postgresql.conf
#    → Fix: docker-compose-lakehouse.yml has correct command

# 2. Wrong credentials
#    → Check: database.user/password in connector config

# 3. Table doesn't exist
#    → Run: ./scripts/kafka_connector.sh ensure_schema

# 4. Network issue
#    → Check: Both containers in same network
#    → Run: docker network inspect binance-merchant-trading-flow_default
```

### **Issue 4: No Messages in Kafka**

```bash
# 1. Verify connector is running
./scripts/kafka_connector.sh status c2c-postgres-connector

# 2. Check PostgreSQL has data
docker exec -it c2c-cdc-postgresql psql -U loncak -d trading -c \
  "SELECT COUNT(*) FROM c2c.trades;"

# 3. Check Debezium logs for errors
docker logs c2c-cdc-debezium | grep ERROR

# 4. Verify Kafka topic exists
docker exec c2c-cdc-broker kafka-topics --list \
  --bootstrap-server localhost:9092 | grep binance

# 5. Check topic has messages
docker exec c2c-cdc-broker kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic binance.c2c.trades
```

---

## 🎯 End-to-End Verification

Run this complete test:

```bash
#!/bin/bash
echo "=== CDC Pipeline E2E Test ==="

# 1. Check connector
echo "1. Checking connector status..."
./scripts/kafka_connector.sh status c2c-postgres-connector

# 2. Insert test data
echo "2. Inserting test data..."
docker exec -it c2c-cdc-postgresql psql -U loncak -d trading <<'SQL'
INSERT INTO c2c.trades (order_number, order_status, amount)
VALUES ('E2E-TEST-'||EXTRACT(EPOCH FROM NOW())::TEXT, 'PENDING', 999);
SQL

# 3. Wait for CDC
echo "3. Waiting 2 seconds for CDC..."
sleep 2

# 4. Check Kafka
echo "4. Checking Kafka topic..."
docker exec c2c-cdc-broker kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic binance.c2c.trades \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 5000

echo "=== Test Complete ==="
```

---

## 📊 Monitoring

### **Connector Metrics**

```bash
# Via REST API
curl -s http://localhost:8083/connectors/c2c-postgres-connector/status | jq

# Via Kafka Control Center
open http://localhost:9021
```

### **Kafka Topic Lag**

```bash
docker exec c2c-cdc-broker kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe \
  --group flink-streaming-consumer
```

### **PostgreSQL Replication Slot**

```bash
docker exec -it c2c-cdc-postgresql psql -U loncak -d trading <<'SQL'
SELECT * FROM pg_replication_slots WHERE slot_name = 'debezium_c2c_slot';
SQL
```

---

## 🔧 Advanced Configuration

### **Custom Environment Variables**

```bash
# Override Debezium URL
export DEBEZIUM_URL=http://custom-host:8083
./scripts/kafka_connector.sh list_connectors

# Override PostgreSQL container
export POSTGRES_CONTAINER=my-postgres
export POSTGRES_USER=myuser
export POSTGRES_DB=mydb
./scripts/kafka_connector.sh ensure_schema
```

### **Load from .env file**

Script automatically loads variables from `.env` if it exists:

```bash
# .env
POSTGRES_CONTAINER=c2c-cdc-postgresql
POSTGRES_USER=loncak
POSTGRES_DB=trading
```

---

## 📝 Connector Configuration Reference

See `configs/debezium-c2c-connector.json` for full config.

**Key Settings:**

| Config | Value | Purpose |
|--------|-------|---------|
| `database.hostname` | `postgresql` | Service name (NOT localhost!) |
| `table.include.list` | `c2c.trades` | Only capture this table |
| `plugin.name` | `pgoutput` | PostgreSQL 10+ native plugin |
| `topic.prefix` | `binance` | Kafka topic prefix |
| `snapshot.mode` | `initial` | Read existing data on startup |
| `transforms` | `unwrap` | Simplify CDC event format |

---

## 🎓 Next Steps

After successful setup:

1. ✅ Verify connector is RUNNING
2. ✅ Test CDC with insert/update
3. ✅ Check Kafka messages
4. ✅ Deploy Flink consumer (see `docs/NETWORK_SETUP.md`)
5. ✅ Run end-to-end Airflow DAG

**Complete Architecture:**
```
Airflow DAG (*/5) → PostgreSQL → Debezium → Kafka → Flink → Analytics
```

Happy streaming! 🚀

