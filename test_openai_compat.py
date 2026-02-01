#!/usr/bin/env python3
"""
Test script to verify OpenAI API compatibility of cache_proxy.
This script sends a request to the cache_proxy and validates the response format.
"""
import httpx
import json
import sys
import argparse

def test_openai_compatibility(url: str, model: str = "test-model"):
    """Test OpenAI API compatibility of the cache_proxy."""
    
    print(f"Testing OpenAI API compatibility at: {url}")
    print("-" * 60)
    
    # Test 1: Single text input
    print("\n[Test 1] Single text input")
    payload = {
        "input": "This is a test sentence for embedding.",
        "model": model
    }
    
    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("Response structure:")
            print(json.dumps(data, indent=2))
            
            # Validate OpenAI-compatible structure
            required_fields = ["object", "data", "model"]
            missing_fields = [f for f in required_fields if f not in data]
            
            if missing_fields:
                print(f"\n❌ FAIL: Missing required fields: {missing_fields}")
                return False
            
            # Check object field
            if data["object"] != "list":
                print(f"\n❌ FAIL: 'object' field should be 'list', got '{data['object']}'")
                return False
            
            # Check data field is a list
            if not isinstance(data["data"], list):
                print(f"\n❌ FAIL: 'data' field should be a list")
                return False
            
            # Check each embedding object
            for i, emb_obj in enumerate(data["data"]):
                emb_required = ["embedding", "index", "object"]
                emb_missing = [f for f in emb_required if f not in emb_obj]
                
                if emb_missing:
                    print(f"\n❌ FAIL: Embedding {i} missing fields: {emb_missing}")
                    return False
                
                if emb_obj["object"] != "embedding":
                    print(f"\n❌ FAIL: Embedding object 'object' should be 'embedding', got '{emb_obj['object']}'")
                    return False
                
                if not isinstance(emb_obj["embedding"], list):
                    print(f"\n❌ FAIL: 'embedding' field should be a list of floats")
                    return False
                
                if emb_obj["index"] != i:
                    print(f"\n❌ FAIL: Embedding index mismatch: expected {i}, got {emb_obj['index']}")
                    return False
            
            # Check usage field (optional but recommended)
            if "usage" in data:
                usage = data["usage"]
                if "prompt_tokens" not in usage or "total_tokens" not in usage:
                    print(f"\n❌ FAIL: 'usage' field missing required keys")
                    return False
            
            print("\n✅ PASS: Single text input test passed")
            
        else:
            print(f"\n❌ FAIL: Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"\n❌ FAIL: Exception occurred: {e}")
        return False
    
    # Test 2: Multiple text inputs
    print("\n[Test 2] Multiple text inputs")
    payload = {
        "input": ["First sentence.", "Second sentence.", "Third sentence."],
        "model": model
    }
    
    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if len(data["data"]) != 3:
                print(f"\n❌ FAIL: Expected 3 embeddings, got {len(data['data'])}")
                return False
            
            print("✅ PASS: Multiple text inputs test passed")
        else:
            print(f"\n❌ FAIL: Request failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ FAIL: Exception occurred: {e}")
        return False
    
    # Test 3: Duplicate input (cache hit test)
    print("\n[Test 3] Cache hit test (duplicate input)")
    payload = {
        "input": "This is a test sentence for embedding.",
        "model": model
    }
    
    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ PASS: Cache hit test passed")
        else:
            print(f"\n❌ FAIL: Request failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ FAIL: Exception occurred: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("All tests passed! ✅")
    print("=" * 60)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test OpenAI API compatibility of cache_proxy")
    parser.add_argument(
        "url",
        help="URL of the cache_proxy /v1/embeddings endpoint",
        default="http://localhost:8080/v1/embeddings"
    )
    parser.add_argument(
        "--model",
        help="Model name to use in requests",
        default="test-model"
    )
    
    args = parser.parse_args()
    
    success = test_openai_compatibility(args.url, args.model)
    sys.exit(0 if success else 1)
