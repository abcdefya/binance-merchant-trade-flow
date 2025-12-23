# Docker Network Setup Guide

## Kết nối 2 Docker Networks

Tôi đã cấu hình để Airflow và Lakehouse (PostgreSQL, Kafka, Flink) có thể giao tiếp với nhau thông qua shared network.

### Cấu trúc Networks

```
┌─────────────────────────────────────┐
│  airflow_default                    │
│  - airflow-apiserver                │
│  - airflow-scheduler                │
│  - airflow-worker                   │
│  - postgres (Airflow metadata)      │
│  - redis                            │
└──────────────┬──────────────────────┘
               │
               │ (bridge)
               │
┌──────────────┴──────────────────────┐
│  binance-merchant-trading-flow_     │
│  default (lakehouse)                │
│  - postgresql (C2C data)            │
│  - kafka/broker                     │
│  - flink-jobmanager                 │
│  - minio                            │
│  - debezium                         │
└─────────────────────────────────────┘
```

### Thay đổi đã thực hiện

#### 1. `docker-compose.yaml` (Airflow)

```yaml
# Thêm vào airflow-common
networks:
  - default          # Network riêng của Airflow
  - lakehouse        # Network external từ lakehouse

# Thêm vào cuối file
networks:
  default:
    name: airflow_default
  lakehouse:
    external: true
    name: binance-merchant-trading-flow_default
```

#### 2. `docker-compose-lakehouse.yml`

```yaml
# Thêm vào cuối file
networks:
  default:
    name: binance-merchant-trading-flow_default
```

## Cách triển khai

### Bước 1: Start Lakehouse trước (tạo network)

```bash
# Từ thư mục gốc project
docker-compose -f docker-compose-lakehouse.yml up -d
```

**Giải thích:** Lakehouse phải start trước để tạo network `binance-merchant-trading-flow_default`. Airflow sẽ join vào network này.

### Bước 2: Verify network đã được tạo

```bash
docker network ls | grep binance
```

Kết quả mong đợi:
```
NETWORK ID     NAME                                    DRIVER    SCOPE
xxxxxxxxxxxx   binance-merchant-trading-flow_default   bridge    local
```

### Bước 3: Start Airflow

```bash
# Stop Airflow nếu đang chạy
docker-compose down

# Start lại
docker-compose up -d
```

### Bước 4: Verify kết nối

```bash
# Check xem Airflow containers đã join vào lakehouse network chưa
docker network inspect binance-merchant-trading-flow_default
```

Trong output, bạn sẽ thấy các containers của Airflow:
- airflow-apiserver
- airflow-scheduler
- airflow-worker
- airflow-triggerer

## Cập nhật Environment Variables

Bây giờ có thể sử dụng **tên service** thay vì `host.docker.internal`:

### Cập nhật file `.env`:

```bash
# PostgreSQL Configuration - SỬ DỤNG SERVICE NAME
POSTGRES_HOST=postgresql          # Tên service trong docker-compose-lakehouse.yml
POSTGRES_PORT=5432
POSTGRES_DB=trading
POSTGRES_USER=loncak
POSTGRES_PASSWORD=loncak

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=broker:29092    # Tên service
KAFKA_TOPIC=binance.c2c.trades

# Flink Configuration  
FLINK_JOBMANAGER_HOST=flink-jobmanager  # Tên service

# MinIO Configuration
MINIO_ENDPOINT=http://minio:9000        # Tên service
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

## Test kết nối

### Test 1: Ping từ Airflow container đến PostgreSQL

```bash
# Exec vào Airflow worker
docker exec -it binance-merchant-trading-flow-airflow-worker-1 bash

# Ping PostgreSQL service
ping postgresql

# Hoặc test với psql
apt-get update && apt-get install -y postgresql-client
psql -h postgresql -U loncak -d trading
```

### Test 2: Chạy Python test trong Airflow container

```bash
docker exec -it binance-merchant-trading-flow-airflow-worker-1 python3 << 'EOF'
import os
os.environ['POSTGRES_HOST'] = 'postgresql'
os.environ['POSTGRES_PORT'] = '5432'
os.environ['POSTGRES_DB'] = 'trading'
os.environ['POSTGRES_USER'] = 'loncak'
os.environ['POSTGRES_PASSWORD'] = 'loncak'

from src.utils.postgresql_client import create_client_from_env
try:
    client = create_client_from_env()
    print("✅ Connection successful!")
except Exception as e:
    print(f"❌ Connection failed: {e}")
EOF
```

### Test 3: Trigger DAG và check logs

```bash
# Trigger DAG
docker exec -it binance-merchant-trading-flow-airflow-scheduler-1 \
  airflow dags trigger binance_c2c_streaming

# Check logs
docker-compose logs -f airflow-scheduler airflow-worker
```

## Troubleshooting

### Lỗi: "network binance-merchant-trading-flow_default not found"

**Nguyên nhân:** Lakehouse chưa start hoặc network chưa được tạo.

**Giải pháp:**
```bash
# Start lakehouse trước
docker-compose -f docker-compose-lakehouse.yml up -d

# Verify network
docker network ls | grep binance

# Sau đó mới start Airflow
docker-compose up -d
```

### Lỗi: "network lakehouse has active endpoints"

**Nguyên nhân:** Cố stop Airflow trong khi đang join vào external network.

**Giải pháp:**
```bash
# Stop Airflow trước
docker-compose down

# Stop lakehouse sau
docker-compose -f docker-compose-lakehouse.yml down
```

### Lỗi: Connection timeout

**Kiểm tra:**
```bash
# 1. Check cả 2 containers có trong cùng network không
docker network inspect binance-merchant-trading-flow_default

# 2. Check PostgreSQL có running không
docker ps | grep postgresql

# 3. Check port PostgreSQL
docker exec -it c2c-cdc-postgresql psql -U loncak -d trading -c "SELECT 1"
```

## Best Practices

### 1. Thứ tự start/stop

**Start:**
```bash
# 1. Start lakehouse trước (tạo network + services)
docker-compose -f docker-compose-lakehouse.yml up -d

# 2. Đợi PostgreSQL healthy
docker-compose -f docker-compose-lakehouse.yml ps

# 3. Start Airflow (join vào network)
docker-compose up -d
```

**Stop:**
```bash
# 1. Stop Airflow trước
docker-compose down

# 2. Stop lakehouse sau
docker-compose -f docker-compose-lakehouse.yml down
```

### 2. Rebuild containers

Nếu thay đổi network config:
```bash
# Stop everything
docker-compose down
docker-compose -f docker-compose-lakehouse.yml down

# Rebuild và start lại
docker-compose -f docker-compose-lakehouse.yml up -d --build
docker-compose up -d --build
```

### 3. Clean up networks (nếu cần)

```bash
# List networks
docker network ls

# Remove unused networks
docker network prune
```

## Summary

✅ **Đã hoàn thành:**
- Cấu hình Airflow join vào lakehouse network
- Airflow có thể truy cập: PostgreSQL, Kafka, Flink, MinIO
- Sử dụng service names thay vì IP addresses

✅ **Service names có thể dùng trong DAG:**
- `postgresql` - PostgreSQL database
- `broker` - Kafka broker
- `flink-jobmanager` - Flink JobManager
- `minio` - MinIO storage
- `schema-registry` - Kafka Schema Registry
- `debezium` - Debezium CDC

✅ **Lợi ích:**
- Không cần `host.docker.internal`
- Dễ scale và maintain
- Service discovery tự động
- Better network isolation

