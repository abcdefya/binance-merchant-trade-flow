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

local_tz = pendulum.timezone("Asia/Ho_Chi_Minh")


def fetch_yesterday_trades():
    try:
        api_key = os.getenv("API_KEY", "")
        api_secret = os.getenv("API_SECRET", "")
        if not api_key or not api_secret:
            raise ValueError("API_KEY/API_SECRET are missing; set them in environment")

        configuration_rest_api = ConfigurationRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            base_path=os.getenv("BASE_PATH", C2C_REST_API_PROD_URL),
        )
        client = C2CExtended(configuration_rest_api)
        data = client.get_latest()

        # Write parquet to shared volume
        base_dir = "/shared_volume/c2c/latest"
        ensure_directory(base_dir)
        # Use yesterday's date in filename for clarity
        yday = pendulum.now(local_tz).subtract(days=1).to_date_string().replace("-", "")
        output_path = os.path.join(base_dir, f"c2c_trades_{yday}.parquet")
        result = write_to_parquet(data, output_path)
        if not result or not os.path.exists(output_path):
            raise RuntimeError(f"Failed to write parquet to {output_path}")
        logging.info(f"Saved parquet to {output_path}")
    except Exception as exc:
        logging.exception(f"Failed to fetch yesterday trades: {exc}")
        raise


with DAG(
    dag_id="binance_get_daily_c2c",
    description="Fetch Binance C2C yesterday trades daily and trigger Spark ELT",
    schedule="0 0 * * *",  # midnight daily
    start_date=pendulum.datetime(2025, 10, 1, tz=local_tz),
    catchup=False,
    tags=["binance", "c2c", "daily"],
) as dag:
    fetch_daily = PythonOperator(
        task_id="fetch_yesterday_c2c",
        python_callable=fetch_yesterday_trades,
        retries=2,
        retry_delay=pendulum.duration(minutes=1),
    )

    bronze_task = DockerOperator(
        task_id="bronze_jobs",
        image="spark-elt:latest",
        auto_remove="success",
        api_version="auto",
        command=None,
        working_dir="/app",
        mount_tmp_dir=False,
        docker_url=os.getenv("DOCKER_URL", "tcp://host.docker.internal:2375"),
        network_mode=os.getenv("LAKEHOUSE_NETWORK", "binance-merchant-trading-flow_default"),
        environment={
            "INPUT_PATH": "/shared_volume/c2c/latest/*.parquet",
            # Pass storage configuration through to the container
            "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
            "MINIO_ROOT_USER": os.getenv("MINIO_ROOT_USER", os.getenv("MINIO_ROOT_USER", "")),
            "MINIO_ROOT_PASSWORD": os.getenv("MINIO_ROOT_PASSWORD", os.getenv("MINIO_ROOT_PASSWORD", "")),
            "BRONZE_PATH": os.getenv("BRONZE_PATH", "s3a://bronze/c2c_trades/"),
            "SILVER_PATH": os.getenv("SILVER_PATH", "s3a://silver/c2c_trades/"),
            "DATE_FILTER": os.getenv("DATE_FILTER", None),
        },
        mounts=[
            Mount(source="shared-volume", target="/shared_volume", type="volume", read_only=False),
        ],
    )

    silver_task = DockerOperator(
        task_id="silver_jobs",
        image="spark-elt:latest",
        auto_remove="success",
        api_version="auto",
        command=None,
        working_dir="/app",
        mount_tmp_dir=False,
        docker_url=os.getenv("DOCKER_URL", "tcp://host.docker.internal:2375"),
        network_mode=os.getenv("LAKEHOUSE_NETWORK", "binance-merchant-trading-flow_default"),
        environment={
            "JOB_SCRIPT": "silver_jobs.py",
            "INPUT_PATH": "/shared_volume/c2c/latest/*.parquet",
            "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
            "MINIO_ROOT_USER": os.getenv("MINIO_ROOT_USER", os.getenv("MINIO_ROOT_USER", "")),
            "MINIO_ROOT_PASSWORD": os.getenv("MINIO_ROOT_PASSWORD", os.getenv("MINIO_ROOT_PASSWORD", "")),
            "BRONZE_PATH": os.getenv("BRONZE_PATH", "s3a://bronze/c2c_trades/"),
            "SILVER_PATH": os.getenv("SILVER_PATH", "s3a://silver/c2c_trades/"),
            "DATE_FILTER": os.getenv("DATE_FILTER", None),
        },
        mounts=[
            Mount(source="shared-volume", target="/shared_volume", type="volume", read_only=False),
        ],
    )

    gold_task = DockerOperator(
        task_id="gold_jobs",
        image="spark-elt:latest",
        auto_remove="success",
        api_version="auto",
        command=None,
        working_dir="/app",
        mount_tmp_dir=False,
        docker_url=os.getenv("DOCKER_URL", "tcp://host.docker.internal:2375"),
        network_mode=os.getenv("LAKEHOUSE_NETWORK", "binance-merchant-trading-flow_default"),
        environment={
            "JOB_SCRIPT": "gold_jobs.py",
            "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
            "MINIO_ROOT_USER": os.getenv("MINIO_ROOT_USER", os.getenv("MINIO_ROOT_USER", "")),
            "MINIO_ROOT_PASSWORD": os.getenv("MINIO_ROOT_PASSWORD", os.getenv("MINIO_ROOT_PASSWORD", "")),
            "SILVER_PATH": os.getenv("SILVER_PATH", "s3a://silver/c2c_trades/"),
            "GOLD_PATH": os.getenv("GOLD_PATH", "s3a://gold/"),
            "DATE_FILTER": os.getenv("DATE_FILTER", None),
        },
        mounts=[
            Mount(source="shared-volume", target="/shared_volume", type="volume", read_only=False),
        ],
    )

    cleanup_shared = BashOperator(
        task_id="cleanup_shared_volume",
        bash_command="rm -rf /shared_volume/c2c/* || true",
    )

    fetch_daily >> bronze_task >> silver_task >> gold_task >> cleanup_shared
