import os
import sys
import logging
from pathlib import Path
from typing import List

from loguru import logger
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import (
    KafkaOffsetsInitializer,
    KafkaSource,
)

from postgres import PostgreSQLClient

# Configure logging for Docker/Airflow compatibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

JARS_PATH = Path(os.getcwd()) / "jars"  # Sử dụng Path để dễ xử lý

def get_jar_uri(jar_name: str) -> str:
    """Tạo file URI đúng cho JAR trên Windows/Linux."""
    jar_path = JARS_PATH / jar_name
    if not jar_path.exists():
        raise FileNotFoundError(f"JAR không tồn tại: {jar_path}")
    posix_path = str(jar_path).replace("\\", "/")  # Chuyển sang forward slash
    if os.name == "nt":  # Windows
        return f"file:///{posix_path}"
    else:
        return f"file://{posix_path}"

def main():
    logging.info("🚀 Flink streaming job started")
    sys.stdout.flush()  # Force flush để Airflow capture log ngay
    
    try:
        # Test để container chạy lâu hơn và có thể debug
        import time
        logging.info("Initializing Flink environment...")
        time.sleep(2)
        
        env = StreamExecutionEnvironment.get_execution_environment()
        env.set_runtime_mode(RuntimeExecutionMode.STREAMING)

        # Add required JARs với URI đúng (loại bỏ SQL connector để tránh conflict)
        logging.info("Loading JARs...")
        env.add_jars(
            get_jar_uri("flink-connector-kafka-3.2.0-1.18.jar"),  # Nâng cấp connector
            get_jar_uri("kafka-clients-3.2.0.jar"),  # Client version >=3.1.0 để fix method
            get_jar_uri("flink-json-1.18.0.jar"),
            get_jar_uri("flink-connector-jdbc-3.2.0-1.18.jar"),  # Nâng cấp nếu cần
            get_jar_uri("postgresql-42.7.7.jar"),
        )

        logging.info("Configuring Kafka source...")
        source = (
            KafkaSource.builder()
            .set_bootstrap_servers("broker:29092")  # Updated to use service name
            .set_topics("binance.c2c.trades")
            .set_group_id("flink-datastream-consumer-001")
            .set_starting_offsets(KafkaOffsetsInitializer.earliest())
            .set_value_only_deserializer(SimpleStringSchema())
            .build()
        )

        logging.info("Creating data stream...")
        ds = env.from_source(source, WatermarkStrategy.no_watermarks(), "kafka-source")
        ds.print()

        logging.info("Executing Flink job...")
        env.execute("kafka-source-print")
        
        logging.info("✅ Flink streaming job completed successfully")
        sys.stdout.flush()
        
    except Exception as e:
        logging.error(f"❌ Flink streaming job failed: {e}", exc_info=True)
        sys.stdout.flush()
        raise


if __name__ == "__main__":
    main()