import logging
import os
from typing import Optional

from minio import Minio
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    from_unixtime,
    from_utc_timestamp,
    to_date,
    year,
    month,
    dayofmonth,
    current_date
)
from pyspark.sql.types import LongType

from spark_utils import (
    check_minio_connectivity,
    create_spark_session,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bronze_job")
logger.info("Starting Bronze Job (Production Optimized)...")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
ACCESS_KEY = os.getenv("MINIO_ROOT_USER", os.getenv("AWS_ACCESS_KEY_ID", ""))
SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
BRONZE_PATH = os.getenv("BRONZE_PATH", "s3a://bronze/c2c_trades/")


# =====================================================================
# 1. SAFE TRADE DATE EXTRACTION
# =====================================================================

def add_trade_date(df: DataFrame) -> DataFrame:
    """
    Add `trade_date` + year/month/day partitions.
    Handles timestamp columns correctly and ensures proper timezone.
    """

    # If already exists (e.g., re-ingest)
    if "trade_date" in df.columns:
        logger.info("trade_date already exists → only generating partitions.")
        return (
            df.withColumn("year", year("trade_date"))
              .withColumn("month", month("trade_date"))
              .withColumn("day", dayofmonth("trade_date"))
        )

    # Detect timestamp column
    timestamp_col = None
    for c in ["createTime", "create_time_ms", "create_time"]:
        if c in df.columns:
            timestamp_col = c
            break

    if not timestamp_col:
        raise Exception(
            "❌ No timestamp column found (createTime/create_time_ms/create_time).\n"
            "Bronze ingest cannot determine trade_date."
        )

    logger.info(f"Using timestamp column: {timestamp_col}")

    # Force timestamp column to long(epoch ms)
    df = df.withColumn(timestamp_col, col(timestamp_col).cast(LongType()))

    # Convert epoch(ms) → timestamp(UTC) → timestamp(Asia/Ho_Chi_Minh)
    df = df.withColumn(
        "create_ts_utc",
        from_unixtime(col(timestamp_col) / 1000)  # epoch → string timestamp UTC
    ).withColumn(
        "create_ts",
        from_utc_timestamp("create_ts_utc", "Asia/Ho_Chi_Minh")
    )

    # Create trade_date + partitions
    df = (
        df.withColumn("trade_date", to_date("create_ts"))
          .withColumn("year", year("trade_date"))
          .withColumn("month", month("trade_date"))
          .withColumn("day", dayofmonth("trade_date"))
          .drop("create_ts_utc")    # cleanup
          .drop("create_ts")
    )

    return df


# =====================================================================
# 2. DUPLICATE PROTECTION
# =====================================================================

def deduplicate(df: DataFrame) -> DataFrame:
    """
    Drop duplicates by orderNumber (if exists).
    This protects Bronze from re-ingestion duplication.
    """
    if "orderNumber" in df.columns:
        before = df.count()
        df = df.dropDuplicates(["orderNumber"])
        after = df.count()
        logger.info(f"Deduplication: {before} → {after} rows after removing duplicates.")
    else:
        logger.warning("No orderNumber column found → skipping deduplication.")

    return df


# =====================================================================
# 3. MAIN PROCESS
# =====================================================================

def main():
    try:
        spark = create_spark_session()
        spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

        check_minio_connectivity(MINIO_ENDPOINT, ACCESS_KEY, SECRET_KEY, BRONZE_PATH)

        input_path = os.getenv("INPUT_PATH", "/shared_volume/c2c/latest/*.parquet")
        logger.info(f"Reading input data from: {input_path}")

        df = (
            spark.read
                .option("mergeSchema", "false")
                .parquet(input_path)
        )

        logger.info("Schema loaded:")
        df.printSchema()

        # Extract trade_date safely
        df = add_trade_date(df)

        # Protect Bronze from duplicates
        df = deduplicate(df)

        # Reduce small files → make Silver faster
        df = df.coalesce(4)

        # Final sanity check
        null_partitions = df.filter(
            col("year").isNull() | col("month").isNull() | col("day").isNull()
        ).count()

        if null_partitions > 0:
            raise Exception(f"❌ Found {null_partitions} rows with NULL partitions (year/month/day).")

        # Write to Delta Lake
        logger.info(f"Writing to Bronze Delta → {BRONZE_PATH}")

        (
            df.write.format("delta")
              .mode("append")
              .partitionBy("year", "month", "day")
              .save(BRONZE_PATH)
        )

        logger.info("✅ Bronze write completed successfully!")

    except Exception as e:
        logger.exception(f"❌ Bronze Job Failed: {e}")
        raise
    finally:
        if "spark" in locals():
            spark.stop()
        logger.info("Spark session stopped.")


if __name__ == "__main__":
    main()
