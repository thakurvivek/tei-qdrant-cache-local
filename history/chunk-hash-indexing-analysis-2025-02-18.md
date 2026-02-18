# Chunk Hash Indexing Analysis - Understanding Hash Storage in Qdrant

## Metadata
- **Created**: 2025-02-18
- **Project**: sglang-embedding-cache
- **Component**: cache_proxy, gradio_code_search
- **Tags**: qdrant, hashing, indexing, cache, embeddings
- **Related Gists**: None

## Summary
Analyzed the codebase to determine whether chunk hashes are stored inside the payload/data that gets indexed in Qdrant. Discovered that there are two separate systems with different approaches: the Cache Proxy uses hashes as point IDs (not in payload), while the Code Search system uses random UUIDs with no hashing at all.

## Problem Statement
User asked: "Help me understand if the hash of all the chunks also gets inside data that gets indexed"

## Environment
- **OS**: Linux 6.8
- **Shell**: /bin/bash
- **User**: vvek
- **Working Directory**: /home/vvek/deep/sglang-embedding-cache-setup/git/sglang-embedding-cache
- **Key Versions**: Python, FastAPI, Qdrant Client
- **Constraints**: Debug mode active

## Timeline
- 2025-02-18T07:22:43Z: User asks about chunk hash storage in indexed data
- 2025-02-18T07:23:12Z: Initial code search for "chunk hash indexed data payload qdrant"
- 2025-02-18T07:23:18Z: Read cache_proxy/main.py and qdrant_utils.py
- 2025-02-18T07:23:39Z: Read gradio_code_search/indexing.py
- 2025-02-18T07:23:54Z: Read gradio_code_search/qdrant_logic.py
- 2025-02-18T17:27:11Z: User requests to run the "learn" skill
- 2025-02-18T17:27:36Z: Skill "learn" not found initially
- 2025-02-18T17:27:42Z: Found skill at /home/vvek/.roo/skills/learn/SKILL.md
- 2025-02-18T17:27:50Z: Read skill definition and begin documentation

## Thought Process

### Initial Hypothesis Generation
I considered 5-7 possible sources of how hashes might be stored:
1. Hash stored in payload as a field
2. Hash used as point ID only
3. Hash stored in both payload and ID
4. No hash used at all (random IDs)
5. Hash used for indexing but not storage
6. Hash used for deduplication only
7. Different systems with different approaches

### Investigation Approach
1. Searched for "chunk hash indexed data payload qdrant" to find relevant code
2. Examined `cache_proxy/main.py` to understand the hashing function and flow
3. Examined `cache_proxy/qdrant_utils.py` to see how data is stored/retrieved
4. Examined `gradio_code_search/indexing.py` to understand the code search indexing
5. Examined `gradio_code_search/qdrant_logic.py` to see Qdrant operations

### Key Findings

**Cache Proxy System:**
- Hash is calculated using SHA256 or MD5 (configurable)
- Hash is converted to UUID format (first 32 hex chars)
- Hash is used as the **point ID** in Qdrant
- Payload contains ONLY: `{"text": text}`
- Retrieval uses `with_payload=False` - only vectors are retrieved

**Code Search System:**
- No hash calculation at all
- Uses random UUIDs as point IDs: `str(uuid.uuid4())`
- Payload contains: `{"file_path", "start_line", "end_line", "text"}`
- No hash-based deduplication

### Distillation to Most Likely Sources
The analysis revealed two distinct systems with different approaches:
1. **Cache Proxy**: Hash as ID, not in payload
2. **Code Search**: No hash, random UUIDs

No logs were needed as the code analysis was sufficient to answer the question definitively.

## Solution

**Answer: No, chunk hashes are NOT stored inside the indexed data payload.**

### Cache Proxy System Details
```python
# In qdrant_utils.py, line 101-105:
point_struct = models.PointStruct(
    id=point_id_uuid.hex,  # ← Hash is the POINT ID
    vector=vector,
    payload={"text": text}  # ← Payload contains ONLY text, NO hash
)
```

### Retrieval Details
```python
# In qdrant_utils.py, line 64-66:
results = await qdrant.retrieve(
    collection_name=collection_name,
    ids=ids_as_hex_strings,
    with_payload=False,  # ← Payload NOT retrieved
    with_vectors=True
)
```

### Code Search System Details
```python
# In indexing.py, line 117:
PointStruct(id=str(uuid.uuid4()), vector=emb, payload=meta)
# ↑ Random UUID as ID, payload contains metadata (file_path, start_line, end_line, text)
```

## Changes Made
No code changes were made. This was purely an analysis task.

## All User Messages
1. "Help me understand if the hash of all the chunks also gets inside data that gets indexed"
2. "lets run the learn skill"
3. "use the skill named learn"

## Learnings

### Technical Insights
1. **Hash as ID Pattern**: The cache proxy uses content-based hashing (SHA256/MD5) to create deterministic point IDs. This enables efficient cache lookups without storing the hash in the payload.

2. **Payload Optimization**: The cache proxy retrieves only vectors (`with_payload=False`) for performance, since the original text isn't needed for cache hits.

3. **Dual System Architecture**: The codebase contains two separate systems with different design goals:
   - Cache Proxy: Optimized for deduplication and fast lookups
   - Code Search: Optimized for semantic search with rich metadata

4. **UUID Truncation**: The hash function truncates SHA256 (64 hex chars) to 32 hex chars to fit UUID format, which is a 128-bit identifier.

### Process Insights
1. **Code Search Strategy**: Using `codebase_search` with multiple queries helped find relevant files quickly.

2. **Systematic Analysis**: Reading files in logical order (main → utils → indexing → qdrant_logic) provided a complete picture of the data flow.

3. **No Logging Needed**: For this type of architectural question, code analysis was sufficient - no runtime debugging was required.

### Edge Cases
1. **Hash Collision Risk**: Truncating SHA256 to 32 hex chars (128 bits) still provides extremely low collision probability for typical use cases.

2. **Different Hash Functions**: The system supports both SHA256 and MD5 via configuration (`cache_hash_function`).

## Optional Next Step
None - the analysis task was completed successfully.

## Open Questions / Follow-up Items
None

## References
- Qdrant Client Documentation: PointStruct, payload, and ID handling
- Python UUID module: UUID creation from hex strings
- Hashlib module: SHA256 and MD5 hashing functions
