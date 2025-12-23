"""
C2C Ingestion Pipeline DAG (UPSERT ENABLED)
- Fetch data from Binance C2C API
- UPSERT into PostgreSQL
- Used to test CDC → Kafka → Flink → Telegram
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret

NAMESPACE = "batch-processing"
IMAGE = "asia-southeast1-docker.pkg.dev/binance-c2c-deployment/docker-images/ingestion-app:latest"

# ============================================================
# Binance API Secrets
# ============================================================

api_key_secret = Secret(
    deploy_type='env',
    deploy_target='BINANCE_API_KEY',
    secret='airflow-producer-secret',
    key='API_KEY'
)

api_secret_secret = Secret(
    deploy_type='env',
    deploy_target='BINANCE_API_SECRET',
    secret='airflow-producer-secret',
    key='API_SECRET'
)

# ============================================================
# PostgreSQL Secrets (UPSERT ENABLED)
# ============================================================

db_password_secret = Secret(
    deploy_type='env',
    deploy_target='DB_PASSWORD',
    secret='airflow-postgres-secret',
    key='POSTGRES_PASSWORD'
)

# ============================================================
# Default arguments
# ============================================================

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

# ============================================================
# DAG definition
# ============================================================

with DAG(
    dag_id='streaming_ingestion',
    default_args=default_args,
    description='C2C ingestion with DB UPSERT (CDC test)',
    schedule=timedelta(minutes=5),
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['c2c', 'ingestion', 'upsert', 'cdc']
) as dag:

    c2c_ingestion_job = KubernetesPodOperator(
        task_id='streaming_ingestion',

        name='streaming_ingestion',
        namespace=NAMESPACE,

        # ingestion image (shared codebase)
        image=IMAGE,

        # ingestion entrypoint
        cmds=["python3", "/app/c2c_ingestion.py"],

        # ENV controls behavior
        env_vars={
            "FETCH_MODE": "latest",
            "ENABLE_DB_UPSERT": "true",
            "SLEEP_INTERVAL": "0.5",
            # DB connection (NO secret hardcode)
            "DB_HOST": "airflow-postgresql.batch-processing.svc.cluster.local",
            "DB_PORT": "5432",
            "DB_NAME": "c2c_trade",
            "DB_USER": "postgres",
        },

        secrets=[
            api_key_secret,
            api_secret_secret,
            db_password_secret,
        ],

        startup_timeout_seconds=300,
        image_pull_policy='Always',
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,
        kubernetes_conn_id=None,
    )