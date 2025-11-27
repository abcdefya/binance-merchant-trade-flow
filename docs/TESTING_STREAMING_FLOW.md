# 🧪 Testing Streaming Flow - End-to-End Guide

## 📋 Prerequisites

Before testing, ensure these services are running:

```bash
# Check all lakehouse services
docker-compose -f docker-compose-lakehouse.yml ps

# Required services should be RUNNING:
# ✅ c2c-cdc-postgresql       (database)
# ✅ c2c-cdc-broker           (Kafka)
# ✅ c2c-cdc-debezium         (CDC connector)
# ✅ c2c-flink-consumer       (Flink streaming)
```

---

## 🔄 Complete Testing Flow

### **Step 1: Verify Debezium Connector is Registered**

```bash
# List all connectors
./scripts/kafka_connector.sh list_connectors

# Expected output:
#   ● c2c-postgres-connector (RUNNING)
```

**If not registered:**
```bash
# Register the connector
./scripts/kafka_connector.sh register_and_init configs/debezium-c2c-connector.json
```

---

### **Step 2: Start Flink Service (if not running)**

```bash
# Start Flink consumer
docker-compose -f docker-compose-lakehouse.yml up -d flink-consumer

# Verify it's running
docker ps | findstr flink  # Windows
docker ps | grep flink     # Linux/Mac

# Check Flink logs
docker logs -f c2c-flink-consumer
```

**Expected Flink startup logs:**
```
2025-10-29 23:10:15,123 - INFO - 🚀 Flink streaming job started
2025-10-29 23:10:17,456 - INFO - Initializing Flink environment...
2025-10-29 23:10:19,789 - INFO - Loading JARs...
2025-10-29 23:10:22,012 - INFO - Configuring Kafka source...
2025-10-29 23:10:24,345 - INFO - Creating data stream...
2025-10-29 23:10:26,678 - INFO - Executing Flink job...
```

---

### **Step 3: Trigger Airflow DAG**

**Option A: Via Airflow UI**
1. Open Airflow UI: http://localhost:8080
2. Find DAG: `binance_c2c_streaming`
3. Click "Trigger DAG" button (play icon ▶️)

**Option B: Via Airflow CLI**
```bash
# Trigger DAG manually
docker exec -it airflow-scheduler airflow dags trigger binance_c2c_streaming
```

---

### **Step 4: Monitor the Flow**

#### **4.1 Check Airflow DAG Logs**

```
# In Airflow UI → DAG Runs → Click on latest run → Task: fetch_latest_and_insert_postgres

Expected logs:
  ✅ Fetched 100 trade records
  ✅ PostgreSQL operation summary: {'inserted': 5, 'updated': 95}
  ✅ Backup parquet saved to /shared_volume/c2c/streaming/c2c_trades_20251029231015.parquet
```

#### **4.2 Check Debezium Logs (CDC capture)**

```bash
docker logs c2c-cdc-debezium --tail 50

# Expected output:
# Debezium should show:
#   - "Sent X events to topic binance.c2c.trades"
```

#### **4.3 Check Kafka Messages**

```bash
# Consume messages from Kafka topic (raw view)
docker exec c2c-cdc-broker kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic binance.c2c.trades \
  --from-beginning \
  --max-messages 5
```

**Expected output:**
```json
{"order_number":"123456","adv_no":"abc","trade_type":"BUY","asset":"USDT",...}
{"order_number":"123457","adv_no":"def","trade_type":"SELL","asset":"USDT",...}
```

#### **4.4 Check Flink Consumer Logs (THE MAIN OUTPUT!)**

```bash
# Watch Flink logs in real-time
docker logs -f c2c-flink-consumer

# You should see messages printed by Flink:
```

**Expected Flink output when consuming Kafka:**
```
2025-10-29 23:15:30,123 - INFO - Executing Flink job...

# Messages from Kafka (printed by ds.print()):
{"order_number":"123456","adv_no":"abc","trade_type":"BUY","asset":"USDT","fiat":"VND","amount":100.5,"total_price":2500000,"unit_price":24876.24,"order_status":"COMPLETED","create_time_ms":1698630000000,"commission":0.1,"counter_part_nick_name":"trader123","advertisement_role":"MAKER","__op":"c","__table":"c2c.trades","__source_ts_ms":1698630015000}

{"order_number":"123457","adv_no":"def","trade_type":"SELL","asset":"USDT","fiat":"VND","amount":200.0,"total_price":5000000,"unit_price":25000.00,"order_status":"PENDING","create_time_ms":1698630005000,"commission":0.2,"counter_part_nick_name":"trader456","advertisement_role":"TAKER","__op":"c","__table":"c2c.trades","__source_ts_ms":1698630020000}
```

**Explanation of CDC fields:**
- `__op`: Operation type (`c` = create/insert, `u` = update, `d` = delete)
- `__table`: Source table name
- `__source_ts_ms`: Timestamp when CDC captured the change
- Other fields: Original table columns

---

## 🎯 **ANSWER TO YOUR QUESTION:**

### **Q: Khi chạy DAG, có đảm bảo message từ Flink in ra không?**

### **A: CÓ, nhưng với các điều kiện sau:**

#### ✅ **YÊU CẦU:**
1. **Debezium connector đang chạy và RUNNING**
   ```bash
   ./scripts/kafka_connector.sh status c2c-postgres-connector
   ```

2. **Flink service đang chạy 24/7**
   ```bash
   docker ps | findstr c2c-flink-consumer
   ```

3. **DAG insert/update data mới (không phải duplicate)**
   - Nếu DAG fetch cùng data đã có trong DB → Debezium không tạo CDC event
   - Chỉ có INSERT hoặc UPDATE mới trigger CDC

4. **Xem đúng nơi in log:**
   - ❌ KHÔNG xem ở Airflow logs
   - ✅ Xem ở Flink container logs: `docker logs -f c2c-flink-consumer`

---

## 🧪 **Quick Test Script**

Save this as `test_streaming_flow.sh`:

```bash
#!/bin/bash

echo "🧪 Testing Streaming Flow End-to-End"
echo "====================================="
echo ""

# Step 1: Check services
echo "Step 1: Checking required services..."
services=("c2c-cdc-postgresql" "c2c-cdc-broker" "c2c-cdc-debezium" "c2c-flink-consumer")
for svc in "${services[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^$svc$"; then
        echo "  ✅ $svc is running"
    else
        echo "  ❌ $svc is NOT running"
        exit 1
    fi
done
echo ""

# Step 2: Check Debezium connector
echo "Step 2: Checking Debezium connector..."
./scripts/kafka_connector.sh status c2c-postgres-connector > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  ✅ c2c-postgres-connector is registered"
else
    echo "  ❌ Connector not found. Registering now..."
    ./scripts/kafka_connector.sh register_and_init configs/debezium-c2c-connector.json
fi
echo ""

# Step 3: Trigger Airflow DAG
echo "Step 3: Triggering Airflow DAG..."
docker exec airflow-scheduler airflow dags trigger binance_c2c_streaming
echo "  ✅ DAG triggered"
echo ""

# Step 4: Wait for data flow
echo "Step 4: Waiting 10 seconds for data to flow through the pipeline..."
sleep 10
echo ""

# Step 5: Show Flink logs
echo "Step 5: Showing latest Flink consumer logs (last 30 lines)..."
echo "-------------------------------------------------------------"
docker logs c2c-flink-consumer --tail 30
echo ""

echo "✅ Test complete!"
echo ""
echo "To monitor Flink in real-time, run:"
echo "  docker logs -f c2c-flink-consumer"
```

**Usage:**
```bash
chmod +x test_streaming_flow.sh
./test_streaming_flow.sh
```

---

## 🐛 Troubleshooting

### **Problem 1: No messages in Flink logs**

**Possible causes:**
1. **Debezium connector not running**
   ```bash
   ./scripts/kafka_connector.sh list_connectors
   # Should show: c2c-postgres-connector (RUNNING)
   ```

2. **DAG inserted duplicate data (no change detected)**
   - Insert NEW data manually to test:
   ```bash
   docker exec -it c2c-cdc-postgresql psql -U loncak -d loncak -c \
     "INSERT INTO c2c.trades (order_number, trade_type, asset, fiat, amount, total_price, unit_price, order_status, create_time_ms) 
      VALUES ('TEST_$(date +%s)', 'BUY', 'USDT', 'VND', 100, 2500000, 25000, 'COMPLETED', $(date +%s)000);"
   ```
   - Then check Flink logs:
   ```bash
   docker logs c2c-flink-consumer --tail 10
   ```

3. **Kafka topic empty**
   ```bash
   docker exec c2c-cdc-broker kafka-console-consumer \
     --bootstrap-server localhost:9092 \
     --topic binance.c2c.trades \
     --from-beginning \
     --max-messages 1 \
     --timeout-ms 5000
   ```

---

### **Problem 2: Flink service keeps restarting**

```bash
# Check error logs
docker logs c2c-flink-consumer --tail 100

# Common issues:
# - Java not found → rebuild image with `default-jdk`
# - Kafka connection refused → check KAFKA_BOOTSTRAP_SERVERS env
# - JAR files missing → check Dockerfile.streaming COPY jars/
```

---

### **Problem 3: Debezium connector in FAILED state**

```bash
# Get detailed status
./scripts/kafka_connector.sh status c2c-postgres-connector

# Restart connector
./scripts/kafka_connector.sh restart_connector c2c-postgres-connector

# If still fails, delete and re-register
./scripts/kafka_connector.sh delete_connector c2c-postgres-connector
./scripts/kafka_connector.sh register_and_init configs/debezium-c2c-connector.json
```

---

## 📊 Expected Timeline

When you trigger the DAG, here's the expected timing:

```
T+0s    : DAG starts (fetch_latest_and_insert_postgres)
T+5s    : Data inserted to PostgreSQL
T+5s    : DAG completes ✅
T+6s    : Debezium detects changes in PostgreSQL WAL
T+7s    : Debezium sends events to Kafka
T+8s    : Flink consumes messages from Kafka
T+8s    : Messages printed in Flink logs 🎉
```

**Total latency: ~8 seconds from API fetch to Flink processing**

---

## 🎓 Summary

| Component | Role | Where to Monitor |
|-----------|------|------------------|
| **Airflow DAG** | Fetch API data → Insert PostgreSQL | Airflow UI logs |
| **Debezium CDC** | Capture DB changes → Kafka | `docker logs c2c-cdc-debezium` |
| **Kafka** | Message queue | `kafka-console-consumer` |
| **Flink Service** | Consume Kafka → Process | `docker logs c2c-flink-consumer` ⭐ |

**Key takeaway:** 
- Flink messages are printed in **Flink container logs**, NOT Airflow logs
- The flow is: `Airflow → PostgreSQL → Debezium → Kafka → Flink`
- Each component runs independently and can be monitored separately

