from urllib.parse import urlparse
from typing import Tuple, Optional
from minio import Minio
from pyspark.sql import SparkSession
import logging
import os

# --------------------- MINIO CONNECTIVITY CHECK ---------------------
def _normalize_minio_endpoint(endpoint: str) -> Tuple[str, bool]:
    parsed = urlparse(endpoint)
    if parsed.scheme in ("http", "https"):
        return parsed.netloc, parsed.scheme == "https"
    return endpoint.replace("http://", "").replace("https://", ""), False

def _parse_s3a_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("s3a://"):
        raise ValueError(f"Unsupported path scheme for BRONZE_PATH: {uri}")
    remainder = uri[len("s3a://"):]
    parts = remainder.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return bucket, prefix

def check_minio_connectivity(MINIO_ENDPOINT: str, ACCESS_KEY: str, SECRET_KEY: str, BUCKET_PATH: str) -> None:
    host, secure = _normalize_minio_endpoint(MINIO_ENDPOINT)
    bucket, _ = _parse_s3a_uri(BUCKET_PATH)
    client = Minio(host, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=secure)
    try:
        exists = client.bucket_exists(bucket)
        if exists:
            logging.info("✅ MinIO connectivity OK. Bucket '%s' is accessible", bucket)
        else:
            logging.warning("⚠️ MinIO connectivity OK but bucket '%s' does not exist", bucket)
    except Exception as exc:
        logging.exception("❌ MinIO connectivity check failed: %s", exc)
        raise

def create_spark_session(
    MINIO_ENDPOINT: Optional[str] = None,
    ACCESS_KEY: Optional[str] = None,
    SECRET_KEY: Optional[str] = None,
) -> SparkSession:
    endpoint = MINIO_ENDPOINT or os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    access = ACCESS_KEY or os.getenv("MINIO_ROOT_USER", os.getenv("AWS_ACCESS_KEY_ID", ""))
    secret = SECRET_KEY or os.getenv("MINIO_ROOT_PASSWORD", os.getenv("AWS_SECRET_ACCESS_KEY", ""))

    spark = (
        SparkSession.builder
        .appName("bronze-transformation-jobs")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        # add delta core JAR (⚠️ adjust version for your Spark)
        .config("spark.jars.packages", "io.delta:delta-core_2.12:2.4.0")
        .config("spark.hadoop.fs.s3a.endpoint", endpoint)
        .config("spark.hadoop.fs.s3a.access.key", access)
        .config("spark.hadoop.fs.s3a.secret.key", secret)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.delta.logStore.class", "org.apache.spark.sql.delta.storage.S3SingleDriverLogStore")
        # Memory configurations to prevent OOM
        .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "2g"))
        .config("spark.executor.memory", os.getenv("SPARK_EXECUTOR_MEMORY", "2g"))
        .config("spark.driver.maxResultSize", "1g")
        .config("spark.sql.shuffle.partitions", "200")
        # Optimize for window operations
        .config("spark.sql.windowExec.buffer.spill.threshold", "10000")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .getOrCreate()
    )
    return spark