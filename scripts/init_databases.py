#!/usr/bin/env python3
"""
Database Initialization Script

Initializes all databases (PostgreSQL, Redis, Qdrant) for the trading system.

Usage:
    python scripts/init_databases.py [--force] [--skip-postgres] [--skip-redis] [--skip-qdrant]

Options:
    --force: Drop existing data and recreate
    --skip-postgres: Skip PostgreSQL initialization
    --skip-redis: Skip Redis initialization
    --skip-qdrant: Skip Qdrant initialization
"""

import sys
import asyncio
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import redis as redis_sync
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PayloadSchemaType

from src.core.config import get_config
from src.core.logger import setup_logging, get_logger


logger = get_logger(__name__)


def init_postgres(database_url: str, force: bool = False) -> bool:
    """
    Initialize PostgreSQL database.

    Args:
        database_url: Database connection URL
        force: If True, drop existing database and recreate

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Initializing PostgreSQL...")

        # Parse database URL to get database name
        # Format: postgresql://user:password@host:port/dbname
        parts = database_url.split('/')
        db_name = parts[-1].split('?')[0]
        base_url = '/'.join(parts[:-1])

        # Connect to postgres database to create our database
        conn = psycopg2.connect(f"{base_url}/postgres")
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,)
        )
        exists = cursor.fetchone()

        if exists:
            if force:
                logger.warning(f"Dropping existing database: {db_name}")
                # Terminate existing connections
                cursor.execute(
                    """
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                      AND pid <> pg_backend_pid()
                    """,
                    (db_name,)
                )
                cursor.execute(sql.SQL("DROP DATABASE {}").format(
                    sql.Identifier(db_name)
                ))
            else:
                logger.info(f"Database {db_name} already exists, using existing")
                cursor.close()
                conn.close()

                # Connect to the database and run init script
                conn = psycopg2.connect(database_url)
                cursor = conn.cursor()

                # Read and execute init script
                script_path = Path(__file__).parent / "init_postgres.sql"
                with open(script_path, 'r') as f:
                    sql_script = f.read()

                cursor.execute(sql_script)
                conn.commit()
                cursor.close()
                conn.close()

                logger.info("✓ PostgreSQL initialized successfully")
                return True

        # Create database
        logger.info(f"Creating database: {db_name}")
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(
            sql.Identifier(db_name)
        ))
        cursor.close()
        conn.close()

        # Connect to the new database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # Read and execute init script
        logger.info("Executing initialization script...")
        script_path = Path(__file__).parent / "init_postgres.sql"

        if not script_path.exists():
            logger.error(f"Init script not found: {script_path}")
            return False

        with open(script_path, 'r') as f:
            sql_script = f.read()

        cursor.execute(sql_script)
        conn.commit()

        # Verify tables were created
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        table_count = cursor.fetchone()[0]

        logger.info(f"✓ Created {table_count} tables")

        cursor.close()
        conn.close()

        logger.info("✓ PostgreSQL initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}", exc_info=True)
        return False


def init_redis(redis_url: str, force: bool = False) -> bool:
    """
    Initialize Redis.

    Args:
        redis_url: Redis connection URL
        force: If True, flush all data

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Initializing Redis...")

        client = redis_sync.from_url(redis_url)

        # Test connection
        client.ping()
        logger.info("✓ Connected to Redis")

        if force:
            logger.warning("Flushing all Redis data...")
            client.flushdb()
            logger.info("✓ Redis data flushed")

        # Get some info
        info = client.info('server')
        logger.info(f"Redis version: {info['redis_version']}")

        client.close()

        logger.info("✓ Redis initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}", exc_info=True)
        return False


def init_qdrant(qdrant_url: str, force: bool = False) -> bool:
    """
    Initialize Qdrant vector database.

    Args:
        qdrant_url: Qdrant connection URL
        force: If True, recreate collections

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Initializing Qdrant...")

        client = QdrantClient(url=qdrant_url)

        # Collection name
        collection_name = "trading_experiences"

        # Check if collection exists
        collections = client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)

        if exists:
            if force:
                logger.warning(f"Deleting existing collection: {collection_name}")
                client.delete_collection(collection_name)
            else:
                logger.info(f"Collection {collection_name} already exists")
                logger.info("✓ Qdrant initialized successfully")
                return True

        # Create collection
        logger.info(f"Creating collection: {collection_name}")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=1536,  # OpenAI embedding dimension
                distance=Distance.COSINE
            )
        )

        # Create payload indexes
        logger.info("Creating payload indexes...")

        # Index for outcome field
        client.create_payload_index(
            collection_name=collection_name,
            field_name="outcome",
            field_schema=PayloadSchemaType.KEYWORD
        )

        # Index for importance_score field
        client.create_payload_index(
            collection_name=collection_name,
            field_name="importance_score",
            field_schema=PayloadSchemaType.FLOAT
        )

        # Index for symbol field
        client.create_payload_index(
            collection_name=collection_name,
            field_name="symbol",
            field_schema=PayloadSchemaType.KEYWORD
        )

        # Index for tags field
        client.create_payload_index(
            collection_name=collection_name,
            field_name="tags",
            field_schema=PayloadSchemaType.KEYWORD
        )

        logger.info("✓ Created 4 payload indexes")

        # Verify collection
        collection_info = client.get_collection(collection_name)
        logger.info(f"Collection info: vectors_count={collection_info.vectors_count}")

        logger.info("✓ Qdrant initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize Qdrant: {e}", exc_info=True)
        return False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Initialize all databases for the trading system"
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help="Force re-initialization (WARNING: will delete existing data)"
    )
    parser.add_argument(
        '--skip-postgres',
        action='store_true',
        help="Skip PostgreSQL initialization"
    )
    parser.add_argument(
        '--skip-redis',
        action='store_true',
        help="Skip Redis initialization"
    )
    parser.add_argument(
        '--skip-qdrant',
        action='store_true',
        help="Skip Qdrant initialization"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(log_level="INFO", environment="dev")

    logger.info("=" * 60)
    logger.info("Trading System Database Initialization")
    logger.info("=" * 60)

    if args.force:
        logger.warning("⚠️  FORCE mode enabled - existing data will be deleted!")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Initialization cancelled")
            return

    # Load configuration
    try:
        config = get_config()
        logger.info(f"Environment: {config.environment}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return

    # Initialize databases
    results = {}

    if not args.skip_postgres:
        logger.info("\n" + "-" * 60)
        results['postgres'] = init_postgres(config.database_url, args.force)

    if not args.skip_redis:
        logger.info("\n" + "-" * 60)
        results['redis'] = init_redis(config.redis_url, args.force)

    if not args.skip_qdrant:
        logger.info("\n" + "-" * 60)
        results['qdrant'] = init_qdrant(config.qdrant_url, args.force)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Initialization Summary")
    logger.info("=" * 60)

    for db_name, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        logger.info(f"{db_name.upper()}: {status}")

    if all(results.values()):
        logger.info("\n✓ All databases initialized successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Start the system: python main.py")
        logger.info("2. Or run tests: pytest")
        return 0
    else:
        logger.error("\n✗ Some databases failed to initialize")
        logger.error("Please check the errors above and try again")
        return 1


if __name__ == "__main__":
    sys.exit(main())
