import os
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.common import WatermarkStrategy
from pyflink.common.typeinfo import Types

def main():
    print("🚀 Starting PyFlink DataStream with KafkaSource.builder()...")
    
    # Create execution environment
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    
    # Add JAR files from kafka_connect/jars directory
    jars_dir = "kafka_connect/jars"
    required_jars = [
        "flink-connector-kafka-1.17.1.jar",
        "kafka-clients-3.4.0.jar",
        "flink-table-api-java-1.17.1.jar"
    ]
    
    jar_paths = []
    for jar_name in required_jars:
        jar_path = os.path.join(jars_dir, jar_name)
        if os.path.exists(jar_path):
            jar_paths.append(f"file://{os.path.abspath(jar_path)}")
            print(f"📦 Found JAR: {jar_name}")
        else:
            print(f"⚠️ Missing JAR: {jar_name}")
    
    # Add all JAR files to Flink environment
    if jar_paths:
        env.add_jars(";".join(jar_paths))  # Windows uses semicolon separator
        print(f"✅ Added {len(jar_paths)} JAR files to Flink environment")
    else:
        print("❌ No JAR files found in kafka_connect/jars/")
    
    # Create Kafka source using builder pattern
    kafka_source = KafkaSource.builder() \
        .set_bootstrap_servers('localhost:9092') \
        .set_topics('c2c-trades') \
        .set_group_id('pyflink-consumer-group') \
        .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()
    
    print("📡 Created KafkaSource for topic 'c2c-trades'...")
    
    # Create DataStream from Kafka source
    data_stream = env.from_source(
        kafka_source,
        WatermarkStrategy.no_watermarks(),
        'Kafka Source'
    )
    
    # Process stream - print each message with formatting
    data_stream.map(
        lambda x: f"📨 [PyFlink] Received: {x}",
        output_type=Types.STRING()
    ).print()
    
    print("🎯 DataStream created with KafkaSource.builder()")
    print("🛑 Press Ctrl+C to stop")
    
    try:
        # Execute the job
        env.execute('PyFlink KafkaSource Consumer')
    except KeyboardInterrupt:
        print("\n🛑 Job stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure Kafka is running and topic 'c2c-trades' exists")

if __name__ == '__main__':
    main()
