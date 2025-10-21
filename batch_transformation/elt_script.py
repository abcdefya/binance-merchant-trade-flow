from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_unixtime, to_date, upper, lower, when, lit, coalesce
from pyspark.sql.types import DecimalType
import os

try:
    # Tạo SparkSession (bỏ jars/packages vì entrypoint handle)
    spark = SparkSession.builder \
        .appName("MinIO ELT Pipeline") \
        .config("spark.hadoop.fs.s3a.endpoint", os.environ["MINIO_ENDPOINT"]) \
        .config("spark.hadoop.fs.s3a.access.key", os.environ["MINIO_ACCESS_KEY"]) \
        .config("spark.hadoop.fs.s3a.secret.key", os.environ["MINIO_SECRET_KEY"]) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", os.environ["MINIO_SECURE"]) \
        .config("spark.hadoop.fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .getOrCreate()

    print("SparkSession created successfully!")

    # Đọc Parquet từ Bronze
    df_bronze = spark.read.parquet(os.environ["BRONZE_PATH"])
    df_bronze.show(5)

    # Transform (giữ nguyên logic)
    df_silver = df_bronze \
        .withColumn("createTime", from_unixtime(col("createTime") / 1000)) \
        .withColumn("trade_date", to_date(col("createTime"))) \
        .withColumn("amount", col("amount").cast(DecimalType(18, 8))) \
        .withColumn("totalPrice", col("totalPrice").cast(DecimalType(18, 2))) \
        .withColumn("unitPrice", col("unitPrice").cast(DecimalType(18, 2))) \
        .withColumn("commission", coalesce(col("commission").cast(DecimalType(18, 8)), lit(0))) \
        .withColumn("tradeType", upper(col("tradeType"))) \
        .withColumn("asset", lower(col("asset"))) \
        .withColumn("net_volume", when(col("tradeType") == "BUY", col("amount")).otherwise(-col("amount")))

    # Ghi vào Silver (Delta)
    df_silver.write.format("delta").mode("overwrite").partitionBy("trade_date").save(os.environ["SILVER_PATH"])

    # Dừng Spark
    spark.stop()
except Exception as e:
    print(f"Error: {str(e)}")
    raise