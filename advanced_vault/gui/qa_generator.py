"""
Q&A Generator Service

Generates Q&A pairs from PDF text chunks using RunPod inference.
Formats output as Alpaca training dataset (JSONL).
"""

import logging
import requests
import json
import time
from typing import List, Dict, Any, Optional
import os

logger = logging.getLogger(__name__)


class QAGenerator:
    """
    Service for generating Q&A pairs from PDF chunks using RunPod inference.
    """
    
    def __init__(self, runpod_endpoint_id: Optional[str] = None, runpod_api_key: Optional[str] = None):
        """
        Initialize Q&A generator.
        
        Args:
            runpod_endpoint_id: RunPod endpoint ID for inference
            runpod_api_key: RunPod API key
        """
        self.endpoint_id = runpod_endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")
        self.api_key = runpod_api_key or os.getenv("RUNPOD_API_KEY")
        self.base_url = f"https://api.runpod.ai/v2/{self.endpoint_id}" if self.endpoint_id else None
        
        if not self.endpoint_id or not self.api_key:
            logger.warning("RunPod endpoint not configured. Q&A generation will be disabled.")
    
    def generate_qa_pairs(self, text_chunk: str, num_pairs: int = 3) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs from a text chunk.
        
        Args:
            text_chunk: Text to generate Q&A from
            num_pairs: Number of Q&A pairs to generate (default: 3)
            
        Returns:
            List of Q&A pairs in format: [{"instruction": "...", "output": "..."}]
        """
        if not self.endpoint_id or not self.api_key:
            logger.warning("RunPod not configured, skipping Q&A generation")
            return []
        
        # Limit chunk length to prevent exceeding model context (2048 tokens)
        # Rough estimate: ~4 chars per token, so limit to ~1200 chars for safety
        # This leaves room for prompt template (~200 tokens) + response (~500 tokens)
        max_chunk_length = 1200
        
        if len(text_chunk) > max_chunk_length:
            logger.warning(f"Text chunk too long ({len(text_chunk)} chars), truncating to {max_chunk_length}")
            text_chunk = text_chunk[:max_chunk_length] + "..."
        
        # Create prompt for Q&A generation
        prompt = f"""Generate {num_pairs} high-quality question-answer pairs from the following text.

Text:
{text_chunk}

Format each Q&A pair as JSON:
{{"instruction": "question here", "output": "answer here"}}

Return only valid JSON array with {num_pairs} Q&A pairs. Do not include markdown formatting or explanations."""

        try:
            # Submit inference job
            payload = {
                "input": {
                    "task": "inference",
                    "prompt": prompt,
                    "max_tokens": 512,
                    "temperature": 0.7,
                    "user_id": "qa_generator"  # Use system user_id for Q&A generation
                }
            }
            
            logger.debug(f"Submitting Q&A generation job for chunk ({len(prompt)} chars)")
            
            response = requests.post(
                f"{self.base_url}/run",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to submit Q&A generation job: {response.status_code} {response.text}")
                return []
            
            job_data = response.json()
            job_id = job_data.get('id')
            
            if not job_id:
                logger.error(f"No job ID in response: {job_data}")
                return []
            
            # Wait for completion
            result = self._wait_for_completion(job_id, timeout=120)
            
            if not result or "error" in result:
                logger.error(f"Q&A generation failed: {result}")
                return []
            
            # Parse response
            response_text = result.get("response", "")
            
            # Log response for debugging
            if response_text:
                logger.info(f"Received response (first 500 chars): {response_text[:500]}")
                logger.debug(f"Full response length: {len(response_text)} chars")
            else:
                logger.warning(f"Empty response from RunPod. Full result: {result}")
                return []
            
            # Try to extract JSON from response
            qa_pairs = self._parse_qa_response(response_text, num_pairs)
            
            if not qa_pairs:
                logger.warning(f"No Q&A pairs extracted from response for chunk (length: {len(response_text)} chars)")
                logger.debug(f"Response text: {response_text}")
            
            return qa_pairs
            
        except Exception as e:
            logger.error(f"Error generating Q&A pairs: {e}")
            return []
    
    def _wait_for_completion(self, job_id: str, timeout: int = 120) -> Optional[Dict[str, Any]]:
        """
        Wait for RunPod job to complete.
        
        Args:
            job_id: RunPod job ID
            timeout: Maximum wait time in seconds
            
        Returns:
            Job result or None if failed/timed out
        """
        start_time = time.time()
        poll_interval = 2
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.base_url}/status/{job_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    timeout=10
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get job status: {response.status_code}")
                    return None
                
                status_data = response.json()
                status = status_data.get("status")
                
                if status == "COMPLETED":
                    output = status_data.get("output", {})
                    # The response might be directly in output or nested in output.response
                    # Check both formats
                    if isinstance(output, dict):
                        response_text = output.get("response", "")
                        if not response_text and "text" in output:
                            response_text = output.get("text", "")
                        if not response_text:
                            # Sometimes the response is the output itself
                            logger.warning(f"Could not find response in output: {output}")
                            return None
                        
                        return {"response": response_text}
                    else:
                        # Output might be a string directly
                        return {"response": str(output)}
                elif status == "FAILED":
                    error = status_data.get("error", "Unknown error")
                    logger.error(f"Job failed: {error}")
                    return {"error": error}
                
                # Still processing
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error checking job status: {e}")
                return None
        
        logger.error(f"Job timed out after {timeout}s")
        return None
    
    def _parse_qa_response(self, response_text: str, expected_pairs: int) -> List[Dict[str, str]]:
        """
        Parse Q&A pairs from model response.
        
        Args:
            response_text: Raw response from model
            expected_pairs: Expected number of pairs
            
        Returns:
            List of Q&A pairs
        """
        qa_pairs = []
        
        # Try to extract JSON array
        try:
            # Find JSON array in response
            start_idx = response_text.find('[')
            end_idx = response_text.rfind(']') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                pairs = json.loads(json_str)
                
                for pair in pairs:
                    if isinstance(pair, dict) and "instruction" in pair and "output" in pair:
                        qa_pairs.append({
                            "instruction": pair["instruction"],
                            "output": pair["output"]
                        })
        except json.JSONDecodeError:
            # Fallback: try to extract pairs manually
            logger.warning("Failed to parse JSON, trying manual extraction")
            qa_pairs = self._extract_qa_manually(response_text)
        
        return qa_pairs[:expected_pairs]
    
    def _extract_qa_manually(self, text: str) -> List[Dict[str, str]]:
        """Fallback manual extraction of Q&A pairs."""
        qa_pairs = []
        
        # Look for Q: and A: patterns
        lines = text.split('\n')
        current_q = None
        current_a = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('Q:') or line.startswith('Question:'):
                if current_q and current_a:
                    qa_pairs.append({
                        "instruction": current_q,
                        "output": ' '.join(current_a)
                    })
                current_q = line.replace('Q:', '').replace('Question:', '').strip()
                current_a = []
            elif line.startswith('A:') or line.startswith('Answer:'):
                if current_q:
                    current_a.append(line.replace('A:', '').replace('Answer:', '').strip())
            elif current_q and line:
                current_a.append(line)
        
        if current_q and current_a:
            qa_pairs.append({
                "instruction": current_q,
                "output": ' '.join(current_a)
            })
        
        return qa_pairs
    
    def generate_from_chunks(self, text_chunks: List[str], user_id: str, num_pairs_per_chunk: int = 3) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs from multiple text chunks.
        
        Args:
            text_chunks: List of text chunks
            user_id: User ID for tracking
            num_pairs_per_chunk: Number of Q&A pairs per chunk
            
        Returns:
            List of all Q&A pairs in Alpaca format
        """
        all_qa_pairs = []
        
        logger.info(f"Generating Q&A pairs from {len(text_chunks)} chunks for user {user_id}")
        
        for i, chunk in enumerate(text_chunks):
            logger.info(f"Processing chunk {i+1}/{len(text_chunks)}")
            
            qa_pairs = self.generate_qa_pairs(chunk, num_pairs_per_chunk)
            
            if qa_pairs:
                all_qa_pairs.extend(qa_pairs)
                logger.info(f"Generated {len(qa_pairs)} Q&A pairs from chunk {i+1}")
            else:
                logger.warning(f"Failed to generate Q&A pairs from chunk {i+1}")
                # Log the chunk length for debugging
                logger.debug(f"Chunk {i+1} length: {len(chunk)} chars")
            
            # Small delay between chunks
            time.sleep(1)
        
        logger.info(f"Total Q&A pairs generated: {len(all_qa_pairs)}")
        return all_qa_pairs
    
    def save_to_jsonl(self, qa_pairs: List[Dict[str, str]], output_path: str):
        """
        Save Q&A pairs to JSONL file (Alpaca format).
        
        Args:
            qa_pairs: List of Q&A pairs
            output_path: Path to output JSONL file
        """
        with open(output_path, 'w') as f:
            for pair in qa_pairs:
                # Add input field (empty for Alpaca format)
                record = {
                    "instruction": pair.get("instruction", ""),
                    "input": "",  # Empty for simple Q&A
                    "output": pair.get("output", "")
                }
                f.write(json.dumps(record) + '\n')
        
        logger.info(f"Saved {len(qa_pairs)} Q&A pairs to {output_path}")


