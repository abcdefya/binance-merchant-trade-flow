import logging
import os
from typing import Optional

from minio import Minio
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col, current_date, from_unixtime, to_date, upper, lower, when,
    coalesce, count, round, lit
)
from pyspark.sql.types import DecimalType
from decimal import Decimal
from delta.tables import DeltaTable
from pyspark.sql.functions import expr

from spark_utils import (
    check_minio_connectivity,
    create_spark_session,
)

# --------------------- CONFIG & LOGGING ---------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Starting Spark session for Silver transformation...")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
ACCESS_KEY = os.getenv("MINIO_ROOT_USER", os.getenv("AWS_ACCESS_KEY_ID", ""))
SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
BRONZE_PATH = os.getenv("BRONZE_PATH", "s3a://bronze/c2c_trades/")
SILVER_PATH = os.getenv("SILVER_PATH", "s3a://silver/c2c_trades/")

logger.info("MINIO_ENDPOINT: %s", MINIO_ENDPOINT)
logger.info("BRONZE_PATH: %s", BRONZE_PATH)
logger.info("SILVER_PATH: %s", SILVER_PATH)


def main() -> None:
    """Main entry point for the Silver transformation script."""
    try:
        spark = create_spark_session()
        spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
        logger.info("SparkSession created with MinIO and Delta config.")

        check_minio_connectivity(MINIO_ENDPOINT, ACCESS_KEY, SECRET_KEY, SILVER_PATH)
        logger.info("MinIO connectivity check completed.")

        input_path = os.getenv("INPUT_PATH", "/shared_volume/c2c/latest/*.parquet")
        logger.info("Reading input data from: %s", input_path)

        df = spark.read.parquet(input_path)
        logger.info("Input Schema:")
        df.printSchema()

        # Choose timestamp column among possible variants
        ts_col = None
        for candidate in ("createTime", "create_time", "create_time_ms"):
            if candidate in df.columns:
                ts_col = candidate
                break

        # Build base with trade_time and trade_date
        if ts_col:
            df = df.withColumn("trade_time", from_unixtime((col(ts_col) / 1000) + 7 * 3600))
            df = df.withColumn("trade_date", to_date(col("trade_time")))
            df = df.drop(ts_col)
        else:
            logger.warning("No create time column found; deriving trade_date as current_date and trade_time NULL")
            df = df.withColumn("trade_date", current_date())
            df = df.withColumn("trade_time", lit(None))

        # Resolve column name variants
        def pick(name1: str, name2: str):
            return name1 if name1 in df.columns else (name2 if name2 in df.columns else None)

        total_price_col = pick("totalPrice", "total_price")
        unit_price_col = pick("unitPrice", "unit_price")
        order_number_col = pick("orderNumber", "order_number")
        adv_no_col = pick("advNo", "adv_no")
        trade_type_col = pick("tradeType", "trade_type")
        order_status_col = pick("orderStatus", "order_status")
        fiat_symbol_col = pick("fiatSymbol", "fiat_symbol")
        counter_nick_col = pick("counterPartNickName", "counter_part_nick_name")

        # Cast and enrich
        df = df.withColumn("amount", col("amount").cast(DecimalType(18, 8)))
        if total_price_col:
            df = df.withColumn("totalPrice_std", col(total_price_col).cast(DecimalType(18, 2)))
        else:
            df = df.withColumn("totalPrice_std", lit(Decimal("0")).cast(DecimalType(18, 2)))
        if unit_price_col:
            df = df.withColumn("unitPrice_std", col(unit_price_col).cast(DecimalType(18, 2)))
        else:
            df = df.withColumn("unitPrice_std", lit(Decimal("0")).cast(DecimalType(18, 2)))

        df = df.withColumn("commission", coalesce(col("commission").cast(DecimalType(18, 8)), lit(Decimal("0.00000000"))))
        df = df.withColumn("total_vnd", col("totalPrice_std"))

        if trade_type_col:
            df = df.withColumn(
                "net_volume",
                when(col(trade_type_col).isin("BUY", "buy"), col("amount") - col("commission"))
                .when(col(trade_type_col).isin("SELL", "sell"), -(col("amount") + col("commission")))
                .otherwise(lit(Decimal("0.00000000")))
            )
            df = df.withColumn(trade_type_col, upper(col(trade_type_col)))
        else:
            df = df.withColumn("net_volume", lit(Decimal("0.00000000")))

        df = df.withColumn("asset", lower(col("asset")))

        # Drop optional columns if they exist
        drop_cols = [c for c in (fiat_symbol_col, counter_nick_col, "advertisement_role") if c and c in df.columns]
        if drop_cols:
            df = df.drop(*drop_cols)

        # Select and alias to standardized schema
        df_silver = df.select(
            (col(order_number_col) if order_number_col else lit(None)).alias("order_number"),
            (col(adv_no_col) if adv_no_col else lit(None)).alias("adv_no"),
            (col(trade_type_col) if trade_type_col else lit(None)).alias("trade_type"),
            col("asset"),
            col("fiat"),
            col("amount"),
            col("totalPrice_std").alias("total_price"),
            col("unitPrice_std").alias("unit_price"),
            (col(order_status_col) if order_status_col else lit(None)).alias("order_status"),
            col("trade_time"),
            col("trade_date"),
            col("commission"),
            col("total_vnd"),
            col("net_volume"),
        )

        # Show sample
        sample_cols = [c for c in ("trade_time", "trade_date") if c in df_silver.columns]
        if sample_cols:
            df_silver.select(*sample_cols).show(5, truncate=False)

        row_count = df_silver.count()
        logger.info("Transformed row count: %s", row_count)

        # Validate data quality
        logger.info("Null percentage per column:")
        df_silver.select([
            round((count(when(col(c).isNull(), c)) / count("*")) * 100, 2).alias(c + "_null_pct")
            for c in df_silver.columns
        ]).show()

        # Prepare status priority on source rows
        df_silver = df_silver.withColumn(
            "status_priority",
            when(col("order_status") == "COMPLETED", lit(8))
            .when(col("order_status") == "IN_APPEAL", lit(7))
            .when(col("order_status") == "DISTRIBUTING", lit(6))
            .when(col("order_status") == "BUYER_PAYED", lit(5))
            .when(col("order_status") == "TRADING", lit(4))
            .when(col("order_status") == "PENDING", lit(3))
            .when(col("order_status") == "CANCELLED", lit(2))
            .when(col("order_status") == "CANCELLED_BY_SYSTEM", lit(1))
            .otherwise(lit(0))
        )

        # If target table does not exist, bootstrap it and return
        if not DeltaTable.isDeltaTable(spark, SILVER_PATH):
            logger.info("Silver table not found. Bootstrapping at %s", SILVER_PATH)
            (
                df_silver.drop("status_priority")
                .write.format("delta")
                .mode("append")
                .partitionBy("trade_date")
                .save(SILVER_PATH)
            )
            logger.info("Bootstrap write completed.")
        else:
            logger.info("Merging into Silver table at %s", SILVER_PATH)
            delta_table = DeltaTable.forPath(spark, SILVER_PATH)

            # Build target priority expression from target.order_status without storing it
            target_priority_sql = (
                "CASE "
                "WHEN target.order_status = 'COMPLETED' THEN 8 "
                "WHEN target.order_status = 'IN_APPEAL' THEN 7 "
                "WHEN target.order_status = 'DISTRIBUTING' THEN 6 "
                "WHEN target.order_status = 'BUYER_PAYED' THEN 5 "
                "WHEN target.order_status = 'TRADING' THEN 4 "
                "WHEN target.order_status = 'PENDING' THEN 3 "
                "WHEN target.order_status = 'CANCELLED' THEN 2 "
                "WHEN target.order_status = 'CANCELLED_BY_SYSTEM' THEN 1 "
                "ELSE 0 END"
            )

            delta_table.alias("target").merge(
                df_silver.alias("source"),
                "target.order_number = source.order_number",
            ).whenMatchedUpdate(
                condition=expr(f"source.status_priority > ({target_priority_sql})"),
                set={
                    "order_status": col("source.order_status"),
                    "commission": col("source.commission"),
                    "net_volume": col("source.net_volume"),
                    "total_vnd": col("source.total_vnd"),
                    "asset": col("source.asset"),
                    "fiat": col("source.fiat"),
                    "amount": col("source.amount"),
                    "total_price": col("source.total_price"),
                    "unit_price": col("source.unit_price"),
                    "trade_time": col("source.trade_time"),
                    "trade_date": col("source.trade_date"),
                },
            ).whenNotMatchedInsertAll().execute()

            logger.info("Merge completed successfully.")

    except Exception as e:
        logger.exception("Error during execution: %s", e)
        raise
    finally:
        if "spark" in locals():
            spark.stop()
        logger.info("Spark session stopped.")


if __name__ == "__main__":
    main()