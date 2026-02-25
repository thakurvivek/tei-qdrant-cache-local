# cache_proxy/qdrant_utils.py (Corrected - Convert UUID to str for client)
import logging
import uuid # Keep import
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.models import Distance, VectorParams
from qdrant_client.http.exceptions import UnexpectedResponse
from config import settings
from typing import List, Dict
import grpc

logger = logging.getLogger(__name__)

async_client = None

def get_qdrant_client() -> AsyncQdrantClient:
    """Gets the singleton async Qdrant client instance with optimized connection pool."""
    global async_client
    if async_client is None:
        logger.info(f"Initializing Async Qdrant client for host: {settings.qdrant_host}:{settings.qdrant_port} (gRPC)")
        async_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            grpc_port=settings.qdrant_port,  # Use grpc_port when prefer_grpc=True
            prefer_grpc=True,  # Use gRPC for better performance
            timeout=30.0,       # 30 second timeout
        )
    return async_client

async def ensure_collection_exists():
    """Ensures the configured Qdrant collection exists, creating it if necessary."""
    qdrant = get_qdrant_client()
    collection_name = settings.qdrant_collection
    logger.info(f"[QDRANT] Checking collection: {collection_name}")
    try:
        collection_info = await qdrant.get_collection(collection_name=collection_name)
        logger.info(f"[QDRANT] Collection '{collection_name}' exists | Points: {collection_info.points_count}")
    except (UnexpectedResponse, ValueError, grpc.aio.AioRpcError) as e:
        # Check if it's a NOT_FOUND error (HTTP 404 or gRPC NOT_FOUND)
        is_not_found = False
        if isinstance(e, UnexpectedResponse) and e.status_code == 404:
            is_not_found = True
        elif isinstance(e, grpc.aio.AioRpcError) and e.code() == grpc.StatusCode.NOT_FOUND:
            is_not_found = True
        elif "not found" in str(e).lower():
            is_not_found = True
        
        if is_not_found:
            logger.warning(f"Qdrant collection '{collection_name}' not found. Creating...")
            try:
                await qdrant.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=settings.embedding_dimension,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Successfully created Qdrant collection '{collection_name}'.")
            except Exception as create_e:
                logger.error(f"Failed to create Qdrant collection '{collection_name}': {create_e}", exc_info=True)
                raise
        else:
             logger.error(f"Unexpected error checking Qdrant collection '{collection_name}': {e}", exc_info=True)
             raise


# Accept list of UUIDs, return dict with UUID keys
async def retrieve_embeddings(point_ids: List[uuid.UUID]) -> Dict[uuid.UUID, List[float]]:
    """Retrieves points by ID asynchronously and returns a dict {UUID: vector}."""
    if not point_ids:
        return {}
    qdrant = get_qdrant_client()
    collection_name = settings.qdrant_collection
    
    # Helper function to perform the actual retrieval
    async def _do_retrieve():
        # *** Convert UUIDs to hex strings (without hyphens) for the client call ***
        ids_as_hex_strings = [pid.hex for pid in point_ids]
        logger.info(f"[QDRANT] Retrieving {len(point_ids)} points from collection '{collection_name}'")

        results = await qdrant.retrieve(
            collection_name=collection_name,
            ids=ids_as_hex_strings, # Pass list of hex strings
            with_payload=False,
            with_vectors=True
        )

        # *** Convert hex string IDs received back to UUIDs for the return dict ***
        found_embeddings = {}
        for point in results:
            if point.vector:
                try:
                    # Qdrant returns hex string IDs, convert back to UUID for consistency
                    point_uuid = uuid.UUID(hex=point.id)
                    found_embeddings[point_uuid] = point.vector
                except ValueError:
                    logger.warning(f"Received non-UUID hex string ID from Qdrant retrieve: {point.id}. Skipping.")

        logger.info(f"[QDRANT] Retrieved {len(found_embeddings)}/{len(point_ids)} points from collection '{collection_name}'")
        return found_embeddings
    
    # Try retrieval with auto-recovery for missing collection
    try:
        return await _do_retrieve()
    except (UnexpectedResponse, ValueError, grpc.aio.AioRpcError) as e:
        # Check if it's a NOT_FOUND error (collection missing)
        is_not_found = False
        if isinstance(e, UnexpectedResponse) and e.status_code == 404:
            is_not_found = True
        elif isinstance(e, grpc.aio.AioRpcError) and e.code() == grpc.StatusCode.NOT_FOUND:
            is_not_found = True
        elif "not found" in str(e).lower() and "collection" in str(e).lower():
            is_not_found = True
        
        if is_not_found:
            logger.warning(f"[QDRANT] Collection '{collection_name}' not found during retrieval. Auto-recreating...")
            try:
                await ensure_collection_exists()
                logger.info(f"[QDRANT] Collection recreated. Retrying retrieval...")
                return await _do_retrieve()
            except Exception as recreate_e:
                logger.error(f"[QDRANT] Failed to recreate collection: {recreate_e}", exc_info=True)
                return {}
        else:
            # Log the specific error for non-NOT_FOUND exceptions
            logger.error(f"Failed to retrieve embeddings from Qdrant for IDs {point_ids}: {e}", exc_info=True)
            return {}
    except Exception as e:
        # Log the specific error, including potentially the IDs that caused it if possible
        logger.error(f"Failed to retrieve embeddings from Qdrant for IDs {point_ids}: {e}", exc_info=True)
        return {}

# Accept list of UUIDs
async def store_embeddings(texts: List[str], vectors: List[List[float]], point_ids: List[uuid.UUID]):
    """Stores embeddings in Qdrant asynchronously using UUIDs (converted to str) as IDs."""
    if not texts or not vectors or not point_ids or len(texts) != len(vectors) or len(texts) != len(point_ids):
        logger.warning("Mismatch in lengths or empty lists provided to store_embeddings. Skipping.")
        return

    qdrant = get_qdrant_client()
    collection_name = settings.qdrant_collection

    points_to_upsert = []
    for text, vector, point_id_uuid in zip(texts, vectors, point_ids):
        try:
            # *** Convert UUID to hex string (without hyphens) when creating PointStruct ***
            point_struct = models.PointStruct(
                id=point_id_uuid.hex, # Pass ID as hex string without hyphens
                vector=vector,
                payload={"text": text}
            )
            points_to_upsert.append(point_struct)
        except Exception as e: # Catch potential errors during PointStruct creation
             logger.error(f"Failed to create PointStruct for ID {point_id_uuid}: {e}", exc_info=True)
             # Decide whether to skip this point or fail the batch
             continue # Skipping problematic point for now

    if not points_to_upsert:
        logger.warning("No valid points constructed for upsert after potential errors.")
        return

    # Helper function to perform the actual upsert
    async def _do_upsert():
        logger.info(f"[QDRANT] Upserting {len(points_to_upsert)} points to collection '{collection_name}'")
        response = await qdrant.upsert(
            collection_name=collection_name,
            points=points_to_upsert,
            wait=True  # Wait for operation to complete before returning
        )
        logger.info(f"Qdrant upsert response status: {response.status}")
        return response

    # Try upsert with auto-recovery for missing collection
    try:
        await _do_upsert()
    except (UnexpectedResponse, ValueError, grpc.aio.AioRpcError) as e:
        # Check if it's a NOT_FOUND error (collection missing)
        is_not_found = False
        if isinstance(e, UnexpectedResponse) and e.status_code == 404:
            is_not_found = True
        elif isinstance(e, grpc.aio.AioRpcError) and e.code() == grpc.StatusCode.NOT_FOUND:
            is_not_found = True
        elif "not found" in str(e).lower() and "collection" in str(e).lower():
            is_not_found = True
        
        if is_not_found:
            logger.warning(f"[QDRANT] Collection '{collection_name}' not found during upsert. Auto-recreating...")
            try:
                await ensure_collection_exists()
                logger.info(f"[QDRANT] Collection recreated. Retrying upsert...")
                await _do_upsert()
            except Exception as recreate_e:
                logger.error(f"[QDRANT] Failed to recreate collection: {recreate_e}", exc_info=True)
        else:
            # Log the specific error for non-NOT_FOUND exceptions
            logger.error(f"Failed to store embeddings in Qdrant: {e}", exc_info=True)
    except Exception as e:
        # Log the specific error
        logger.error(f"Failed to store embeddings in Qdrant: {e}", exc_info=True)


async def close_qdrant_client():
    """Closes the async Qdrant client connection."""
    global async_client
    if async_client:
        logger.info("Closing Async Qdrant client.")
        await async_client.close()
        async_client = None