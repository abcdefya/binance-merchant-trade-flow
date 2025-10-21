# Use official Spark image with Python support
FROM apache/spark:3.5.0-python3

# Switch to root to install packages
USER root

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Download required JAR files for MinIO/S3A and Delta Lake
RUN mkdir -p /opt/spark/jars && \
    wget -q -P /opt/spark/jars https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar && \
    wget -q -P /opt/spark/jars https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar && \
    wget -q -P /opt/spark/jars https://repo1.maven.org/maven2/io/delta/delta-core_2.12/2.4.0/delta-core_2.12-2.4.0.jar && \
    wget -q -P /opt/spark/jars https://repo1.maven.org/maven2/io/delta/delta-storage/2.4.0/delta-storage-2.4.0.jar

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir pyspark==3.5.0 delta-spark==2.4.0 minio

# Copy the ELT script
COPY elt_script.py .

# Set environment variables (can be overridden at runtime)
ENV SPARK_HOME=/opt/spark
ENV PYTHONPATH=$SPARK_HOME/python:$SPARK_HOME/python/lib/py4j-*.zip:$PYTHONPATH
ENV PATH=$SPARK_HOME/bin:$PATH

# Default environment variables for MinIO (override these in docker-compose)
ENV MINIO_ENDPOINT=http://minio:9000
ENV MINIO_ACCESS_KEY=minioadmin
ENV MINIO_SECRET_KEY=minioadmin
ENV MINIO_SECURE=false
ENV BRONZE_PATH=s3a://bronze/c2c_trades/
ENV SILVER_PATH=s3a://silver/c2c_trades/

# Switch back to spark user for security
USER spark

# Run the ELT script with spark-submit
ENTRYPOINT ["spark-submit", \
    "--master", "local[*]", \
    "--deploy-mode", "client", \
    "--conf", "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension", \
    "--conf", "spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog", \
    "--conf", "spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem", \
    "--conf", "spark.hadoop.fs.s3a.path.style.access=true", \
    "elt_script.py"]

