"""
RunPod Deployment Automation for Personal SLMs
Handles containerization, orchestration, and lifecycle management
"""

import os
import json
import yaml
import docker
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import runpod
import kubernetes
from kubernetes import client, config
import boto3
import hashlib
import tempfile
import shutil
import logging


logger = logging.getLogger(__name__)


@dataclass
class DeploymentConfig:
    """Deployment configuration"""
    gpu_type: str = "NVIDIA GeForce RTX 3060"
    min_workers: int = 0
    max_workers: int = 1
    idle_timeout: int = 300  # 5 minutes
    disk_size_gb: int = 20
    memory_gb: int = 16
    container_registry: str = "ghcr.io/slm-vault"
    namespace: str = "slm-production"
    autoscale_metric: str = "gpu_utilization"
    autoscale_threshold: float = 0.7


class ContainerBuilder:
    """Build and push Docker containers for SLM deployment"""

    def __init__(self, registry: str):
        self.registry = registry
        self.docker_client = docker.from_env()

    def build_slm_container(self, user_id: str, model_path: Path) -> str:
        """Build container with user's SLM"""
        tag = f"{self.registry}/slm-{user_id}:{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Create temporary build directory
        build_dir = Path(tempfile.mkdtemp())

        try:
            # Copy model files
            model_dir = build_dir / "models"
            model_dir.mkdir()
            shutil.copytree(model_path, model_dir / "current")

            # Create Dockerfile
            dockerfile_content = self._generate_dockerfile()
            (build_dir / "Dockerfile").write_text(dockerfile_content)

            # Copy application code
            app_dir = build_dir / "app"
            app_dir.mkdir()
            self._copy_app_code(app_dir)

            # Create requirements.txt
            requirements = self._generate_requirements()
            (build_dir / "requirements.txt").write_text(requirements)

            # Build image
            logger.info(f"Building container for user {user_id}")
            image, logs = self.docker_client.images.build(
                path=str(build_dir),
                tag=tag,
                buildargs={
                    'USER_ID': user_id,
                    'MODEL_VERSION': self._get_model_version(model_path)
                }
            )

            # Push to registry
            logger.info(f"Pushing {tag} to registry")
            self.docker_client.images.push(tag)

            return tag

        finally:
            # Cleanup
            shutil.rmtree(build_dir)

    def _generate_dockerfile(self) -> str:
        """Generate optimized Dockerfile"""
        return """
FROM nvidia/cuda:12.1-runtime-ubuntu22.04

# Security updates
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    python3.11 python3-pip curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash -u 1001 slm-user

# Set up working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=slm-user:slm-user app/ .

# Copy model (will be encrypted)
COPY --chown=slm-user:slm-user models/ /models/

# Switch to non-root user
USER slm-user

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV MODEL_PATH=/models/current
ENV CUDA_VISIBLE_DEVICES=0

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 healthcheck.py

# Expose ports
EXPOSE 8080 8081

# Entry point
ENTRYPOINT ["python3", "server.py"]
"""

    def _generate_requirements(self) -> str:
        """Generate requirements.txt"""
        return """
torch==2.1.0
transformers==4.35.0
peft==0.6.0
accelerate==0.24.0
fastapi==0.104.0
uvicorn==0.24.0
redis==5.0.0
cryptography==41.0.0
numpy==1.24.3
pandas==2.0.3
scikit-learn==1.3.0
wandb==0.15.0
prometheus-client==0.18.0
runpod==1.2.0
"""

    def _copy_app_code(self, app_dir: Path):
        """Copy application code to build directory"""
        # Create inference server
        server_code = self._generate_inference_server()
        (app_dir / "server.py").write_text(server_code)

        # Create health check
        health_check = self._generate_health_check()
        (app_dir / "healthcheck.py").write_text(health_check)

        # Copy model loading utilities
        model_utils = self._generate_model_utils()
        (app_dir / "model_utils.py").write_text(model_utils)

    def _generate_inference_server(self) -> str:
        """Generate FastAPI inference server"""
        return '''
import os
import json
import torch
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict
import logging
from prometheus_client import Counter, Histogram, generate_latest
from model_utils import load_model, run_inference
from security import verify_token, decrypt_model


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Personal SLM Inference Server")
security = HTTPBearer()

# Metrics
inference_counter = Counter('slm_inference_total', 'Total inference requests')
inference_duration = Histogram('slm_inference_duration_seconds', 'Inference duration')


class InferenceRequest(BaseModel):
    prompt: str
    max_tokens: int = 128
    temperature: float = 0.7
    genetic_context: Optional[Dict] = None
    fitness_metrics: Optional[Dict] = None


class InferenceResponse(BaseModel):
    response: str
    tokens_generated: int
    inference_time: float
    model_version: str


# Load model on startup
model = None


@app.on_event("startup")
async def startup_event():
    global model
    model_path = os.getenv("MODEL_PATH", "/models/current")
    user_id = os.getenv("USER_ID")

    logger.info(f"Loading model for user {user_id}")
    model = load_model(model_path, user_id)
    logger.info("Model loaded successfully")


@app.post("/inference", response_model=InferenceResponse)
async def inference(
    request: InferenceRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Run inference on personal SLM"""
    # Verify token
    user_id = verify_token(credentials.credentials)

    # Track metrics
    inference_counter.inc()

    with inference_duration.time():
        response = run_inference(
            model,
            request.prompt,
            request.max_tokens,
            request.temperature,
            request.genetic_context,
            request.fitness_metrics
        )

    return InferenceResponse(**response)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "model_loaded": model is not None}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
'''

    def _generate_health_check(self) -> str:
        """Generate health check script"""
        return '''
import sys
import requests

try:
    response = requests.get("http://localhost:8080/health", timeout=5)
    if response.status_code == 200 and response.json()["status"] == "healthy":
        sys.exit(0)
    else:
        sys.exit(1)
except Exception as e:
    print(f"Health check failed: {e}")
    sys.exit(1)
'''

    def _generate_model_utils(self) -> str:
        """Generate model utility functions"""
        return '''
import torch
import json
import time
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer


def load_model(model_path: str, user_id: str):
    """Load and decrypt user's model"""
    # In production: decrypt model weights
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    return {"model": model, "tokenizer": tokenizer, "version": "1.0.0"}


def run_inference(
    model_dict: dict,
    prompt: str,
    max_tokens: int,
    temperature: float,
    genetic_context: dict = None,
    fitness_metrics: dict = None
):
    """Run model inference"""
    start_time = time.time()

    model = model_dict["model"]
    tokenizer = model_dict["tokenizer"]

    # Prepare input
    if genetic_context or fitness_metrics:
        # Inject multimodal context
        context = f"Genetic: {genetic_context}, Fitness: {fitness_metrics}"
        prompt = f"{context}\\n{prompt}"

    # Tokenize
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True)
    inputs = {k: v.cuda() for k, v in inputs.items()}

    # Generate
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=True
        )

    # Decode
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    response = response[len(prompt):].strip()

    inference_time = time.time() - start_time

    return {
        "response": response,
        "tokens_generated": len(outputs[0]) - len(inputs["input_ids"][0]),
        "inference_time": inference_time,
        "model_version": model_dict["version"]
    }
'''

    def _get_model_version(self, model_path: Path) -> str:
        """Extract model version from path"""
        # In production: read from model metadata
        return "1.0.0"


class RunPodDeployer:
    """Deploy and manage SLMs on RunPod"""

    def __init__(self, api_key: str):
        runpod.api_key = api_key
        self.deployments = {}

    def deploy_user_slm(
        self,
        user_id: str,
        container_image: str,
        config: DeploymentConfig
    ) -> Dict:
        """Deploy user's SLM to RunPod"""
        deployment_name = f"slm-{user_id}"

        # Check if deployment exists
        if deployment_name in self.deployments:
            logger.info(f"Updating existing deployment for {user_id}")
            return self.update_deployment(user_id, container_image)

        # Create new deployment
        deployment_config = {
            "name": deployment_name,
            "image": container_image,
            "gpu_type_id": self._get_gpu_type_id(config.gpu_type),
            "cloud_type": "SECURE",  # Use secure cloud
            "docker_args": "",
            "env": {
                "USER_ID": user_id,
                "MODEL_PATH": "/models/current",
                "REDIS_URL": os.getenv("REDIS_URL"),
                "LOG_LEVEL": "INFO"
            },
            "scaling_config": {
                "min_workers": config.min_workers,
                "max_workers": config.max_workers,
                "idle_timeout": config.idle_timeout
            },
            "disk_size_gb": config.disk_size_gb,
            "volume_mount_path": "/data"
        }

        logger.info(f"Creating RunPod deployment for {user_id}")

        try:
            # Create serverless endpoint
            endpoint = runpod.create_endpoint(**deployment_config)

            self.deployments[deployment_name] = {
                "endpoint_id": endpoint["id"],
                "endpoint_url": endpoint["endpoint_url"],
                "created_at": datetime.now().isoformat(),
                "status": "deploying"
            }

            # Wait for deployment to be ready
            self._wait_for_ready(endpoint["id"])

            return self.deployments[deployment_name]

        except Exception as e:
            logger.error(f"Failed to deploy for {user_id}: {e}")
            raise

    def update_deployment(self, user_id: str, new_image: str) -> Dict:
        """Update existing deployment with new model"""
        deployment_name = f"slm-{user_id}"

        if deployment_name not in self.deployments:
            raise ValueError(f"No deployment found for {user_id}")

        endpoint_id = self.deployments[deployment_name]["endpoint_id"]

        logger.info(f"Updating deployment {deployment_name} with {new_image}")

        # Update the endpoint
        runpod.update_endpoint(
            endpoint_id=endpoint_id,
            image=new_image
        )

        self.deployments[deployment_name]["updated_at"] = datetime.now().isoformat()
        self.deployments[deployment_name]["image"] = new_image

        return self.deployments[deployment_name]

    def scale_deployment(self, user_id: str, min_workers: int, max_workers: int):
        """Adjust deployment scaling"""
        deployment_name = f"slm-{user_id}"

        if deployment_name not in self.deployments:
            raise ValueError(f"No deployment found for {user_id}")

        endpoint_id = self.deployments[deployment_name]["endpoint_id"]

        runpod.update_endpoint_scaling(
            endpoint_id=endpoint_id,
            min_workers=min_workers,
            max_workers=max_workers
        )

        logger.info(f"Scaled {deployment_name} to {min_workers}-{max_workers} workers")

    def get_deployment_status(self, user_id: str) -> Dict:
        """Get deployment status and metrics"""
        deployment_name = f"slm-{user_id}"

        if deployment_name not in self.deployments:
            return {"status": "not_deployed"}

        endpoint_id = self.deployments[deployment_name]["endpoint_id"]

        # Get endpoint status
        endpoint = runpod.get_endpoint(endpoint_id)

        status = {
            "status": endpoint["status"],
            "workers": {
                "running": endpoint.get("workers_running", 0),
                "pending": endpoint.get("workers_pending", 0),
                "failed": endpoint.get("workers_failed", 0)
            },
            "metrics": {
                "requests_completed": endpoint.get("requests_completed", 0),
                "requests_failed": endpoint.get("requests_failed", 0),
                "avg_latency_ms": endpoint.get("avg_latency_ms", 0)
            },
            "endpoint_url": endpoint["endpoint_url"]
        }

        return status

    def delete_deployment(self, user_id: str):
        """Delete user's deployment"""
        deployment_name = f"slm-{user_id}"

        if deployment_name not in self.deployments:
            logger.warning(f"No deployment found for {user_id}")
            return

        endpoint_id = self.deployments[deployment_name]["endpoint_id"]

        logger.info(f"Deleting deployment for {user_id}")
        runpod.delete_endpoint(endpoint_id)

        del self.deployments[deployment_name]

    def _get_gpu_type_id(self, gpu_type: str) -> str:
        """Map GPU type to RunPod GPU ID"""
        gpu_map = {
            "NVIDIA GeForce RTX 3060": "gpu_rtx3060",
            "NVIDIA GeForce RTX 3070": "gpu_rtx3070",
            "NVIDIA GeForce RTX 3080": "gpu_rtx3080",
            "NVIDIA GeForce RTX 3090": "gpu_rtx3090",
            "NVIDIA GeForce RTX 4090": "gpu_rtx4090",
            "NVIDIA A100": "gpu_a100"
        }
        return gpu_map.get(gpu_type, "gpu_rtx3060")

    def _wait_for_ready(self, endpoint_id: str, timeout: int = 300):
        """Wait for deployment to be ready"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            endpoint = runpod.get_endpoint(endpoint_id)

            if endpoint["status"] == "ready":
                logger.info(f"Deployment {endpoint_id} is ready")
                return

            time.sleep(10)

        raise TimeoutError(f"Deployment {endpoint_id} failed to become ready")


class KubernetesOrchestrator:
    """Kubernetes orchestration for production deployments"""

    def __init__(self, kubeconfig_path: str = None):
        if kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            config.load_incluster_config()

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.batch_v1 = client.BatchV1Api()

    def create_slm_deployment(
        self,
        user_id: str,
        image: str,
        config: DeploymentConfig
    ) -> Dict:
        """Create Kubernetes deployment for SLM"""
        deployment_name = f"slm-{user_id}"

        # Deployment manifest
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(
                name=deployment_name,
                namespace=config.namespace,
                labels={"app": "slm", "user": user_id}
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"app": "slm", "user": user_id}
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={"app": "slm", "user": user_id}
                    ),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="slm",
                                image=image,
                                ports=[
                                    client.V1ContainerPort(container_port=8080)
                                ],
                                resources=client.V1ResourceRequirements(
                                    requests={"nvidia.com/gpu": "1"},
                                    limits={"nvidia.com/gpu": "1"}
                                ),
                                env=[
                                    client.V1EnvVar(name="USER_ID", value=user_id),
                                    client.V1EnvVar(
                                        name="MODEL_PATH",
                                        value="/models/current"
                                    )
                                ],
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="model-storage",
                                        mount_path="/models"
                                    )
                                ]
                            )
                        ],
                        volumes=[
                            client.V1Volume(
                                name="model-storage",
                                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name=f"slm-pvc-{user_id}"
                                )
                            )
                        ],
                        node_selector={"gpu": "true"}
                    )
                )
            )
        )

        # Create deployment
        self.apps_v1.create_namespaced_deployment(
            namespace=config.namespace,
            body=deployment
        )

        # Create service
        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=deployment_name,
                namespace=config.namespace
            ),
            spec=client.V1ServiceSpec(
                selector={"app": "slm", "user": user_id},
                ports=[
                    client.V1ServicePort(
                        port=8080,
                        target_port=8080,
                        name="http"
                    )
                ],
                type="ClusterIP"
            )
        )

        self.v1.create_namespaced_service(
            namespace=config.namespace,
            body=service
        )

        # Create HPA for autoscaling
        self._create_hpa(deployment_name, config)

        return {
            "deployment": deployment_name,
            "service": deployment_name,
            "namespace": config.namespace,
            "status": "created"
        }

    def _create_hpa(self, deployment_name: str, config: DeploymentConfig):
        """Create Horizontal Pod Autoscaler"""
        from kubernetes.client import V2HorizontalPodAutoscaler, V2HorizontalPodAutoscalerSpec

        hpa = V2HorizontalPodAutoscaler(
            api_version="autoscaling/v2",
            kind="HorizontalPodAutoscaler",
            metadata=client.V1ObjectMeta(
                name=f"{deployment_name}-hpa",
                namespace=config.namespace
            ),
            spec=V2HorizontalPodAutoscalerSpec(
                scale_target_ref=client.V2CrossVersionObjectReference(
                    api_version="apps/v1",
                    kind="Deployment",
                    name=deployment_name
                ),
                min_replicas=config.min_workers,
                max_replicas=config.max_workers,
                metrics=[
                    client.V2MetricSpec(
                        type="Resource",
                        resource=client.V2ResourceMetricSource(
                            name="nvidia.com/gpu",
                            target=client.V2MetricTarget(
                                type="Utilization",
                                average_utilization=int(config.autoscale_threshold * 100)
                            )
                        )
                    )
                ]
            )
        )

        autoscaling_v2 = client.AutoscalingV2Api()
        autoscaling_v2.create_namespaced_horizontal_pod_autoscaler(
            namespace=config.namespace,
            body=hpa
        )

    def create_training_job(
        self,
        user_id: str,
        image: str,
        config: DeploymentConfig
    ):
        """Create Kubernetes Job for model training"""
        job_name = f"slm-training-{user_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=config.namespace
            ),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="training",
                                image=image,
                                command=["python3", "train.py"],
                                resources=client.V1ResourceRequirements(
                                    requests={"nvidia.com/gpu": "1"},
                                    limits={"nvidia.com/gpu": "1"}
                                ),
                                env=[
                                    client.V1EnvVar(name="USER_ID", value=user_id),
                                    client.V1EnvVar(name="TRAINING_MODE", value="incremental")
                                ]
                            )
                        ],
                        restart_policy="OnFailure",
                        node_selector={"gpu": "true"}
                    )
                ),
                backoff_limit=3,
                ttl_seconds_after_finished=86400  # Clean up after 24 hours
            )
        )

        self.batch_v1.create_namespaced_job(
            namespace=config.namespace,
            body=job
        )

        logger.info(f"Created training job {job_name}")
        return job_name


if __name__ == "__main__":
    import time

    # Test container builder
    builder = ContainerBuilder("ghcr.io/slm-vault")

    # Test RunPod deployment
    if os.getenv("RUNPOD_API_KEY"):
        deployer = RunPodDeployer(os.getenv("RUNPOD_API_KEY"))

        # Deploy test model
        config = DeploymentConfig()
        deployment = deployer.deploy_user_slm(
            user_id="test_user_001",
            container_image="ghcr.io/slm-vault/test:latest",
            config=config
        )

        print(f"Deployment created: {deployment}")

        # Check status
        status = deployer.get_deployment_status("test_user_001")
        print(f"Deployment status: {status}")

    print("Deployment tests completed!")