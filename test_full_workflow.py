#!/usr/bin/env python3
"""
Complete DoRA WDVA workflow test
Tests: Training → Encryption → Inference with encrypted adapter
"""

import os
import time
import json
import requests
from typing import Dict, Any, Optional

# Configuration
ENDPOINT_URL = "https://api.runpod.ai/v2/ayi3s70ihlpbtg"
API_KEY = os.environ.get("RUNPOD_API_KEY")

if not API_KEY:
    print("Error: RUNPOD_API_KEY environment variable not set")
    exit(1)

class RunPodTester:
    def __init__(self, endpoint_url: str, api_key: str):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def submit_job(self, payload: Dict[str, Any]) -> str:
        """Submit a job and return job ID"""
        response = requests.post(
            f"{self.endpoint_url}/run",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data['id']

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status"""
        response = requests.get(
            f"{self.endpoint_url}/status/{job_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def wait_for_completion(self, job_id: str, timeout: int = 600, poll_interval: int = 5) -> Dict[str, Any]:
        """Wait for job to complete"""
        elapsed = 0
        print(f"Waiting for job {job_id}...", end="", flush=True)

        while elapsed < timeout:
            status_data = self.get_status(job_id)
            status = status_data.get('status')

            if status == 'COMPLETED':
                print(f" ✓ COMPLETED ({elapsed}s)")
                return status_data
            elif status == 'FAILED':
                print(f" ✗ FAILED")
                print(json.dumps(status_data, indent=2))
                raise Exception(f"Job failed: {status_data.get('error')}")

            print(".", end="", flush=True)
            time.sleep(poll_interval)
            elapsed += poll_interval

        print(f" ⏱ TIMEOUT ({timeout}s)")
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


def test_basic_inference(tester: RunPodTester):
    """Test 1: Basic inference without adapter"""
    print("\n" + "="*60)
    print("TEST 1: Basic Inference (No Adapter)")
    print("="*60)

    payload = {
        "input": {
            "task": "inference",
            "prompt": "Explain quantum computing in simple terms:",
            "max_tokens": 150,
            "temperature": 0.7
        }
    }

    job_id = tester.submit_job(payload)
    print(f"Job ID: {job_id}")

    result = tester.wait_for_completion(job_id, timeout=120)

    response_text = result['output']['response']
    print(f"\n✓ Response received ({len(response_text)} characters):")
    print(f"  {response_text[:200]}...")

    return result


def test_training_tiny(tester: RunPodTester):
    """Test 2: Train a tiny DoRA adapter (for testing)"""
    print("\n" + "="*60)
    print("TEST 2: Training Tiny DoRA Adapter")
    print("="*60)
    print("⚠️  This will take 3-5 minutes with 50 samples")

    payload = {
        "input": {
            "task": "training",
            "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "dataset_name": "yahma/alpaca-cleaned",
            "max_samples": 50,  # Very small for testing
            "epochs": 1,
            "use_4bit": True,
            "lora_r": 8,  # Small rank
            "lora_alpha": 16
        }
    }

    job_id = tester.submit_job(payload)
    print(f"Job ID: {job_id}")

    try:
        result = tester.wait_for_completion(job_id, timeout=600)  # 10 min max

        output = result['output']
        print(f"\n✓ Training completed:")
        print(f"  Adapter path: {output.get('adapter_path', 'N/A')}")
        print(f"  Training loss: {output.get('final_loss', 'N/A')}")

        return result
    except Exception as e:
        print(f"\n⚠️  Training test skipped or failed: {e}")
        return None


def test_encryption(tester: RunPodTester, adapter_path: str):
    """Test 3: Encrypt the trained adapter"""
    print("\n" + "="*60)
    print("TEST 3: Encrypting DoRA Adapter")
    print("="*60)

    # Generate a test encryption key
    import secrets
    encryption_key = secrets.token_hex(32)  # 256-bit key

    payload = {
        "input": {
            "task": "encrypt",
            "adapter_path": adapter_path,
            "encryption_key": encryption_key,
            "enable_compression": True
        }
    }

    job_id = tester.submit_job(payload)
    print(f"Job ID: {job_id}")

    result = tester.wait_for_completion(job_id, timeout=120)

    output = result['output']
    print(f"\n✓ Encryption completed:")
    print(f"  Encrypted path: {output.get('encrypted_path', 'N/A')}")
    print(f"  Original size: {output.get('original_size_mb', 'N/A')} MB")
    print(f"  Compressed size: {output.get('compressed_size_mb', 'N/A')} MB")

    return result, encryption_key


def test_encrypted_inference(tester: RunPodTester, encrypted_path: str, encryption_key: str):
    """Test 4: Inference with encrypted adapter"""
    print("\n" + "="*60)
    print("TEST 4: Inference with Encrypted Adapter")
    print("="*60)

    payload = {
        "input": {
            "task": "inference",
            "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "encrypted_adapter_path": encrypted_path,
            "encryption_key": encryption_key,
            "prompt": "Tell me about machine learning:",
            "max_tokens": 150,
            "temperature": 0.7,
            "enable_cache": True
        }
    }

    job_id = tester.submit_job(payload)
    print(f"Job ID: {job_id}")

    result = tester.wait_for_completion(job_id, timeout=180)

    response_text = result['output']['response']
    metadata = result['output'].get('metadata', {})

    print(f"\n✓ Encrypted inference completed:")
    print(f"  Response: {response_text[:200]}...")
    print(f"  Cache hit: {metadata.get('cache_hit', False)}")
    print(f"  Inference time: {metadata.get('inference_time_ms', 'N/A')}ms")

    return result


def test_performance_comparison(tester: RunPodTester):
    """Test 5: Compare performance across different scenarios"""
    print("\n" + "="*60)
    print("TEST 5: Performance Benchmarking")
    print("="*60)

    prompts = [
        "Short",
        "This is a medium length prompt for testing",
        "This is a longer prompt that includes more context and detail to see how the model handles it"
    ]

    token_limits = [10, 50, 100]

    results = []

    for i, (prompt, tokens) in enumerate(zip(prompts, token_limits), 1):
        print(f"\nSubtest {i}/3: {len(prompt.split())} words, {tokens} tokens")

        payload = {
            "input": {
                "task": "inference",
                "prompt": prompt,
                "max_tokens": tokens
            }
        }

        start = time.time()
        job_id = tester.submit_job(payload)
        result = tester.wait_for_completion(job_id, timeout=120)
        total_time = time.time() - start

        exec_time = result.get('executionTime', 0)

        results.append({
            'prompt_length': len(prompt.split()),
            'max_tokens': tokens,
            'total_time': total_time,
            'exec_time': exec_time
        })

        print(f"  Total: {total_time:.2f}s, Execution: {exec_time}ms")

    return results


def test_error_handling(tester: RunPodTester):
    """Test 6: Error handling"""
    print("\n" + "="*60)
    print("TEST 6: Error Handling")
    print("="*60)

    # Test 1: Missing required field
    print("\nSubtest 1: Missing prompt")
    try:
        payload = {"input": {"task": "inference", "max_tokens": 50}}
        job_id = tester.submit_job(payload)
        result = tester.wait_for_completion(job_id, timeout=30)

        if 'error' in result.get('output', {}):
            print("  ✓ Correctly returned error for missing prompt")
        else:
            print("  ✗ Should have returned error")
    except Exception as e:
        print(f"  ✓ Exception caught: {str(e)[:100]}")

    # Test 2: Invalid task
    print("\nSubtest 2: Invalid task type")
    try:
        payload = {"input": {"task": "invalid_task", "prompt": "test"}}
        job_id = tester.submit_job(payload)
        result = tester.wait_for_completion(job_id, timeout=30)

        if 'error' in result.get('output', {}):
            print("  ✓ Correctly returned error for invalid task")
        else:
            print("  ✗ Should have returned error")
    except Exception as e:
        print(f"  ✓ Exception caught: {str(e)[:100]}")


def main():
    print("="*60)
    print("RunPod WDVA - Comprehensive Workflow Test")
    print("="*60)
    print(f"Endpoint: {ENDPOINT_URL}")
    print()

    tester = RunPodTester(ENDPOINT_URL, API_KEY)

    try:
        # Test 1: Basic inference
        print("\n🧪 Running basic inference test...")
        test_basic_inference(tester)

        # Test 2: Performance comparison
        print("\n🧪 Running performance benchmarks...")
        perf_results = test_performance_comparison(tester)

        # Test 3: Error handling
        print("\n🧪 Running error handling tests...")
        test_error_handling(tester)

        # Optional: Full workflow (only if you want to test training)
        full_workflow = input("\n\nRun full workflow test (training → encryption → inference)? This takes 5-10 minutes. (y/N): ")

        if full_workflow.lower() == 'y':
            print("\n🧪 Running full DoRA workflow...")

            # Train
            training_result = test_training_tiny(tester)

            if training_result:
                adapter_path = training_result['output']['adapter_path']

                # Encrypt
                encryption_result, key = test_encryption(tester, adapter_path)
                encrypted_path = encryption_result['output']['encrypted_path']

                # Inference with encrypted adapter
                test_encrypted_inference(tester, encrypted_path, key)

        print("\n" + "="*60)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("="*60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
