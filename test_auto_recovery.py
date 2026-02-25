#!/usr/bin/env python3
"""
Test script to verify auto-recovery of Qdrant collection.
This will delete the collection and then test if the cache proxy recreates it.
"""

import asyncio
import logging
from qdrant_client import AsyncQdrantClient

# Configuration
QDRANT_HOST = "buddha.alpine-musical.ts.net"
QDRANT_PORT = 6336  # gRPC port
COLLECTION_NAME = "text_embedding_cache_octen-0.6b-fp16"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def delete_collection():
    """Delete the collection."""
    client = AsyncQdrantClient(
        host=QDRANT_HOST,
        grpc_port=QDRANT_PORT,
        prefer_grpc=True,
        timeout=30.0,
    )

    try:
        logger.info(f"Deleting collection '{COLLECTION_NAME}'...")
        await client.delete_collection(collection_name=COLLECTION_NAME)
        logger.info(f"Successfully deleted collection '{COLLECTION_NAME}'.")
    except Exception as e:
        logger.error(f"Error deleting collection: {e}", exc_info=True)
        raise
    finally:
        await client.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("DELETING QDRANT COLLECTION FOR AUTO-RECOVERY TEST")
    logger.info("=" * 60)
    logger.info(f"Collection: {COLLECTION_NAME}")
    logger.info("=" * 60)

    asyncio.run(delete_collection())

    logger.info("=" * 60)
    logger.info("COLLECTION DELETED")
    logger.info("Now test the cache proxy with a request to verify auto-recovery")
    logger.info("=" * 60)
