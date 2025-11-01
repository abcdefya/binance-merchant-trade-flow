import logging
import os
from datetime import datetime

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql.functions import (
    col, sum as spark_sum, avg, count, when, round, lit, current_timestamp,
    coalesce, year, month, dayofmonth, concat, to_date, row_number, expr, current_date
)
from pyspark.sql.types import IntegerType, DecimalType
from decimal import Decimal

from spark_utils import (
    check_minio_connectivity,
    create_spark_session,
)

# --------------------- CONFIG & LOGGING ---------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Starting Spark session for Gold transformation with Star Schema...")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
ACCESS_KEY = os.getenv("MINIO_ROOT_USER", os.getenv("AWS_ACCESS_KEY_ID", ""))
SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
SILVER_PATH = os.getenv("SILVER_PATH", "s3a://silver/c2c_trades/")
GOLD_PATH = os.getenv("GOLD_PATH", "s3a://gold/")

logger.info("MINIO_ENDPOINT: %s", MINIO_ENDPOINT)
logger.info("SILVER_PATH: %s", SILVER_PATH)
logger.info("GOLD_PATH: %s", GOLD_PATH)


def populate_dim_date(spark: SparkSession, df_silver: DataFrame) -> DataFrame:
    """Populate dim_date from min-max trade_date in Silver."""
    min_date = df_silver.agg({"trade_date": "min"}).collect()[0][0]
    max_date = df_silver.agg({"trade_date": "max"}).collect()[0][0]
    if min_date and max_date:
        df_dates = spark.sql(f"""
            SELECT sequence(to_date('{min_date}'), to_date('{max_date}'), interval 1 day) AS date_array
        """).selectExpr("explode(date_array) AS full_date")

        df_dim_date = (
            df_dates
            .withColumn(
                "date_key",
                (year("full_date") * 10000 + month("full_date") * 100 + dayofmonth("full_date")).cast(IntegerType()),
            )
            .withColumn("day_of_week", expr("dayofweek(full_date)"))
            .withColumn("month", month("full_date"))
            .withColumn("quarter", expr("quarter(full_date)"))
            .withColumn("year", year("full_date"))
            .withColumn("is_weekend", expr("dayofweek(full_date) IN (1, 7)"))
            .withColumn("fiscal_year", year("full_date"))  # Customize if needed
        )
    else:
        df_dim_date = spark.createDataFrame([], schema="date_key INT, full_date DATE, day_of_week INT, month INT, quarter INT, year INT, is_weekend BOOLEAN, fiscal_year INT")
    
    return df_dim_date

def populate_dim_asset(spark: SparkSession, df_silver: DataFrame) -> DataFrame:
    """Populate dim_asset from distinct asset in Silver."""
    df_dim_asset = (
        df_silver.select("asset").distinct().withColumnRenamed("asset", "asset_code")
        .withColumn(
            "asset_key",
            row_number().over(Window.orderBy("asset_code")).cast(IntegerType()),
        )
        .withColumn("asset_name", concat(lit("Asset "), col("asset_code")))
        .withColumn("is_stablecoin", when(col("asset_code") == "usdt", lit(True)).otherwise(lit(False)))
        .withColumn("created_date", current_timestamp().cast("date"))
    )
    
    return df_dim_asset

def populate_dim_fiat(spark: SparkSession, df_silver: DataFrame) -> DataFrame:
    """Populate dim_fiat from distinct fiat in Silver."""
    df_dim_fiat = (
        df_silver.select("fiat").distinct().withColumnRenamed("fiat", "fiat_code")
        .withColumn(
            "fiat_key",
            row_number().over(Window.orderBy("fiat_code")).cast(IntegerType()),
        )
        .withColumn("fiat_name", concat(lit("Fiat "), col("fiat_code")))
        .withColumn("currency_symbol", when(col("fiat_code") == "vnd", lit("₫")).otherwise(lit("$")))
        .withColumn("is_local", when(col("fiat_code") == "vnd", lit(True)).otherwise(lit(False)))
    )
    
    return df_dim_fiat


def main() -> None:
    """Main entry point for the Gold aggregation script with Star Schema."""
    try:
        spark = create_spark_session(MINIO_ENDPOINT, ACCESS_KEY, SECRET_KEY)
        spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
        logger.info("SparkSession created with MinIO and Delta config.")

        check_minio_connectivity(MINIO_ENDPOINT, ACCESS_KEY, SECRET_KEY, GOLD_PATH)
        logger.info("MinIO connectivity check completed.")

        # Get date_filter from env or default to current_date - 2 days
        date_filter_str = os.getenv("DATE_FILTER", None)
        filter_date = None
        if date_filter_str:
            try:
                # Parse "dd/MM/yyyy" to DATE
                filter_date = spark.sql(f"SELECT to_date(lit('{date_filter_str}'), 'dd/MM/yyyy') as filter_date").collect()[0][0]
                logger.info("Date filter applied from env: from %s to current", filter_date)
            except Exception as e:
                logger.warning("Invalid DATE_FILTER '%s': %s. Using default (current - 2 days).", date_filter_str, e)
                date_filter_str = None

        if not date_filter_str:
            # Default to current_date - 2 days
            filter_date = spark.sql("SELECT date_sub(current_date(), 2) as filter_date").collect()[0][0]
            logger.info("No DATE_FILTER; using default filter: from %s to current", filter_date)

        logger.info("Reading Silver data from: %s", SILVER_PATH)
        df_silver = spark.read.format("delta").load(SILVER_PATH)
        
        # Apply date filter
        if filter_date:
            df_silver = df_silver.filter(col("trade_date") >= filter_date)
            logger.info("Filtered Silver to %d rows from date %s", df_silver.count(), filter_date)
        else:
            logger.info("No date filter; reading full Silver (%d rows)", df_silver.count())

        logger.info("Silver Schema:")
        df_silver.printSchema()

        # Populate dim tables
        dim_date_path = os.path.join(GOLD_PATH, "dim_date/")
        df_dim_date = populate_dim_date(spark, df_silver)
        df_dim_date.write.format("delta").mode("overwrite").save(dim_date_path)
        logger.info("Dim date populated at %s", dim_date_path)

        dim_asset_path = os.path.join(GOLD_PATH, "dim_asset/")
        df_dim_asset = populate_dim_asset(spark, df_silver)
        df_dim_asset.write.format("delta").mode("overwrite").save(dim_asset_path)
        logger.info("Dim asset populated at %s", dim_asset_path)

        dim_fiat_path = os.path.join(GOLD_PATH, "dim_fiat/")
        df_dim_fiat = populate_dim_fiat(spark, df_silver)
        df_dim_fiat.write.format("delta").mode("overwrite").save(dim_fiat_path)
        logger.info("Dim fiat populated at %s", dim_fiat_path)

        # Load dims for joining
        df_dim_date.createOrReplaceTempView("dim_date_view")
        df_dim_asset.createOrReplaceTempView("dim_asset_view")
        df_dim_fiat.createOrReplaceTempView("dim_fiat_view")

        # Filter for completed orders for most metrics
        df_completed = df_silver.filter(col("order_status") == "COMPLETED")

        # Aggregate measures for fact
        df_fact_agg = (
            df_completed.groupBy("trade_date", "asset", "fiat")
            .agg(
                spark_sum(when(col("trade_type") == "BUY", col("amount")).otherwise(0)).alias("buy_volume"),
                spark_sum(when(col("trade_type") == "SELL", col("amount")).otherwise(0)).alias("sell_volume"),
                spark_sum(when(col("trade_type") == "BUY", col("total_price")).otherwise(0)).alias("buy_total_vnd"),
                spark_sum(when(col("trade_type") == "SELL", col("total_price")).otherwise(0)).alias("sell_total_vnd"),
                (spark_sum(when(col("trade_type") == "BUY", col("total_price")).otherwise(0)) +
                 spark_sum(when(col("trade_type") == "SELL", col("total_price")).otherwise(0))).alias("total_buy_sell_vnd"),
                spark_sum(col("net_volume")).alias("daily_net_volume"),
                spark_sum(col("commission")).alias("total_commission"),
                avg(col("commission")).alias("avg_commission"),
                # Weighted avg unit prices
                (spark_sum(when(col("trade_type") == "BUY", col("unit_price") * col("amount")).otherwise(0)) /
                 coalesce(spark_sum(when(col("trade_type") == "BUY", col("amount")).otherwise(0)), lit(1))).alias("avg_unit_buy_price"),
                (spark_sum(when(col("trade_type") == "SELL", col("unit_price") * col("amount")).otherwise(0)) /
                 coalesce(spark_sum(when(col("trade_type") == "SELL", col("amount")).otherwise(0)), lit(1))).alias("avg_unit_sell_price"),
                count("*").alias("completed_orders"),  # Completed orders
            )
            .withColumn("price_spread", col("avg_unit_sell_price") - col("avg_unit_buy_price"))
        )

        # Add rates from full Silver
        df_full_agg = (
            df_silver.groupBy("trade_date", "asset", "fiat")
            .agg(
                count("*").alias("total_orders"),
                count(when(col("order_status") == "CANCELLED", lit(1)).otherwise(None)).alias("canceled_orders"),
            )
        )

        # Join rates
        df_fact_agg = df_fact_agg.join(
            df_full_agg,
            ["trade_date", "asset", "fiat"],
            "left"
        ).withColumn(
            "completed_rate",
            round((col("completed_orders") / coalesce(col("total_orders"), lit(1))) * 100, 2)
        ).withColumn(
            "cancel_rate",
            round((col("canceled_orders") / coalesce(col("total_orders"), lit(1))) * 100, 2)
        ).withColumn(
            "daily_net_vnd",
            col("sell_total_vnd") - col("buy_total_vnd")
        )

        # Add FKs, partition columns, and cumulative
        df_fact = (
            df_fact_agg
            .withColumn(
                "date_key",
                (year("trade_date") * 10000 + month("trade_date") * 100 + dayofmonth("trade_date")).cast(IntegerType()),
            )
            .withColumn("year", year(col("trade_date")))
            .withColumn("month", month(col("trade_date")))
            .withColumn("day", dayofmonth(col("trade_date")))
            .join(
                spark.table("dim_asset_view").select("asset_key", "asset_code"),
                col("asset") == col("asset_code"),
                "left",
            )
            .drop("asset_code")
            .join(
                spark.table("dim_fiat_view").select("fiat_key", "fiat_code"),
                col("fiat") == col("fiat_code"),
                "left",
            )
            .drop("fiat_code")
            .withColumn("last_updated", current_timestamp())
        )

        # Persist before window operations to reduce memory pressure
        df_fact.persist()
        logger.info("Persisted fact dataframe before window operations. Row count: %s", df_fact.count())

        # Repartition by window partition keys to optimize memory usage
        df_fact = df_fact.repartition("asset", "fiat")

        window_spec_usdt = Window.partitionBy("asset").orderBy("trade_date").rowsBetween(Window.unboundedPreceding, Window.currentRow)
        window_spec_vnd = Window.partitionBy("fiat").orderBy("trade_date").rowsBetween(Window.unboundedPreceding, Window.currentRow)

        df_fact = df_fact.withColumn(
            "cumulative_net_volume",
            spark_sum("daily_net_volume").over(window_spec_usdt)
        ).withColumn(
            "cumulative_net_vnd",
            spark_sum("daily_net_vnd").over(window_spec_vnd)
        )
        
        # Unpersist after window operations
        df_fact.unpersist()

        # Handle NULLs
        df_fact = df_fact.fillna(0, subset=["avg_unit_buy_price", "avg_unit_sell_price", "price_spread", "total_orders", "canceled_orders"])

        # Show sample
        logger.info("Fact aggregation complete")
        df_fact.printSchema()
        df_fact.show(5, truncate=False)

        # Validate data quality
        logger.info("Null percentage per column:")
        df_fact.select([
            round((count(when(col(c).isNull(), c)) / count("*")) * 100, 2).alias(c + "_null_pct")
            for c in df_fact.columns
        ]).show()

        row_count = df_fact.count()
        logger.info("Aggregated row count: %s", row_count)

        fact_path = os.path.join(GOLD_PATH, "fact_c2c_trades_daily/")
        logger.info("Writing fact table to Delta Lake (overwrite mode) → %s", fact_path)
        (
            df_fact.write
            .format("delta")
            .mode("overwrite")
            .option("mergeSchema", "true")
            .partitionBy("year", "month", "day")
            .save(fact_path)
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