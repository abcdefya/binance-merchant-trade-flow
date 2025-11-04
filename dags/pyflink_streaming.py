import os
import sys
import logging
from datetime import datetime
import pendulum
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

from binance_sdk_c2c.c2c import ConfigurationRestAPI, C2C_REST_API_PROD_URL

# Ensure project root and src are importable
PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/opt/airflow")
SRC_DIR = os.getenv("SRC_DIR", os.path.join(PROJECT_ROOT, "src"))
for p in [PROJECT_ROOT, SRC_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.components.data_ingestion import C2CExtended
from src.utils.utils import ensure_directory, write_to_parquet
from src.utils.postgresql_client import create_client_from_env

local_tz = pendulum.timezone("Asia/Ho_Chi_Minh")

def get_latest_and_insert_postgres():
    """Fetch latest C2C trades and insert/update to PostgreSQL."""
    try:
        # Initialize Binance C2C API client
        api_key = os.getenv("API_KEY", "")
        api_secret = os.getenv("API_SECRET", "")
        if not api_key or not api_secret:
            raise ValueError("API_KEY/API_SECRET are missing; set them in environment")

        configuration_rest_api = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=os.getenv("BASE_PATH", C2C_REST_API_PROD_URL),
        )
        c2c_client = C2CExtended(configuration_rest_api)
        
        # Fetch latest trades from today
        logging.info("Fetching latest C2C trades from Binance API...")
        data = c2c_client.get_latest_by_week()
        logging.info(f"Fetched {len(data)} trade records")
        
        # Initialize PostgreSQL client from environment variables
        pg_client = create_client_from_env()
        
        # Insert/Update data to PostgreSQL
        logging.info("Inserting/Updating trades to PostgreSQL...")
        summary = pg_client.update_order_status(data, table="c2c.trades")
        logging.info(f"PostgreSQL operation summary: {summary}")
        
        # Optionally write to parquet for backup/streaming
        base_dir = "/shared_volume/c2c/streaming"
        ensure_directory(base_dir)
        timestamp = pendulum.now(local_tz).format('YYYYMMDDHHmmss')
        output_path = os.path.join(base_dir, f"c2c_trades_{timestamp}.parquet")
        result = write_to_parquet(data, output_path)
        if result and os.path.exists(output_path):
            logging.info(f"Backup parquet saved to {output_path}")
        
        return summary
        
    except Exception as exc:
        logging.exception(f"Failed to fetch and insert latest trades: {exc}")
        raise

# Define the streaming DAG
with DAG(
    dag_id="binance_c2c_streaming",
    description="Real-time streaming pipeline for Binance C2C trades using PyFlink",
    schedule="*/5 * * * *",  # Run every 5 minutes to fetch fresh data
    start_date=pendulum.datetime(2025, 10, 27, tz=local_tz),
    catchup=False,
    tags=["binance", "c2c", "streaming", "flink"],
    max_active_runs=1,  # Prevent overlapping runs
) as dag:
    
    # Task 1: Fetch latest trades from Binance API and insert to PostgreSQL
    fetch_and_insert_task = PythonOperator(
        task_id="fetch_latest_and_insert_postgres",
        python_callable=get_latest_and_insert_postgres,
        retries=3,
        retry_delay=pendulum.duration(seconds=30),
    )
    
    # ========================================================================
    # NOTE: Flink streaming task is now a standalone 24/7 service in 
    # docker-compose-lakehouse.yml (service: flink-consumer)
    # 
    # The DAG only needs to:
    #   1. Fetch data from Binance API
    #   2. Insert to PostgreSQL
    #   3. Debezium CDC will capture changes → Kafka
    #   4. Flink service will consume Kafka 24/7
    # ========================================================================
    
    # # Task 2: Run Flink streaming job to process data from Kafka
    # # (REMOVED - now running as standalone service)
    # flink_streaming_task = DockerOperator(
    #     task_id="flink_streaming_processor",
    #     image="flink-streaming:latest",
    #     auto_remove="success",
    #     api_version="auto",
    #     command=[
    #         "python", "/app/flink_streaming.py"
    #     ],
    #     working_dir="/app",
    #     mount_tmp_dir=False,
    #     docker_url=os.getenv("DOCKER_URL", "tcp://host.docker.internal:2375"),
    #     network_mode=os.getenv("LAKEHOUSE_NETWORK", "binance-merchant-trading-flow_default"),
    #     environment={
    #         "KAFKA_BOOTSTRAP_SERVERS": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
    #         "KAFKA_TOPIC": os.getenv("KAFKA_TOPIC", "binance.c2c.trades"),
    #         "KAFKA_GROUP_ID": os.getenv("KAFKA_GROUP_ID", "flink-streaming-consumer"),
    #         "POSTGRES_HOST": os.getenv("POSTGRES_HOST", "timescaledb"),
    #         "POSTGRES_PORT": os.getenv("POSTGRES_PORT", "5432"),
    #         "POSTGRES_DB": os.getenv("POSTGRES_DB", "trading"),
    #         "POSTGRES_USER": os.getenv("POSTGRES_USER", "postgres"),
    #         "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", "postgres"),
    #     },
    #     retries=2,
    #     retry_delay=pendulum.duration(minutes=1),
    # )
    
    # # Task 3: Health check and monitoring (optional)
    # health_check = BashOperator(
    #     task_id="streaming_health_check",
    #     bash_command="""
    #     echo "Checking Flink streaming job health..."
    #     echo "Timestamp: $(date)"
    #     echo "Data ingested successfully"
    #     """,
    # )
    
    # Define task dependencies
    # DAG now only runs data ingestion - streaming is handled by standalone service
    # fetch_and_insert_task >> flink_streaming_task  # OLD
    fetch_and_insert_task  # NEW: single task