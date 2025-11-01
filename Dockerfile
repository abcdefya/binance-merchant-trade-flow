# Dockerfile
FROM apache/airflow:3.1.0-python3.10

# (Tuỳ chọn) cài thêm OS packages nếu cần
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    nano vim less \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY src/ src/
# COPY jars/ jars/
COPY configs/ configs/
COPY scripts/ scripts/
# COPY streaming/ streaming/
COPY kafka_connect/ kafka_connect/
COPY dags/ dags/
# COPY .env .env
# Cài python packages (nếu có)
USER airflow

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy sẵn thư mục dags (vẫn sẽ mount bằng volumes để sửa live)
COPY dags /opt/airflow/dags
