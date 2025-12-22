from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret
from kubernetes.client import models as k8s


# =========================================================
# NAMESPACE
# =========================================================
NAMESPACE = "batch-processing"
IMAGE = "asia-southeast1-docker.pkg.dev/binance-c2c-deployment/docker-images/batch-app:latest"
# =========================================================
# BINANCE API SECRETS
# =========================================================
api_key_secret = Secret(
    deploy_type="env",
    deploy_target="BINANCE_API_KEY",
    secret="airflow-producer-secret",
    key="API_KEY",
)

api_secret_secret = Secret(
    deploy_type="env",
    deploy_target="BINANCE_API_SECRET",
    secret="airflow-producer-secret",
    key="API_SECRET",
)

# =========================================================
# MINIO SECRETS
# =========================================================
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

# =========================================================
# DEFAULT ARGS
# =========================================================
default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

# =========================================================
# DAG
# =========================================================
with DAG(
    dag_id="daily_batch_processing",
    default_args=default_args,
    description="TEST DAG: Binance C2C ingestion → bronze landing → bronze delta",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["c2c", "ingestion", "bronze", "test"],
) as dag:

    # TASK 1: INGESTION → LANDING
    data_ingestion = KubernetesPodOperator(
        task_id="c2c_ingestion",
        name="c2c-ingestion",
        namespace=NAMESPACE,

        image="asia-southeast1-docker.pkg.dev/binance-c2c-deployment/docker-images/ingestion-app:latest",
        cmds=["python3", "/app/c2c_ingestion.py"],

        env_vars={
            "FETCH_MODE": "latest_month",
            "ENABLE_MINIO_WRITE": "true",
            "ENABLE_DB_UPSERT": "false",
            # MinIO landing config
            "MINIO_ENDPOINT": "http://minio.storage.svc.cluster.local:80",
            "MINIO_BUCKET": "bronze",
            "MINIO_PREFIX": "c2c_trades/_landing",
        },

        secrets=[
            api_key_secret,
            api_secret_secret,
            minio_access_key,
            minio_secret_key,
        ],

        image_pull_policy="Always",
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,
        kubernetes_conn_id=None,
    )

    # Task 2: Bronze jobs
    bronze_jobs = KubernetesPodOperator(
        task_id="c2c_bronze_job",
        name="c2c-bronze-job",
        namespace=NAMESPACE,

        image="asia-southeast1-docker.pkg.dev/binance-c2c-deployment/docker-images/batch-app:latest",
        cmds=["python3", "etl_jobs/bronze_job.py"],

        env_vars={
            # append only
            "BRONZE_WRITE_MODE": "append",

            # cleanup landing after success
            "BRONZE_CLEANUP_MODE": "delete",
        },

        image_pull_policy="Always",
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,
        kubernetes_conn_id=None,
    )

    # Task 3: Silver jobs
    silver_jobs = KubernetesPodOperator(
        task_id='silver_transformation',
        name='silver-transformation',
        namespace=NAMESPACE,
        image=IMAGE,
        cmds=["python3", "etl_jobs/silver_job.py"],
        # env_vars={"DATE_FILTER": "yesterday"},  # Uncomment for daily incremental mode
        image_pull_policy='Always',
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,
        kubernetes_conn_id=None,
    )

    # Task 4: Gold jobs
    gold_jobs = KubernetesPodOperator(
        task_id='gold_transformation',
        name='gold-transformation-v1',
        namespace=NAMESPACE,
        image=IMAGE,
        cmds=["python3", "etl_jobs/gold_job_v1.py"],
        env_vars={
            "GCS_BUCKET": "gold-c2c-bucket",
            "GCS_PREFIX": "gold_v1_backup",  # Different prefix to separate V0 and V1
            "GCS_WORKERS": "16",
            "GCS_USE_THREADS": "true",
            "GOOGLE_APPLICATION_CREDENTIALS": "/secrets/gcs-auth.json"
        },
        # Mount GCS credentials from Kubernetes Secret
        volumes=[
            k8s.V1Volume(
                name='gcs-credentials',
                secret=k8s.V1SecretVolumeSource(secret_name='gcs-credentials')
            )
        ],
        volume_mounts=[
            k8s.V1VolumeMount(
                name='gcs-credentials',
                mount_path='/secrets',
                read_only=True
            )
        ],
        image_pull_policy='Always',
        is_delete_operator_pod=True,
        get_logs=True,
        in_cluster=True,
        kubernetes_conn_id=None,
    )

    data_ingestion >> bronze_jobs >> silver_jobs >> gold_jobs
