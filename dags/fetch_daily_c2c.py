import os
import sys
import logging
from datetime import datetime
import pendulum
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator

from binance_sdk_c2c.c2c import ConfigurationRestAPI, C2C_REST_API_PROD_URL

# Ensure project root and src are importable
PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/opt/airflow")
SRC_DIR = os.getenv("SRC_DIR", os.path.join(PROJECT_ROOT, "src"))
for p in [PROJECT_ROOT, SRC_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.components.data_ingestion import C2CExtended

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
        data = client.get_yesterday()
        logging.info(f"Finished fetching yesterday's trades, total {len(data)} records")
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

    process_with_spark = DockerOperator(
        task_id="run_spark_elt",
        image="spark-elt:latest",  # tên image Spark bạn đã build
        auto_remove="success",
        api_version="auto",
        command=None,
        working_dir="/app",
        mount_tmp_dir=False,
        docker_url=os.getenv("DOCKER_URL", "tcp://host.docker.internal:2375"),
        network_mode="bridge",
        environment={
            "MINIO_ENDPOINT": "http://minio:9000",
            "AWS_ACCESS_KEY_ID": "minioadmin",
            "AWS_SECRET_ACCESS_KEY": "minioadmin",
            "BRONZE_PATH": "s3a://bronze/c2c_trades/",
            "SILVER_PATH": "s3a://silver/c2c_trades/",
        },
    )

    fetch_daily >> process_with_spark
