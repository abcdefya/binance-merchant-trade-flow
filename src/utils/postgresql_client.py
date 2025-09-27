import logging
import os
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Union
from urllib.parse import quote_plus

import pandas as pd
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PostgreSQLClientError(Exception):
    """Custom exception for PostgreSQL client errors"""
    pass


class PostgreSQLClient:
    """
    Production-ready PostgreSQL client with connection pooling and proper error handling.
    
    Features:
    - Connection pooling for better performance
    - Proper error handling and logging
    - Security: SQL injection prevention
    - Type hints for better code maintainability
    - Context managers for resource management
    - Configurable connection parameters
    """
    
    def __init__(
        self, 
        database: str,
        user: str,
        password: str,
        host: str = "127.0.0.1",
        port: Union[str, int] = 5432,
        min_conn: int = 1,
        max_conn: int = 10,
        connect_timeout: int = 30,
        **kwargs
    ):
        """
        Initialize PostgreSQL client with connection pooling.
        
        Args:
            database: Database name
            user: Username
            password: Password
            host: Database host
            port: Database port
            min_conn: Minimum connections in pool
            max_conn: Maximum connections in pool
            connect_timeout: Connection timeout in seconds
            **kwargs: Additional psycopg2 connection parameters
        """
        self.database = database
        self.user = user
        self.password = password
        self.host = host
        self.port = int(port)
        self.connect_timeout = connect_timeout
        
        # Connection parameters
        self.conn_params = {
            "database": self.database,
            "user": self.user,
            "password": self.password,
            "host": self.host,
            "port": self.port,
            "connect_timeout": self.connect_timeout,
            **kwargs
        }
        
        # Initialize connection pool
        try:
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                min_conn, max_conn, **self.conn_params
            )
            logger.info(f"Connection pool initialized: {min_conn}-{max_conn} connections")
        except psycopg2.Error as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise PostgreSQLClientError(f"Connection pool initialization failed: {e}")
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for getting database connections from pool.
        
        Yields:
            psycopg2.connection: Database connection
            
        Raises:
            PostgreSQLClientError: If connection cannot be obtained
        """
        conn = None
        try:
            conn = self.connection_pool.getconn()
            if conn is None:
                raise PostgreSQLClientError("Unable to get connection from pool")
            
            # Test connection
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                
            yield conn
            
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {e}")
            raise PostgreSQLClientError(f"Database operation failed: {e}")
        finally:
            if conn:
                self.connection_pool.putconn(conn)
    
    def execute_query(
        self, 
        query: str, 
        params: Optional[tuple] = None,
        fetch: bool = False,
        return_dict: bool = False
    ) -> Optional[List[Any]]:
        """
        Execute SQL query with proper error handling and parameterization.
        
        Args:
            query: SQL query string
            params: Query parameters (prevents SQL injection)
            fetch: Whether to fetch results
            return_dict: Return results as dictionaries
            
        Returns:
            Query results if fetch=True, None otherwise
            
        Raises:
            PostgreSQLClientError: If query execution fails
        """
        try:
            with self.get_connection() as conn:
                cursor_factory = RealDictCursor if return_dict else None
                
                with conn.cursor(cursor_factory=cursor_factory) as cursor:
                    # Log query (without sensitive parameters)
                    logger.debug(f"Executing query: {query[:100]}...")
                    
                    cursor.execute(query, params)
                    
                    if fetch:
                        results = cursor.fetchall()
                        logger.info(f"Query returned {len(results)} rows")
                        return results
                    else:
                        conn.commit()
                        affected_rows = cursor.rowcount
                        logger.info(f"Query executed successfully. {affected_rows} rows affected")
                        return None
                        
        except psycopg2.Error as e:
            logger.error(f"Query execution failed: {e}")
            raise PostgreSQLClientError(f"Query execution failed: {e}")
    
    def execute_many(self, query: str, params_list: List[tuple]) -> None:
        """
        Execute query multiple times with different parameters (batch insert).
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
            
        Raises:
            PostgreSQLClientError: If batch execution fails
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    logger.debug(f"Executing batch query with {len(params_list)} parameter sets")
                    cursor.executemany(query, params_list)
                    conn.commit()
                    logger.info(f"Batch query executed successfully. {cursor.rowcount} rows affected")
                    
        except psycopg2.Error as e:
            logger.error(f"Batch query execution failed: {e}")
            raise PostgreSQLClientError(f"Batch query execution failed: {e}")
    
    def get_columns(self, table_name: str, schema: str = "public") -> List[str]:
        """
        Get column names for a table using information_schema (efficient approach).
        
        Args:
            table_name: Name of the table
            schema: Schema name (default: public)
            
        Returns:
            List of column names
            
        Raises:
            PostgreSQLClientError: If unable to fetch column information
        """
        query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND table_schema = %s
        ORDER BY ordinal_position
        """
        
        try:
            results = self.execute_query(query, (table_name, schema), fetch=True)
            columns = [row[0] for row in results] if results else []
            
            if not columns:
                logger.warning(f"No columns found for table {schema}.{table_name}")
                
            return columns
            
        except PostgreSQLClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to get columns for table {table_name}: {e}")
            raise PostgreSQLClientError(f"Failed to get table columns: {e}")
    
    def table_exists(self, table_name: str, schema: str = "public") -> bool:
        """
        Check if a table exists in the database.
        
        Args:
            table_name: Name of the table
            schema: Schema name (default: public)
            
        Returns:
            True if table exists, False otherwise
        """
        query = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = %s AND table_schema = %s
        )
        """
        
        try:
            result = self.execute_query(query, (table_name, schema), fetch=True)
            return result[0][0] if result else False
        except PostgreSQLClientError:
            return False
    
    def get_dataframe(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """
        Execute query and return results as pandas DataFrame.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            pandas DataFrame with query results
            
        Raises:
            PostgreSQLClientError: If query execution fails
        """
        try:
            # Create SQLAlchemy engine for pandas
            engine = self._get_sqlalchemy_engine()
            
            # Use pandas.read_sql with parameterized query
            if params:
                df = pd.read_sql(query, engine, params=params)
            else:
                df = pd.read_sql(query, engine)
            
            logger.info(f"DataFrame created with {len(df)} rows and {len(df.columns)} columns")
            return df
            
        except Exception as e:
            logger.error(f"Failed to create DataFrame: {e}")
            raise PostgreSQLClientError(f"DataFrame creation failed: {e}")
    
    def _get_sqlalchemy_engine(self):
        """
        Create SQLAlchemy engine with connection pooling.
        
        Returns:
            SQLAlchemy engine
        """
        # URL encode password to handle special characters
        encoded_password = quote_plus(self.password)
        
        connection_string = (
            f"postgresql+psycopg2://{self.user}:{encoded_password}"
            f"@{self.host}:{self.port}/{self.database}"
        )
        
        return create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Validate connections before use
            echo=False  # Set to True for SQL logging
        )
    
    def close_all_connections(self) -> None:
        """
        Close all connections in the pool.
        """
        try:
            if hasattr(self, 'connection_pool'):
                self.connection_pool.closeall()
                logger.info("All database connections closed")
        except Exception as e:
            logger.error(f"Error closing connections: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close_all_connections()
    
    def __del__(self):
        """Destructor - ensure connections are closed"""
        self.close_all_connections()


# Factory function for easy client creation from environment variables
def create_client_from_env() -> PostgreSQLClient:
    """
    Create PostgreSQL client using environment variables.
    
    Environment variables:
    - POSTGRES_DB: Database name
    - POSTGRES_USER: Username  
    - POSTGRES_PASSWORD: Password
    - POSTGRES_HOST: Host (default: 127.0.0.1)
    - POSTGRES_PORT: Port (default: 5432)
    
    Returns:
        PostgreSQLClient instance
        
    Raises:
        PostgreSQLClientError: If required environment variables are missing
    """
    required_vars = ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise PostgreSQLClientError(f"Missing required environment variables: {missing_vars}")
    
    return PostgreSQLClient(
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )
