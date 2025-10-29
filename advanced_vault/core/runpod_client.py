"""
RunPod DoRA Client

Simple client for making inference requests to RunPod endpoints with encrypted DoRA adapters.
"""

import time
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class RunPodDoRAClient:
    """
    Client for RunPod-based DoRA inference.

    Handles remote inference requests to RunPod serverless endpoints
    with encrypted DoRA adapters.
    """

    def __init__(
        self,
        endpoint_id: str,
        api_key: str,
        adapter_path: str,
        timeout: int = 60
    ):
        """
        Initialize RunPod client.

        Args:
            endpoint_id: RunPod endpoint ID
            api_key: RunPod API key
            adapter_path: Path to encrypted DoRA adapter (for reference)
            timeout: Request timeout in seconds
        """
        self.endpoint_id = endpoint_id
        self.api_key = api_key
        self.adapter_path = adapter_path
        self.timeout = timeout
        self.base_url = f"https://api.runpod.ai/v2/{endpoint_id}"

        logger.info(f"Initialized RunPod client for endpoint {endpoint_id}")

    def generate(self, prompt: str, max_new_tokens: int = 256) -> str:
        """
        Generate text using encrypted DoRA adapter on RunPod.

        Args:
            prompt: Input prompt
            max_new_tokens: Maximum tokens to generate

        Returns:
            Generated text

        Raises:
            Exception: If inference fails
        """
        # Submit inference job
        payload = {
            "input": {
                "task": "inference",
                "prompt": prompt,
                "max_new_tokens": max_new_tokens,
                "temperature": 0.7,
                "top_p": 0.9
            }
        }

        logger.debug(f"Submitting inference job: {prompt[:50]}...")

        response = requests.post(
            f"{self.base_url}/run",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=10
        )

        if response.status_code != 200:
            raise Exception(f"Failed to submit job: {response.status_code} {response.text}")

        job_id = response.json()['id']
        logger.debug(f"Job submitted: {job_id}")

        # Wait for completion
        return self._wait_for_result(job_id)

    def _wait_for_result(self, job_id: str) -> str:
        """
        Wait for job completion and return result.

        Args:
            job_id: RunPod job ID

        Returns:
            Generated text

        Raises:
            Exception: If job fails or times out
        """
        start_time = time.time()

        while time.time() - start_time < self.timeout:
            response = requests.get(
                f"{self.base_url}/status/{job_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )

            if response.status_code != 200:
                raise Exception(f"Failed to check status: {response.status_code}")

            status_data = response.json()
            status = status_data.get('status')

            if status == 'COMPLETED':
                output = status_data.get('output', {})
                return output.get('generated_text', '')

            elif status == 'FAILED':
                error = status_data.get('error', 'Unknown error')
                raise Exception(f"Job failed: {error}")

            # Still running, wait a bit
            time.sleep(1)

        raise Exception(f"Job timed out after {self.timeout}s")

    def close(self):
        """Cleanup (no-op for RunPod client)."""
        logger.debug("RunPod client closed")
