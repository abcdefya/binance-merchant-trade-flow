import logging
import os
from datetime import datetime

# Import từ documents của bạn (thay nếu cần path hoặc adjust import)
from src.components.data_ingestion import C2CExtended  # Class để gọi API
from src.utils.delta_exporter import api_results_to_dataframe  # Chuyển data thành DataFrame

# Import PySpark và Delta
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_unixtime, to_date, year, month, dayofmonth
from pyspark.sql.types import DecimalType

# Configure logging
logging.basicConfig(level=logging.INFO)

def main():
    # Lấy config từ env vars (override khi run container với -e)
    minio_endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY", "adminc2c")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY", "adminc2c")
    minio_secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
    bronze_delta_path = os.environ.get("BRONZE_DELTA_PATH", "s3a://sparkbucket/bronze/delta/c2c_trades")

    # Tạo SparkSession với Delta và MinIO config
    spark = SparkSession.builder \
        .appName("Direct Delta Write to MinIO Bronze") \
        .config("spark.hadoop.fs.s3a.endpoint", f"http://{minio_endpoint}" if not minio_secure else f"https://{minio_endpoint}") \
        .config("spark.hadoop.fs.s3a.access.key", minio_access_key) \
        .config("spark.hadoop.fs.s3a.secret.key", minio_secret_key) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "true" if minio_secure else "false") \
        .config("spark.jars.packages", "io.delta:delta-spark_2.12:3.2.0") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("INFO")
    logging.info("SparkSession created with MinIO and Delta config.")

    try:
        # Lấy data từ API
        c2c = C2CExtended(config_rest_api=None)  # Thay config nếu cần
        data = c2c.get_latest()
        logging.info(f"Retrieved {len(data)} trades from get_latest()")

        if not data:
            logging.warning("No data retrieved. Skipping.")
            return

        # Chuyển thành Pandas DF rồi sang Spark DF
        pandas_df = api_results_to_dataframe(data)
        df_bronze = spark.createDataFrame(pandas_df)
        logging.info(f"DataFrame created with {df_bronze.count()} rows.")

        # Enrich với partition columns và transform
        df_enriched = df_bronze \
            .withColumn("create_time_ts", from_unixtime(col("create_time") / 1000)) \
            .withColumn("trade_date", to_date(col("create_time_ts"))) \
            .withColumn("year", year(col("trade_date"))) \
            .withColumn("month", month(col("trade_date"))) \
            .withColumn("day", dayofmonth(col("trade_date"))) \
            .withColumn("amount", col("amount").cast(DecimalType(18, 8))) \
            .withColumn("total_price", col("total_price").cast(DecimalType(18, 2))) \
            .withColumn("unit_price", col("unit_price").cast(DecimalType(18, 2))) \
            .withColumn("commission", coalesce(col("commission").cast(DecimalType(18, 8)), lit(0))) \
            .withColumn("trade_type", upper(col("trade_type"))) \
            .withColumn("asset", lower(col("asset"))) \
            .withColumn("net_volume", when(col("trade_type") == "BUY", col("amount")).otherwise(-col("amount")))

        logging.info("Data enriched with partition columns (year/month/day).")

        # Direct write vào Delta trên MinIO Bronze (append mode, partitioning)
        df_enriched.write \
            .format("delta") \
            .mode("append") \
            .partitionBy("year", "month", "day") \
            .save(bronze_delta_path)

        logging.info(f"Data appended directly to Delta table on MinIO: {bronze_delta_path}")

    except Exception as e:
        logging.error(f"Error in pipeline: {str(e)}")
        raise

    finally:
        # Dừng Spark
        spark.stop()
        logging.info("SparkSession stopped.")

if __name__ == "__main__":
    main()