# Airflow Setup Guide

## Giới thiệu

Airflow được sử dụng để orchestrate và schedule các data pipelines cho Binance P2P trading data.

## Cấu trúc

```
.
├── docker-compose-airflow.yml   # Airflow services
├── Dockerfile                   # Custom Airflow image với dependencies
├── dags/                        # Airflow DAGs
│   └── binance_get_latest_dag.py  # DAG lấy dữ liệu latest trades
├── logs/                        # Airflow logs
├── plugins/                     # Airflow plugins (nếu có)
└── .env                         # Environment variables
```

## Cài đặt

### 1. Tạo file .env

```bash
cp .env.airflow.example .env
```

Chỉnh sửa file `.env` với thông tin của bạn:
- `BINANCE_API_KEY`: API key từ Binance (optional)
- `BINANCE_API_SECRET`: API secret từ Binance (optional)
- `MINIO_ROOT_USER`: MinIO username
- `MINIO_ROOT_PASSWORD`: MinIO password

### 2. Set AIRFLOW_UID (Linux/Mac)

```bash
echo -e "AIRFLOW_UID=$(id -u)" >> .env
```

Trên Windows, set `AIRFLOW_UID=50000` trong file `.env`

### 3. Build Docker image

```bash
docker build -t binance_flow .
```

### 4. Start các services cần thiết (MinIO, PostgreSQL, etc.)

Đầu tiên start các services chính:

```bash
docker-compose up -d
```

### 5. Start Airflow

```bash
docker-compose -f docker-compose-airflow.yml up -d
```

### 6. Truy cập Airflow UI

- URL: http://localhost:8085
- Username: `airflow` (hoặc theo `.env`)
- Password: `airflow` (hoặc theo `.env`)

## DAG có sẵn

### `binance_get_latest_trades`

**Mô tả**: Lấy dữ liệu P2P trades từ 00:00 hôm nay đến hiện tại (Vietnam timezone UTC+7)

**Schedule**: Chạy mỗi 6 giờ (`0 */6 * * *`)

**Tasks**:
1. `fetch_latest_trades`: Gọi API Binance P2P để lấy latest trades

**Kết quả**:
- Log số lượng records đã fetch
- Push metadata vào XCom (trade_count, fetch_timestamp)

## Sử dụng

### Chạy DAG thủ công

1. Vào Airflow UI: http://localhost:8085
2. Tìm DAG `binance_get_latest_trades`
3. Bật DAG (toggle ON)
4. Click "Trigger DAG" để chạy ngay

### Xem logs

1. Click vào DAG run
2. Click vào task
3. Click "Log" để xem chi tiết

### Test DAG locally

```bash
# Exec vào container
docker exec -it c2c-airflow-webserver /bin/bash

# Test DAG
python /opt/airflow/dags/binance_get_latest_dag.py
```

## Commands hữu ích

### Stop Airflow

```bash
docker-compose -f docker-compose-airflow.yml down
```

### Xem logs

```bash
# Webserver logs
docker logs c2c-airflow-webserver

# Scheduler logs
docker logs c2c-airflow-scheduler

# Follow logs
docker logs -f c2c-airflow-scheduler
```

### Restart services

```bash
docker-compose -f docker-compose-airflow.yml restart
```

### Xóa database và reset (cẩn thận!)

```bash
docker-compose -f docker-compose-airflow.yml down -v
```

### Access bash trong container

```bash
docker exec -it c2c-airflow-webserver bash
```

### Run Airflow commands

```bash
# List DAGs
docker exec c2c-airflow-webserver airflow dags list

# Test task
docker exec c2c-airflow-webserver airflow tasks test binance_get_latest_trades fetch_latest_trades 2025-01-01

# Trigger DAG
docker exec c2c-airflow-webserver airflow dags trigger binance_get_latest_trades
```

## Troubleshooting

### Container không start được

Kiểm tra logs:
```bash
docker logs c2c-airflow-init
docker logs c2c-airflow-webserver
```

### Permission errors

Trên Linux/Mac:
```bash
sudo chown -R $(id -u):$(id -g) logs/ dags/ plugins/
```

### DAG không xuất hiện trong UI

1. Kiểm tra syntax DAG:
```bash
docker exec c2c-airflow-webserver python /opt/airflow/dags/binance_get_latest_dag.py
```

2. Restart scheduler:
```bash
docker restart c2c-airflow-scheduler
```

### Import errors

Kiểm tra dependencies đã install đủ trong Dockerfile:
```bash
docker exec c2c-airflow-webserver pip list
```

## Mở rộng

### Thêm DAG mới

1. Tạo file Python trong `dags/`
2. Import các modules cần thiết
3. Define DAG với `with DAG(...) as dag:`
4. Define tasks với Operators
5. DAG sẽ tự động load trong vài giây

### Thêm Python dependencies

Sửa `requirements.txt` và rebuild image:
```bash
docker-compose -f docker-compose-airflow.yml build
docker-compose -f docker-compose-airflow.yml up -d
```

### Kết nối với MinIO/S3

Xem code trong DAG để lấy credentials từ environment variables:
```python
minio_endpoint = os.getenv('MINIO_ENDPOINT')
access_key = os.getenv('AWS_ACCESS_KEY_ID')
secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
```

## Best Practices

1. **Idempotency**: Đảm bảo tasks có thể chạy lại nhiều lần mà không gây lỗi
2. **Error Handling**: Dùng try-except và log errors đầy đủ
3. **Testing**: Test DAG trước khi deploy
4. **Monitoring**: Theo dõi logs và alerts
5. **Security**: Không commit credentials vào Git

## Tham khảo

- [Airflow Documentation](https://airflow.apache.org/docs/)
- [Airflow Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)

