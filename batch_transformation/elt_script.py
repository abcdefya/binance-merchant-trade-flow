from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_unixtime, to_date, upper, lower, when,
    lit, coalesce, count, round
)
from pyspark.sql.types import DecimalType
from decimal import Decimal
import os

# ============================
# ENVIRONMENT VARIABLES
# ============================
MINIO_ENDPOINT = os.environ["MINIO_ENDPOINT"]
ACCESS_KEY     = os.environ["AWS_ACCESS_KEY_ID"]
SECRET_KEY     = os.environ["AWS_SECRET_ACCESS_KEY"]
BRONZE_PATH    = os.environ["BRONZE_PATH"]
SILVER_PATH    = os.environ["SILVER_PATH"]

# ============================
# SPARK SESSION CONFIG
# ============================
spark = (
    SparkSession.builder
    .appName("silver-transformation")
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
    .config("spark.hadoop.fs.s3a.access.key", ACCESS_KEY)
    .config("spark.hadoop.fs.s3a.secret.key", SECRET_KEY)
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
    .config("spark.delta.logStore.class", "org.apache.spark.sql.delta.storage.S3SingleDriverLogStore")
    .getOrCreate()
)

# ============================
# STEP 1 — READ BRONZE PARQUET
# ============================
df_bronze = spark.read.parquet(BRONZE_PATH)
print("✅ Loaded Bronze data")
df_bronze.printSchema()

# ============================
# STEP 2 — SILVER TRANSFORMATION
# ============================
df_silver = (
    df_bronze
    # Cast createTime (ms → TIMESTAMP)
    .withColumn("createTime", from_unixtime(col("createTime") / 1000))
    # Derive trade_date
    .withColumn("trade_date", to_date(col("createTime")))
    # Cast numerics
    .withColumn("amount", col("amount").cast(DecimalType(18, 8)))
    .withColumn("totalPrice", col("totalPrice").cast(DecimalType(18, 2)))
    .withColumn("unitPrice", col("unitPrice").cast(DecimalType(18, 2)))
    .withColumn("commission", coalesce(col("commission").cast(DecimalType(18, 8)), lit(Decimal("0.00000000"))))
    # Enrich
    .withColumn("total_vnd", col("totalPrice"))
    .withColumn(
        "net_volume",
        when(col("tradeType") == "BUY", col("amount"))
        .when(col("tradeType") == "SELL", -col("amount"))
        .otherwise(lit(Decimal("0.00000000")))
    )
    # Standardize
    .withColumn("tradeType", upper(col("tradeType")))
    .withColumn("asset", lower(col("asset")))
    # Optional filter
    # .filter(col("orderStatus") == "COMPLETED")
    # Select + alias
    .select(
        col("orderNumber").alias("order_number"),
        col("advNo").alias("adv_no"),
        col("tradeType").alias("trade_type"),
        col("asset"),
        col("fiat"),
        col("fiatSymbol").alias("fiat_symbol"),
        col("amount"),
        col("totalPrice").alias("total_price"),
        col("unitPrice").alias("unit_price"),
        col("orderStatus").alias("order_status"),
        col("createTime").alias("create_time"),
        col("trade_date"),
        col("commission"),
        col("counterPartNickName").alias("counter_part_nick_name"),
        lit("UNKNOWN").alias("advertisement_role"),
        col("total_vnd"),
        col("net_volume"),
    )
)

print("✅ Silver transformation complete")
df_silver.printSchema()
df_silver.show(5, truncate=False)

# ============================
# STEP 3 — VALIDATE DATA QUALITY
# ============================
print("🔍 Null percentage per column:")
df_silver.select([
    round((count(when(col(c).isNull(), c)) / count("*")) * 100, 2).alias(c + "_null_pct")
    for c in df_silver.columns
]).show()

# ============================
# STEP 4 — WRITE TO DELTA (SILVER)
# ============================
(
    df_silver.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("trade_date")
    .save(SILVER_PATH)
)
print(f"✅ Silver Delta table written successfully → {SILVER_PATH}")

spark.stop()