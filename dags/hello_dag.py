from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

# Default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=1),
}

# Task 1
def print_hello():
    print("Hello, World!")
    print("This is a simple Airflow DAG!")
    return "Hello task completed successfully"

# Task 2 (new task)
def print_goodbye():
    print("Goodbye!")
    print("This is the second task in the DAG.")
    return "Goodbye task completed successfully"

# Define the DAG
with DAG(
    dag_id='hello_dag',
    default_args=default_args,
    description='A simple hello world DAG',
    start_date=datetime(2024, 1, 1),
    schedule='@daily',
    catchup=False,
    tags=['hello', 'example']
) as dag:
    
    # Hello task
    hello_task = PythonOperator(
        task_id='hello_task',
        python_callable=print_hello,
    )

    # Goodbye task (added)
    goodbye_task = PythonOperator(
        task_id='goodbye_task',
        python_callable=print_goodbye,
    )

    # Task dependency
    hello_task >> goodbye_task