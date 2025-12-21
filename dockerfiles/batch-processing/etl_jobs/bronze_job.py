import os
import sys
import logging

sys.path.append("/app")

from pyspark.sql.functions import (
    col,
    year,
    month,
    dayofmonth,
    from_unixtime,
    from_utc_timestamp,
    to_date,
)
from pyspark.sql.types import LongType
from common.utils import get_spark

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bronze-job")

# =========================================================
# PATH CONFIG 
# =========================================================
LANDING_PATH = "s3a://bronze/c2c_trades/_landing"
BRONZE_PATH = "s3a://bronze/c2c_trades/bronze_delta"
APP_NAME = "C2CBronzeJob"


def main():
    # =====================================================
    # MODE FLAGS 
    # =====================================================
    write_mode = os.getenv("BRONZE_WRITE_MODE", "append").lower()
    cleanup_mode = os.getenv("BRONZE_CLEANUP_MODE", "none").lower()

    logger.info(f"BRONZE_WRITE_MODE={write_mode}")
    logger.info(f"BRONZE_CLEANUP_MODE={cleanup_mode}")

    # =====================================================
    # INIT SPARK 
    # =====================================================
    spark = get_spark(APP_NAME)

    # =====================================================
    # 1. READ LANDING
    # =====================================================
    logger.info("🔵 Reading landing data...")
    df = spark.read.parquet(f"{LANDING_PATH}/batch_id=*")

    if df.rdd.isEmpty():
        logger.warning("⚠️ No data found in landing → exit")
        spark.stop()
        return

    # =====================================================
    # 2. TRANSFORMATION 
    # =====================================================
    logger.info("🟡 Transforming bronze data (TZ=Asia/Ho_Chi_Minh)...")

    df = df.withColumn(
        "create_time",
        col("create_time").cast(LongType())
    )

    df = (
        df.withColumn(
            "create_ts_utc",
            from_unixtime(col("create_time") / 1000)
        )
        .withColumn(
            "create_ts",
            from_utc_timestamp("create_ts_utc", "Asia/Ho_Chi_Minh")
        )
        .withColumn(
            "trade_date",
            to_date("create_ts")
        )
        .withColumn("year", year("trade_date"))
        .withColumn("month", month("trade_date"))
        .withColumn("day", dayofmonth("trade_date"))
        .drop("create_ts_utc", "create_ts")
    )

    # Deduplicate theo business key 
    df = df.dropDuplicates(["order_number"])

    # =====================================================
    # 3. WRITE BRONZE (APPEND ONLY)
    # =====================================================
    logger.info("🟢 Writing Bronze Delta (APPEND ONLY)...")

    if write_mode != "append":
        logger.warning(
            "⚠️ Non-append mode requested but NOT supported. "
            "Forcing append."
        )

    (
        df.write
        .format("delta")
        .mode("append")   # 
        .partitionBy("year", "month", "day")
        .save(BRONZE_PATH)
    )

    logger.info("✅ Bronze write completed")

    # =====================================================
    # 4. CLEANUP LANDING 
    # =====================================================
    fs = spark._jvm.org.apache.hadoop.fs.FileSystem.get(
        spark._jsc.hadoopConfiguration()
    )
    landing_path = spark._jvm.org.apache.hadoop.fs.Path(LANDING_PATH)

    if cleanup_mode == "delete":
        if fs.exists(landing_path):
            fs.delete(landing_path, True)
            logger.info("🧹 Landing deleted")

    elif cleanup_mode == "processed":
        processed_path = spark._jvm.org.apache.hadoop.fs.Path(
            LANDING_PATH.replace("_landing", "_processed")
        )
        if fs.exists(landing_path):
            fs.rename(landing_path, processed_path)
            logger.info("📦 Landing moved to _processed")

    else:
        logger.info("ℹ️ Cleanup skipped (BRONZE_CLEANUP_MODE=none)")

    spark.stop()
    logger.info("🏁 Bronze job finished successfully")


if __name__ == "__main__":
    main()
