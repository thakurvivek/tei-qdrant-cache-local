# cache_proxy/main.py (Updated with TEI Batching)
import logging
import hashlib
import time
import os # <--- IMPORT os module for environment variables
import orjson # Faster JSON
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse
import httpx
from contextlib import asynccontextmanager
from typing import List
import uuid # <--- IMPORT uuid library
import asyncio # For potential sleep between batches

# Use absolute imports
import schemas
import qdrant_utils
import config

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Define batch size for requests sent TO the TEI endpoint
# Adjust this based on model token limits and average chunk size
# Start with 12 and tune based on performance testing
TEI_REQUEST_BATCH_SIZE = int(os.getenv("TEI_REQUEST_BATCH_SIZE", "12"))

# Retry configuration for connection errors
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_BASE = float(os.getenv("RETRY_DELAY_BASE", "1.0"))  # Base delay in seconds
RETRY_DELAY_MAX = float(os.getenv("RETRY_DELAY_MAX", "10.0"))   # Max delay in seconds

# Delay between batches to give TEI service time to recover
BATCH_DELAY_SECONDS = float(os.getenv("BATCH_DELAY_SECONDS", "0.5"))

# --- Diagnostic Logging ---
logger.info("=" * 60)
logger.info("CACHE PROXY DIAGNOSTIC STARTUP")
logger.info("=" * 60)
logger.info(f"QDRANT_COLLECTION: {config.settings.qdrant_collection}")
logger.info(f"QDRANT_HOST: {config.settings.qdrant_host}:{config.settings.qdrant_port}")
logger.info(f"EMBEDDING_ENGINE: {config.settings.embedding_engine}")
logger.info(f"NGINX_UPSTREAM_URL: {config.settings.nginx_upstream_url}")
logger.info(f"APPEND_EMBED_PATH: {config.settings.append_embed_path}")
logger.info(f"TEI_REQUEST_BATCH_SIZE: {TEI_REQUEST_BATCH_SIZE}")
logger.info(f"EMBEDDING_DIMENSION: {config.settings.embedding_dimension}")
logger.info(f"MAX_RETRIES: {MAX_RETRIES}")
logger.info(f"RETRY_DELAY_BASE: {RETRY_DELAY_BASE}s")
logger.info(f"RETRY_DELAY_MAX: {RETRY_DELAY_MAX}s")
logger.info(f"BATCH_DELAY_SECONDS: {BATCH_DELAY_SECONDS}s")
logger.info("=" * 60)

# --- Hashing Function ---
def get_text_hash(text: str) -> uuid.UUID:
    """Calculates SHA256 hash and returns it as a UUID object.
    
    # A UUID is 128 bits (16 bytes) which requires 32 hex characters to represent.
    # The hash_hex string contains more characters than needed for a UUID, so we only
    # take the first 32 hex chars (16 bytes) to create a valid UUID object.
    # The remaining hash characters are truncated since UUIDs have a fixed size.
    """
    hasher = hashlib.new(config.settings.cache_hash_function)
    hasher.update(text.encode('utf-8'))
    hash_hex = hasher.hexdigest()
    # Create a UUID from the first 32 hex characters (16 bytes) of the hash
    return uuid.UUID(hex=hash_hex[:32])

# --- FastAPI Lifespan for Qdrant Init/Cleanup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI app starting up...")
    try:
        qdrant_utils.get_qdrant_client() # Initialize client connection pool
        await qdrant_utils.ensure_collection_exists() # Create collection if needed
        logger.info("Qdrant connection initialized and collection checked.")
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant during startup: {e}", exc_info=True)
        # raise # Optional: prevent startup if Qdrant is essential
    yield
    # Clean up resources on shutdown
    logger.info("FastAPI app shutting down...")
    await qdrant_utils.close_qdrant_client() # Close the async client


app = FastAPI(lifespan=lifespan, default_response_class=ORJSONResponse)
main = app  # Rename to 'main' for uvicorn -m flag
# Use a persistent httpx client for connection pooling with limits
http_client = httpx.AsyncClient(
    timeout=60.0,
    limits=httpx.Limits(
        max_keepalive_connections=20,  # Max connections to keep alive
        max_connections=50,            # Max total connections
        keepalive_expiry=30.0           # Expire keepalive after 30s
    )
)

@app.post("/v1/embeddings", response_model=dict)
async def create_embeddings(request: Request):
    start_time = time.monotonic()
    try:
        # Parse request body for logging
        body = await request.json()
        logger.info(f"Received request body: {body}")
        
        # Validate and parse using Pydantic
        embed_request = schemas.EmbedRequest(**body)
        original_inputs = [embed_request.get_inputs()] if isinstance(embed_request.get_inputs(), str) else embed_request.get_inputs()
        num_inputs = len(original_inputs)
        logger.info(f"Received request to embed {num_inputs} texts.")
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(status_code=422, detail=f"Invalid request: {str(e)}")

    if not original_inputs:
        return []

    # 1. Calculate Hashes (returns UUIDs)
    input_hashes: List[uuid.UUID] = [get_text_hash(text) for text in original_inputs]
    logger.info(f"Calculated UUIDs: {input_hashes}")
    logger.info(f"UUID hex values: {[h.hex for h in input_hashes]}")

    # 2. Check Cache (Qdrant)
    cache_check_start = time.monotonic()
    cached_embeddings_map = await qdrant_utils.retrieve_embeddings(input_hashes)
    cache_check_duration = time.monotonic() - cache_check_start
    logger.info(f"[CACHE] Collection: {config.settings.qdrant_collection} | Check took {cache_check_duration:.4f}s | Found {len(cached_embeddings_map)}/{num_inputs} items")

    # 3. Identify Hits and Misses
    final_embeddings = [None] * num_inputs
    missed_indices = [] # Store original indices of missed items
    missed_texts = []   # Store text of missed items
    missed_hashes: List[uuid.UUID] = [] # Store UUID of missed items

    for i, text_hash_uuid in enumerate(input_hashes):
        if text_hash_uuid in cached_embeddings_map:
            final_embeddings[i] = cached_embeddings_map[text_hash_uuid]
        else:
            missed_indices.append(i) # Track original index
            missed_texts.append(original_inputs[i])
            missed_hashes.append(text_hash_uuid)

    cache_hits = num_inputs - len(missed_texts)
    cache_hit_rate = (cache_hits / num_inputs * 100) if num_inputs > 0 else 0
    logger.info(f"[CACHE] Hits: {cache_hits} | Misses: {len(missed_texts)} | Hit Rate: {cache_hit_rate:.1f}%")

    # 4. Handle Misses (Call Nginx -> TEI) - WITH BATCHING AND RETRY LOGIC
    if missed_texts:
        logger.info(f"[SGLANG] Processing {len(missed_texts)} cache misses in batches of {TEI_REQUEST_BATCH_SIZE}...")
        logger.info(f"[SGLANG] Target URL: {config.settings.nginx_upstream_url}")
        all_batches_successful = True # Flag to track if any batch failed

        # Iterate through missed items in smaller batches
        for i in range(0, len(missed_texts), TEI_REQUEST_BATCH_SIZE):
            # Slice the data for the current batch
            batch_texts = missed_texts[i : i + TEI_REQUEST_BATCH_SIZE]
            batch_original_indices = missed_indices[i : i + TEI_REQUEST_BATCH_SIZE]
            batch_hashes_to_store = missed_hashes[i : i + TEI_REQUEST_BATCH_SIZE]

            if not batch_texts: continue # Should not happen, but safe check

            batch_num = i // TEI_REQUEST_BATCH_SIZE + 1
            logger.info(f"[SGLANG] Batch {batch_num}: {len(batch_texts)} texts | Indices: {batch_original_indices}")

            # Prepare payload for this specific batch
            # Different engines use different field names
            if config.settings.embedding_engine == "sglang":
                # sglang uses "input" instead of "inputs"
                tei_payload = {"input": batch_texts}
            else:
                # TEI, vllm, OpenAI use "inputs"
                tei_payload = {"inputs": batch_texts}
                # Only include normalize if provided (some engines may not support it)
                if embed_request.normalize is not None:
                    tei_payload["normalize"] = embed_request.normalize
                # Include model parameter if provided
                if embed_request.model is not None:
                    tei_payload["model"] = embed_request.model
                # Include encoding_format if provided (pass through from request)
                if embed_request.encoding_format is not None:
                    tei_payload["encoding_format"] = embed_request.encoding_format

            # Build URL based on engine configuration
            embed_url = config.settings.nginx_upstream_url
            if config.settings.append_embed_path:
                embed_url += "/v1/embeddings"

            # Retry logic with exponential backoff
            batch_succeeded = False
            last_error = None
            
            for retry_attempt in range(MAX_RETRIES):
                try:
                    inference_start = time.monotonic()
                    
                    # Log retry attempt if not first try
                    if retry_attempt > 0:
                        retry_delay = min(RETRY_DELAY_BASE * (2 ** retry_attempt), RETRY_DELAY_MAX)
                        logger.warning(f"[SGLANG] Batch {batch_num} retry {retry_attempt}/{MAX_RETRIES} after {retry_delay:.2f}s delay")
                        await asyncio.sleep(retry_delay)
                    
                    logger.info(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1}/{MAX_RETRIES} | URL: {embed_url}")
                    
                    # Send the smaller batch to the embedding endpoint
                    response = await http_client.post(embed_url, json=tei_payload)
                    response.raise_for_status() # Raise exception for 4xx/5xx errors
                    tei_result = response.json()

                    # Validate and extract embeddings from the response
                    # sglang returns {"data": [{"embedding": [...]}]
                    if isinstance(tei_result, dict) and 'data' in tei_result:
                         batch_new_embeddings = [item['embedding'] for item in tei_result['data']]
                    elif isinstance(tei_result, list):
                         batch_new_embeddings = tei_result
                    elif isinstance(tei_result, dict) and 'embeddings' in tei_result:
                         batch_new_embeddings = tei_result['embeddings']
                    else:
                         logger.error(f"Unexpected response structure from sglang for batch: {tei_result}")
                         last_error = f"Unexpected response structure: {tei_result}"
                         continue # Try next retry

                    inference_duration = time.monotonic() - inference_start
                    logger.info(f"[SGLANG] Batch {batch_num} completed in {inference_duration:.4f}s | {len(batch_texts)} texts | {inference_duration/len(batch_texts):.4f}s/text")

                    # Verify the number of embeddings received matches the number sent
                    if len(batch_new_embeddings) != len(batch_texts):
                        logger.error(f"Mismatch in batch: requested {len(batch_texts)}, received {len(batch_new_embeddings)}.")
                        last_error = f"Embedding count mismatch: requested {len(batch_texts)}, received {len(batch_new_embeddings)}"
                        continue # Try next retry

                    # 5. Populate Cache & Combine Results for this batch
                    # Store embeddings for this successful batch in Qdrant
                    store_start = time.monotonic()
                    await qdrant_utils.store_embeddings(batch_texts, batch_new_embeddings, batch_hashes_to_store)
                    store_duration = time.monotonic() - store_start
                    logger.info(f"[QDRANT] Stored {len(batch_texts)} embeddings in {store_duration:.4f}s | Collection: {config.settings.qdrant_collection}")

                    # Place the received embeddings into the correct positions in the final list
                    for j, original_index in enumerate(batch_original_indices):
                        final_embeddings[original_index] = batch_new_embeddings[j]

                    batch_succeeded = True
                    break # Success, exit retry loop

                except httpx.ConnectError as e:
                    # TCP connection failed - TEI service might be down or overloaded
                    last_error = f"TCP connection failed: {str(e)}"
                    logger.error(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1} TCP connection error: {e}")
                    # Will retry if attempts remain
                except httpx.TimeoutException as e:
                    # Request timed out
                    last_error = f"Request timeout: {str(e)}"
                    logger.error(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1} timeout error: {e}")
                    # Will retry if attempts remain
                except httpx.HTTPStatusError as e:
                    # HTTP error (4xx/5xx) - these are usually not retryable
                    last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                    logger.error(f"[SGLANG] Batch {batch_num} HTTP error {e.response.status_code}: {e.response.text[:200]}")
                    # Don't retry HTTP errors (client errors 4xx, server errors 5xx)
                    break
                except httpx.RequestError as e:
                    # Other request errors
                    last_error = f"Request error: {str(e)}"
                    logger.error(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1} request error: {e}", exc_info=True)
                    # Will retry if attempts remain
                except Exception as e:
                    # Unexpected errors
                    last_error = f"Unexpected error: {str(e)}"
                    logger.error(f"[SGLANG] Batch {batch_num} attempt {retry_attempt + 1} unexpected error: {e}", exc_info=True)
                    # Don't retry unexpected errors
                    break

            if not batch_succeeded:
                logger.error(f"[SGLANG] Batch {batch_num} FAILED after {MAX_RETRIES} attempts. Last error: {last_error}")
                all_batches_successful = False
            else:
                logger.info(f"[SGLANG] Batch {batch_num} SUCCEEDED")

            # Delay between batches to give TEI service time to recover
            if i + TEI_REQUEST_BATCH_SIZE < len(missed_texts):  # Only delay if there are more batches
                logger.debug(f"[SGLANG] Waiting {BATCH_DELAY_SECONDS}s before next batch...")
                await asyncio.sleep(BATCH_DELAY_SECONDS)

        # After processing all batches, check if any failed
        if not all_batches_successful:
            logger.warning("One or more batches failed during TEI processing. Final results might be incomplete.")
            # You could raise an HTTPException here if partial results are unacceptable
            # raise HTTPException(status_code=502, detail="Failed to process all embedding batches.")


    # 6. Return Combined Results (OpenAI-compatible format)
    total_duration = time.monotonic() - start_time
    logger.info(f"[SUMMARY] Total: {total_duration:.4f}s | Cache: {cache_check_duration:.4f}s | SGLANG: {total_duration - cache_check_duration:.4f}s | Items: {num_inputs}")

    # Final check: ensure all slots are filled (unless batches failed and we allowed partial results)
    if None in final_embeddings and all_batches_successful: # Check only if all batches were expected to succeed
         logger.error("Failed to populate all final embeddings despite successful batches. This indicates a logic error.")
         # Only raise 500 if we expected completion but didn't get it
         raise HTTPException(status_code=500, detail="Internal error: Failed to assemble all embeddings")
    elif None in final_embeddings and not all_batches_successful:
         logger.warning("Returning potentially incomplete results due to batch processing errors.")
         # Return partial results (items that failed will be None)
         # Or filter out None values if the client expects only successful results
         # return [emb for emb in final_embeddings if emb is not None] # Option: Return only non-None

    # If returning partial results is okay, just return the list which might contain None
    # If partial results are NOT okay, the exception should have been raised earlier.
    # Assuming partial results are okay for now if batches fail:
    # Replace None with a default vector or handle appropriately if needed before returning
    # For now, just return the list possibly containing None
    # A robust implementation might replace None with zeros or raise a specific error code.
    # Let's filter out None for now, assuming client wants only successful embeddings.
    successful_embeddings = [emb for emb in final_embeddings if emb is not None]
    if len(successful_embeddings) != num_inputs and all_batches_successful:
         # This case should ideally not happen if all_batches_successful is true
         logger.error("Logic error: All batches reported success, but final embeddings are incomplete.")
         raise HTTPException(status_code=500, detail="Internal error assembling embeddings.")
    elif len(successful_embeddings) != num_inputs and not all_batches_successful:
         logger.warning(f"Returning {len(successful_embeddings)} embeddings out of {num_inputs} requested due to errors.")
         # Decide on API contract: return partial list or error? Returning partial list for now.
         # Build OpenAI-compatible response for partial results
         data = [{"embedding": emb, "index": i, "object": "embedding"} for i, emb in enumerate(successful_embeddings)]
         return {
             "object": "list",
             "data": data,
             "model": embed_request.model or "default",
             "usage": {
                 "prompt_tokens": num_inputs,  # Approximate, could be improved with actual tokenization
                 "total_tokens": num_inputs
             }
         }

    # Build OpenAI-compatible response for full results
    data = [{"embedding": emb, "index": i, "object": "embedding"} for i, emb in enumerate(final_embeddings)]
    return {
        "object": "list",
        "data": data,
        "model": embed_request.model or "default",
        "usage": {
            "prompt_tokens": num_inputs,  # Approximate, could be improved with actual tokenization
            "total_tokens": num_inputs
        }
    }


@app.get("/health")
async def health_check():
    # Could add an async Qdrant health check here if needed
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Text Embedding Cache Proxy running (Async Qdrant)"}