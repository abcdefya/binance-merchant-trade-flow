import os
import logging
from pathlib import Path
from typing import List

import yaml
from delta.tables import DeltaTable

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import IntegerType
from pyspark.sql.functions import (
    col,
    when,
    lit,
    sum as spark_sum,
    avg,
    count,
    coalesce,
    year,
    month,
    dayofmonth,
    dayofweek,
    lower,
    current_timestamp,
    max as spark_max,
    date_sub,
    row_number,
)

from pyspark.sql.window import Window

from spark_utils import create_spark_session, check_minio_connectivity
from gcs_manager import GCSManager

# ========================= CONFIG & LOGGING ============================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gold_job_v3")
logger.info("Starting Gold Job V3 (siêu tối ưu)")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
ACCESS_KEY = os.getenv("MINIO_ROOT_USER", os.getenv("AWS_ACCESS_KEY_ID", ""))
SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", os.getenv("AWS_SECRET_ACCESS_KEY", ""))

SILVER_PATH = os.getenv("SILVER_PATH", "s3a://silver/c2c_trades/")
GOLD_LOCAL_PATH = os.getenv("GOLD_LOCAL_PATH", "/tmp/gold_delta")

CONFIG_PATH = os.getenv("CONFIG_PATH", "configs.yaml")

logger.info(f"SILVER_PATH={SILVER_PATH}")
logger.info(f"GOLD_LOCAL_PATH={GOLD_LOCAL_PATH}")
logger.info(f"CONFIG_PATH={CONFIG_PATH}")


# ========================= BACKUP CONFIG & GCS =========================

def load_backup_config(config_path: str = "configs.yaml") -> dict:
    """Đọc cấu hình gold_backup từ configs.yaml."""
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        logger.warning("Config file %s not found. GCS backup disabled.", config_path)
        return {"enabled": False}

    with cfg_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    backup_cfg = config.get("gold_backup", {})
    backup_cfg["enabled"] = backup_cfg.get("enabled", False)
    return backup_cfg


def backup_gold_to_gcs(gold_local_path: str, config_path: str = "configs.yaml") -> None:
    """
    Upload nguyên Gold layer (thư mục GOLD_LOCAL_PATH) lên GCS
    bằng GCSManager.upload_tree_parallel.
    """
    backup_cfg = load_backup_config(config_path)
    if not backup_cfg.get("enabled", False):
        logger.info("GCS backup is DISABLED in config.gold_backup.enabled. Skipping upload.")
        return

    gcs_manager = GCSManager(config_path=config_path)

    bucket = backup_cfg.get("backup_bucket", getattr(gcs_manager, "default_bucket", None))
    prefix = backup_cfg.get("backup_prefix", "gold_backup")
    workers = backup_cfg.get("workers", 16)
    use_threads = backup_cfg.get("use_threads", False)

    if not bucket:
        logger.error("No backup_bucket configured and no default_bucket on GCSManager.")
        return

    logger.info("Uploading Gold layer to GCS:")
    logger.info("  - Bucket: %s", bucket)
    logger.info("  - Prefix: %s", prefix)
    logger.info("  - Workers: %s", workers)
    logger.info("  - Mode: %s", "threads" if use_threads else "processes")

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket_obj = client.bucket(bucket)
        if not bucket_obj.exists():
            logger.info("Bucket %s does not exist. Creating...", bucket)
            gcs_manager.create_bucket(bucket_name=bucket)
            logger.info("Bucket %s created successfully.", bucket)
        else:
            logger.info("Bucket %s already exists.", bucket)
    except Exception as e:
        logger.error("Failed to check/create bucket %s: %s", bucket, e)
        return

    if not os.path.isdir(gold_local_path):
        logger.warning("Gold local path %s does not exist, nothing to upload.", gold_local_path)
        return

    gcs_manager.upload_tree_parallel(
        root_folder=gold_local_path,
        destination_prefix=prefix,
        bucket_name=bucket,
        workers=workers,
        use_threads=use_threads,
    )

    logger.info("Gold layer uploaded to gs://%s/%s/", bucket, prefix)


# ========================= DIMENSION BUILDERS ==========================

def build_dim_date(spark: SparkSession, df_silver_all: DataFrame, dim_date_path: str) -> DataFrame:
    """
    Dim date: dùng toàn bộ range trade_date trong Silver.
    (Đơn giản, ổn định, chi phí nhỏ.)
    """
    agg = df_silver_all.agg(
        spark_max("trade_date").alias("max_date"),
        spark_sum(when(col("trade_date").isNotNull(), lit(1)).otherwise(lit(0))).alias("non_null_count")
    ).collect()[0]

    max_date = agg["max_date"]
    if not max_date or agg["non_null_count"] == 0:
        logger.warning("No valid trade_date found in Silver for dim_date. Skipping.")
        return spark.createDataFrame([], "date_key INT, full_date DATE, day_of_week INT, month INT, quarter INT, year INT, is_weekend BOOLEAN, fiscal_year INT")

    df_dates = (
        df_silver_all
        .select("trade_date")
        .where(col("trade_date").isNotNull())
        .distinct()
        .withColumnRenamed("trade_date", "full_date")
    )

    df_dim_date = (
        df_dates
        .withColumn(
            "date_key",
            (year("full_date") * 10000 + month("full_date") * 100 + dayofmonth("full_date")).cast(IntegerType())
        )
        .withColumn("day_of_week", dayofweek("full_date"))
        .withColumn("month", month("full_date"))
        .withColumn("quarter", ((month("full_date") - 1) / 3 + 1).cast("int"))
        .withColumn("year", year("full_date"))
        .withColumn("is_weekend", when(col("day_of_week").isin(1, 7), lit(True)).otherwise(lit(False)))
        .withColumn("fiscal_year", year("full_date"))
    )

    (
        df_dim_date.write
        .format("delta")
        .mode("overwrite")
        .save(dim_date_path)
    )

    logger.info("dim_date written to %s (rows=%d)", dim_date_path, df_dim_date.count())
    return df_dim_date


def build_dim_asset(df_silver_all: DataFrame, dim_asset_path: str) -> DataFrame:
    w = Window.orderBy("asset_code")

    df_dim_asset = (
        df_silver_all
        .select(lower(col("asset")).alias("asset_code"))
        .where(col("asset").isNotNull())
        .distinct()
        .withColumn("asset_key", (row_number().over(w)).cast(IntegerType()))
        .withColumn("asset_name", col("asset_code"))
        .withColumn("is_stablecoin", when(col("asset_code") == "usdt", lit(True)).otherwise(lit(False)))
        .withColumn("created_at", current_timestamp())
    )

    (
        df_dim_asset.write
        .format("delta")
        .mode("overwrite")
        .save(dim_asset_path)
    )

    logger.info("dim_asset written to %s (rows=%d)", dim_asset_path, df_dim_asset.count())
    return df_dim_asset


def build_dim_fiat(df_silver_all: DataFrame, dim_fiat_path: str) -> DataFrame:
    w = Window.orderBy("fiat_code")

    df_dim_fiat = (
        df_silver_all
        .select(lower(col("fiat")).alias("fiat_code"))
        .where(col("fiat").isNotNull())
        .distinct()
        .withColumn("fiat_key", (row_number().over(w)).cast(IntegerType()))
        .withColumn("fiat_name", col("fiat_code"))
        .withColumn("currency_symbol", when(col("fiat_code") == "vnd", lit("₫")).otherwise(lit("$")))
        .withColumn("is_local", when(col("fiat_code") == "vnd", lit(True)).otherwise(lit(False)))
    )

    (
        df_dim_fiat.write
        .format("delta")
        .mode("overwrite")
        .save(dim_fiat_path)
    )

    logger.info("dim_fiat written to %s (rows=%d)", dim_fiat_path, df_dim_fiat.count())
    return df_dim_fiat


# ========================= FACT BUILDER ================================

def build_fact(df_silver_2d: DataFrame,
               df_dim_asset: DataFrame,
               df_dim_fiat: DataFrame,
               fact_path: str,
               spark: SparkSession) -> None:

    logger.info("Building FACT for last 2 days (windowed Silver)...")

    df_completed = df_silver_2d.filter(col("order_status") == "COMPLETED")

    df_fact_agg = (
        df_completed.groupBy("trade_date", "asset", "fiat")
        .agg(
            spark_sum(when(col("trade_type") == "BUY", col("amount")).otherwise(0)).alias("buy_volume"),
            spark_sum(when(col("trade_type") == "SELL", col("amount")).otherwise(0)).alias("sell_volume"),
            spark_sum(when(col("trade_type") == "BUY", col("total_vnd")).otherwise(0)).alias("buy_total_vnd"),
            spark_sum(when(col("trade_type") == "SELL", col("total_vnd")).otherwise(0)).alias("sell_total_vnd"),
            spark_sum(col("net_volume")).alias("daily_net_volume"),
            spark_sum(col("commission")).alias("total_commission"),
            avg(col("commission")).alias("avg_commission"),
            # Weighted avg prices
            (
                spark_sum(when(col("trade_type") == "BUY", col("unit_price") * col("amount")).otherwise(0)) /
                coalesce(spark_sum(when(col("trade_type") == "BUY", col("amount")).otherwise(0)), lit(1))
            ).alias("avg_unit_buy_price"),
            (
                spark_sum(when(col("trade_type") == "SELL", col("unit_price") * col("amount")).otherwise(0)) /
                coalesce(spark_sum(when(col("trade_type") == "SELL", col("amount")).otherwise(0)), lit(1))
            ).alias("avg_unit_sell_price"),
            count("*").alias("completed_orders"),
        )
        .withColumn("price_spread", col("avg_unit_sell_price") - col("avg_unit_buy_price"))
    )
    df_full = (
        df_silver_2d.groupBy("trade_date", "asset", "fiat")
        .agg(
            count("*").alias("total_orders"),
            count(when(col("order_status") == "CANCELLED", lit(1)).otherwise(None)).alias("canceled_orders"),
        )
    )

    df_fact = (
        df_fact_agg
        .join(df_full, ["trade_date", "asset", "fiat"], "left")
        .withColumn("completed_rate",
                    (col("completed_orders") / coalesce(col("total_orders"), lit(1))) * 100)
        .withColumn("cancel_rate",
                    (col("canceled_orders") / coalesce(col("total_orders"), lit(1))) * 100)
        .withColumn("daily_net_vnd",
                    col("sell_total_vnd") - col("buy_total_vnd"))
    )

    df_fact = (
        df_fact
        .withColumn(
            "date_key",
            (year("trade_date") * 10000 + month("trade_date") * 100 + dayofmonth("trade_date")).cast(IntegerType())
        )
        .withColumn("year", year(col("trade_date")))
        .withColumn("month", month(col("trade_date")))
        .withColumn("day", dayofmonth(col("trade_date")))
    )

    df_fact = (
        df_fact
        .join(
            df_dim_asset.select("asset_key", "asset_code"),
            lower(df_fact["asset"]) == df_dim_asset["asset_code"],
            "left"
        )
        .join(
            df_dim_fiat.select("fiat_key", "fiat_code"),
            lower(df_fact["fiat"]) == df_dim_fiat["fiat_code"],
            "left"
        )
        .drop("asset_code", "fiat_code")
        .withColumn("last_updated", current_timestamp())
    )

    fact_cols = [
        "date_key", "asset_key", "fiat_key",
        "trade_date", "asset", "fiat",
        "buy_volume", "sell_volume",
        "buy_total_vnd", "sell_total_vnd",
        "daily_net_volume", "daily_net_vnd",
        "total_commission", "avg_commission",
        "avg_unit_buy_price", "avg_unit_sell_price",
        "price_spread",
        "completed_orders", "total_orders", "canceled_orders",
        "completed_rate", "cancel_rate",
        "year", "month", "day",
        "last_updated",
    ]

    df_fact = df_fact.select(*fact_cols)

    # =========== DELETE + APPEND THEO NGÀY (KHÔNG MERGE) ============

    date_rows = df_fact.select("trade_date").distinct().collect()
    proc_dates: List[str] = [r["trade_date"].strftime("%Y-%m-%d") for r in date_rows]
    logger.info("Fact window dates to refresh: %s", proc_dates)

    fact_path_path = Path(fact_path)
    fact_path_str = str(fact_path_path)

    if fact_path_path.exists() and DeltaTable.isDeltaTable(spark, fact_path_str):
        logger.info("Fact table exists at %s → DELETE + APPEND cho các ngày trong batch", fact_path_str)
        delta_fact = DeltaTable.forPath(spark, fact_path_str)

        if proc_dates:
            cond = "trade_date IN ({})".format(
                ", ".join([f"DATE '{d}'" for d in proc_dates])
            )
            logger.info("Deleting rows with condition: %s", cond)
            delta_fact.delete(cond)

        # Append rows mới
        (
            df_fact.write
            .format("delta")
            .mode("append")
            .partitionBy("year", "month", "day")
            .save(fact_path_str)
        )
        logger.info("Appended %d rows into fact_c2c_trades_daily", df_fact.count())

    else:
        logger.info("Fact table does NOT exist → creating new Delta fact at %s", fact_path_str)
        fact_path_path.mkdir(parents=True, exist_ok=True)
        (
            df_fact.write
            .format("delta")
            .mode("overwrite")
            .partitionBy("year", "month", "day")
            .save(fact_path_str)
        )
        logger.info("Initial fact written (rows=%d)", df_fact.count())


# ========================= MAIN =======================================

def main():
    spark: SparkSession = None
    try:
        spark = create_spark_session()
        spark.conf.set("spark.sql.shuffle.partitions",
                       os.getenv("SPARK_SHUFFLE_PARTITIONS", "8"))

        logger.info("Checking MinIO connectivity for Silver...")
        check_minio_connectivity(MINIO_ENDPOINT, ACCESS_KEY, SECRET_KEY, SILVER_PATH)

        logger.info("Reading Silver from %s", SILVER_PATH)
        df_silver_all = spark.read.format("delta").load(SILVER_PATH)

        if df_silver_all.rdd.isEmpty():
            logger.warning("Silver table is empty. Nothing to process in Gold.")
            return

        max_date_row = df_silver_all.select(spark_max("trade_date").alias("max_date")).collect()[0]
        max_date = max_date_row["max_date"]
        if not max_date:
            logger.warning("No trade_date found in Silver. Abort Gold job.")
            return

        from_date_row = spark.createDataFrame(
            [(max_date,)],
            ["max_date"]
        ).select(date_sub(col("max_date"), 1).alias("from_date")).collect()[0]
        from_date = from_date_row["from_date"]

        logger.info("Gold window: from %s to %s (2 most recent days)", from_date, max_date)

        df_silver_2d = df_silver_all.filter(
            (col("trade_date") >= from_date) & (col("trade_date") <= max_date)
        )

        # ================= BUILD DIMS & FACT ======================

        gold_root = Path(GOLD_LOCAL_PATH)
        gold_root.mkdir(parents=True, exist_ok=True)

        dim_date_path = str(gold_root / "dim_date")
        dim_asset_path = str(gold_root / "dim_asset")
        dim_fiat_path = str(gold_root / "dim_fiat")
        fact_path = str(gold_root / "fact_c2c_trades_daily")

        logger.info("Generating dimensions...")
        df_dim_date = build_dim_date(spark, df_silver_all, dim_date_path)
        df_dim_asset = build_dim_asset(df_silver_all, dim_asset_path)
        df_dim_fiat = build_dim_fiat(df_silver_all, dim_fiat_path)

        logger.info("Generating fact table (delete + append by date)...")
        build_fact(df_silver_2d, df_dim_asset, df_dim_fiat, fact_path, spark)

        # ================= UPLOAD TO GCS ==========================
        logger.info("Gold layer built locally. Starting upload to GCS...")
        backup_gold_to_gcs(GOLD_LOCAL_PATH, CONFIG_PATH)

        logger.info("Gold Job V3 completed successfully.")

    except Exception as e:
        logger.exception("Gold Job V3 failed: %s", e)
        raise

    finally:
        if spark is not None:
            spark.stop()
        logger.info("Spark session stopped.")


if __name__ == "__main__":
    main()
