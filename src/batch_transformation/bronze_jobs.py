import logging
import os
from typing import Optional

from minio import Minio
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, current_date, from_unixtime, to_date

from spark_utils import (
    check_minio_connectivity,
    create_spark_session,
)

# --------------------- CONFIG & LOGGING ---------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Starting Spark session...")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
ACCESS_KEY = os.getenv("MINIO_ROOT_USER", os.getenv("AWS_ACCESS_KEY_ID", ""))
SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
BRONZE_PATH = os.getenv("BRONZE_PATH", "s3a://bronze/c2c_trades/")
SILVER_PATH = os.getenv("SILVER_PATH", "s3a://silver/c2c_trades/")

logger.info("MINIO_ENDPOINT: %s", MINIO_ENDPOINT)
logger.info("BRONZE_PATH: %s", BRONZE_PATH)
logger.info("SILVER_PATH: %s", SILVER_PATH)


def add_trade_date(df: DataFrame) -> DataFrame:
    """Add 'trade_date' column based on available timestamp columns."""
    if "trade_date" in df.columns:
        return df

    timestamp_col: Optional[str] = None
    if "createTime" in df.columns:
        timestamp_col = "createTime"
    elif "create_time_ms" in df.columns:
        timestamp_col = "create_time_ms"
    elif "create_time" in df.columns:
        timestamp_col = "create_time"
    
    if timestamp_col:
        # Convert from ms (assuming UTC) to timestamp with UTC+7 adjustment, then to date
        df = (
            df.withColumn(
                "createTime_ts",
                from_unixtime((col(timestamp_col) / 1000) + 7 * 3600),
            ).withColumn("trade_date", to_date(col("createTime_ts")))
        )
    else:
        logger.warning(
            "No create time column found, using current_date for partitioning"
        )
        df = df.withColumn("trade_date", current_date())
    
    return df


def main() -> None:
    """Main entry point for the script."""
    try:
        spark = create_spark_session()
        spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
        logger.info("SparkSession created with MinIO and Delta config.")

        check_minio_connectivity(MINIO_ENDPOINT, ACCESS_KEY, SECRET_KEY, BRONZE_PATH)
        logger.info("MinIO connectivity check completed.")

        input_path = os.getenv("INPUT_PATH", "/shared_volume/c2c/latest/*.parquet")
        logger.info("Reading input data from: %s", input_path)

        df = spark.read.parquet(input_path)
        logger.info("Schema:")
        df.printSchema()

        df = add_trade_date(df)

        # Show sample using available columns
        sample_cols = [
            c for c in ("createTime", "create_time", "trade_date") if c in df.columns
        ]
        if sample_cols:
            df.select(*sample_cols).show(5, truncate=False)

        count = df.count()
        logger.info("Input row count: %s", count)

        logger.info("Writing to Delta Lake (append mode) → %s", BRONZE_PATH)
        (
            df.write.format("delta")
            .mode("append")
            .partitionBy("trade_date")
            .save(BRONZE_PATH)
        )
        logger.info("Write completed successfully.")

    except Exception as e:
        logger.exception("Error during execution: %s", e)
        raise
    finally:
        if "spark" in locals():
            spark.stop()
        logger.info("Spark session stopped.")


if __name__ == "__main__":
    main()