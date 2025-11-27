# Streaming DAG Setup Guide

## Lỗi PostgreSQL Connection Refused

### Nguyên nhân
Khi chạy DAG trong Airflow container, `127.0.0.1` trỏ đến localhost của container, không phải host machine. Do đó không thể kết nối đến PostgreSQL.

### Giải pháp

#### Option 1: Sử dụng `host.docker.internal` (Recommended)

Tạo hoặc cập nhật file `.env` tại thư mục gốc project:

```bash
# PostgreSQL Configuration (for Airflow tasks)
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5432
POSTGRES_DB=trading
POSTGRES_USER=loncak
POSTGRES_PASSWORD=loncak
```

**Lưu ý:** `host.docker.internal` là DNS đặc biệt của Docker cho phép container kết nối đến services trên host machine.

#### Option 2: Kết nối hai Docker networks

Nếu Option 1 không hoạt động, hãy thêm Airflow vào network của lakehouse:

Trong `docker-compose.yaml`, thêm network external:

```yaml
services:
  airflow-apiserver:
    <<: *airflow-common
    # ... existing config ...
    networks:
      - default
      - lakehouse_default  # Thêm network này

networks:
  lakehouse_default:
    external: true
    name: binance-merchant-trading-flow_default
```

Sau đó set trong `.env`:

```bash
POSTGRES_HOST=postgresql  # Tên service trong docker-compose-lakehouse.yml
POSTGRES_PORT=5432
```

#### Option 3: Sử dụng IP của host machine

Nếu các option trên không work, sử dụng IP của máy host:

```bash
# Windows: ipconfig
# Linux/Mac: ifconfig hoặc ip addr show

POSTGRES_HOST=192.168.x.x  # Thay bằng IP thực tế của bạn
POSTGRES_PORT=5432
```

## Vấn đề phụ: Không có dữ liệu

Log cho thấy: `"Fetched 0 trade records"` - có thể do:

1. **Không có trades trong khoảng thời gian hiện tại** (từ 00:00 hôm nay đến bây giờ)
2. **API key không có quyền truy cập trades**

### Kiểm tra:

```python
# Test trong notebook
from src.components.data_ingestion import C2CExtended
from binance_sdk_c2c.c2c import ConfigurationRestAPI, C2C_REST_API_PROD_URL
import os

api_key = os.getenv("API_KEY")
api_secret = os.getenv("API_SECRET")

config = ConfigurationRestAPI(
    api_key=api_key,
    api_secret=api_secret,
    base_path=C2C_REST_API_PROD_URL
)

client = C2CExtended(config)
data = client.get_latest()
print(f"Found {len(data)} trades")
```

## Restart Airflow sau khi cập nhật .env

```bash
# Stop Airflow
docker-compose down

# Start lại
docker-compose up -d

# Check logs
docker-compose logs -f airflow-scheduler
```

## Test kết nối PostgreSQL từ Airflow container

```bash
# Exec vào Airflow container
docker exec -it <airflow-container-id> bash

# Test connection
python3 << EOF
import os
os.environ['POSTGRES_HOST'] = 'host.docker.internal'
os.environ['POSTGRES_PORT'] = '5432'
os.environ['POSTGRES_DB'] = 'trading'
os.environ['POSTGRES_USER'] = 'loncak'
os.environ['POSTGRES_PASSWORD'] = 'loncak'

from src.utils.postgresql_client import create_client_from_env
client = create_client_from_env()
print("Connection successful!")
EOF
```

## Environment Variables đầy đủ

Tạo file `.env` với nội dung sau:

```bash
# Binance API Credentials
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here
BASE_PATH=https://api.binance.com

# PostgreSQL Configuration (QUAN TRỌNG!)
POSTGRES_HOST=host.docker.internal  # hoặc postgresql nếu dùng same network
POSTGRES_PORT=5432
POSTGRES_DB=trading
POSTGRES_USER=loncak
POSTGRES_PASSWORD=loncak

# MinIO Configuration
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_ENDPOINT=http://minio:9000

# Lakehouse paths
BRONZE_PATH=s3a://bronze/c2c_trades/
SILVER_PATH=s3a://silver/c2c_trades/
GOLD_PATH=s3a://gold/

# Docker configuration
DOCKER_URL=tcp://host.docker.internal:2375
LAKEHOUSE_NETWORK=binance-merchant-trading-flow_default

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=broker:29092
KAFKA_TOPIC=binance.c2c.trades
KAFKA_GROUP_ID=flink-streaming-consumer

# Airflow Configuration
AIRFLOW_UID=50000
_AIRFLOW_WWW_USER_USERNAME=airflow
_AIRFLOW_WWW_USER_PASSWORD=airflow
AIRFLOW_PROJ_DIR=.
```

