from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret

# Namespace Airflow đang chạy
NAMESPACE = "batch-processing"

# -------------------------
# MinIO secrets
# -------------------------
minio_access_key = Secret(
    deploy_type="env",
    deploy_target="MINIO_ACCESS_KEY",
    secret="minio-secret",
    key="access_key",
)

minio_secret_key = Secret(
    deploy_type="env",
    deploy_target="MINIO_SECRET_KEY",
    secret="minio-secret",
    key="secret_key",
)

api_key_secret = Secret('env', 
'BINANCE_API_KEY', 
'airflow-producer-secret', 
'API_KEY')
api_secret_secret = Secret('env', 
'BINANCE_API_SECRET', 
'airflow-producer-secret', 
'API_SECRET')


default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="c2c_ingestion_to_bronze_landing",
    default_args=default_args,
    description="Ingest Binance C2C data and write Parquet to MinIO bronze landing",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["c2c", "ingestion", "bronze", "minio"],
) as dag:

    ingestion_task = KubernetesPodOperator(
        task_id="c2c_ingestion",
        name="c2c-ingestion",
        namespace=NAMESPACE,

        # 👉 ingestion image của bạn
        image="asia-southeast1-docker.pkg.dev/binance-c2c-deployment/docker-images/ingestion-app:latest",

        cmds=["python3", "c2c_ingestion.py"],

        # -------------------------
        # ENV (non-secret)
        # -------------------------
        env_vars={
            "FETCH_MODE": "latest_month",

            # bật ghi MinIO
            "ENABLE_MINIO_WRITE": "true",

            # tắt DB nếu chỉ muốn landing
            "ENABLE_DB_UPSERT": "false",

            # MinIO endpoint + path
            "MINIO_ENDPOINT": "http://minio.storage.svc.cluster.local:80",
            "MINIO_BUCKET": "bronze",
            "MINIO_PREFIX": "c2c_trades/_landing",
        },

        # -------------------------
        # Secrets
        # -------------------------
        secrets=[
            minio_access_key,
            minio_secret_key,
        ],

        image_pull_policy="Always",
        get_logs=True,
        is_delete_operator_pod=True,

        in_cluster=True,
        kubernetes_conn_id=None,
    )
