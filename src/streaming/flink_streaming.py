import os
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
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)

    # Add required JARs với URI đúng (loại bỏ SQL connector để tránh conflict)
    env.add_jars(
        get_jar_uri("flink-connector-kafka-3.2.0-1.18.jar"),  # Nâng cấp connector
        get_jar_uri("kafka-clients-3.2.0.jar"),  # Client version >=3.1.0 để fix method
        get_jar_uri("flink-json-1.18.0.jar"),
        get_jar_uri("flink-connector-jdbc-3.2.0-1.18.jar"),  # Nâng cấp nếu cần
        get_jar_uri("postgresql-42.7.7.jar"),
    )

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers("127.0.0.1:9092")
        .set_topics("binance.c2c.trades")
        .set_group_id("flink-datastream-consumer-001")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    ds = env.from_source(source, WatermarkStrategy.no_watermarks(), "kafka-source")
    ds.print()

    env.execute("kafka-source-print")


if __name__ == "__main__":
    main()