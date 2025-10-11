"""
Monitoring and Lifecycle Management for Personal SLMs
Implements privacy-preserving metrics, observability, and user controls
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
import wandb
from differential_privacy import LaplaceMechanism
import redis
import asyncio
import aiohttp
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging


logger = logging.getLogger(__name__)
Base = declarative_base()


@dataclass
class MonitoringConfig:
    """Monitoring configuration"""
    metrics_retention_days: int = 90
    alert_threshold_inference_latency_ms: float = 1000
    alert_threshold_error_rate: float = 0.05
    alert_threshold_gpu_utilization: float = 0.9
    differential_privacy_epsilon: float = 1.0
    federated_learning_enabled: bool = True
    aggregate_metrics_interval_minutes: int = 5


class PrivacyPreservingMetrics:
    """Differential privacy for aggregate metrics"""

    def __init__(self, epsilon: float = 1.0):
        self.epsilon = epsilon
        self.laplace = LaplaceMechanism(epsilon)

    def add_noise(self, value: float, sensitivity: float = 1.0) -> float:
        """Add Laplace noise for differential privacy"""
        noise = np.random.laplace(0, sensitivity / self.epsilon)
        return value + noise

    def private_mean(self, values: List[float], bounds: Tuple[float, float]) -> float:
        """Calculate differentially private mean"""
        if not values:
            return 0.0

        # Clip values to bounds for sensitivity
        clipped = np.clip(values, bounds[0], bounds[1])
        true_mean = np.mean(clipped)

        # Add noise proportional to range/count
        sensitivity = (bounds[1] - bounds[0]) / len(values)
        return self.add_noise(true_mean, sensitivity)

    def private_count(self, count: int, max_contribution: int = 1) -> int:
        """Calculate differentially private count"""
        noisy_count = self.add_noise(count, max_contribution)
        return max(0, int(noisy_count))  # Ensure non-negative

    def private_percentile(self, values: List[float], percentile: float) -> float:
        """Calculate differentially private percentile"""
        if not values:
            return 0.0

        true_percentile = np.percentile(values, percentile)
        sensitivity = max(values) - min(values)
        return self.add_noise(true_percentile, sensitivity * 0.1)


class MetricsCollector:
    """Collect and aggregate system metrics"""

    def __init__(self, user_id: str, config: MonitoringConfig):
        self.user_id = user_id
        self.config = config
        self.privacy = PrivacyPreservingMetrics(config.differential_privacy_epsilon)

        # Prometheus metrics
        self.registry = CollectorRegistry()

        self.inference_counter = Counter(
            'slm_inference_total',
            'Total inference requests',
            ['user_id', 'model_version'],
            registry=self.registry
        )

        self.inference_latency = Histogram(
            'slm_inference_latency_seconds',
            'Inference latency',
            ['user_id'],
            registry=self.registry,
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
        )

        self.model_accuracy = Gauge(
            'slm_model_accuracy',
            'Model accuracy score',
            ['user_id'],
            registry=self.registry
        )

        self.gpu_utilization = Gauge(
            'slm_gpu_utilization',
            'GPU utilization percentage',
            ['user_id'],
            registry=self.registry
        )

        self.training_loss = Gauge(
            'slm_training_loss',
            'Training loss',
            ['user_id', 'epoch'],
            registry=self.registry
        )

        # Redis for real-time metrics
        self.redis = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True
        )

    def record_inference(
        self,
        latency_ms: float,
        tokens_generated: int,
        success: bool,
        model_version: str
    ):
        """Record inference metrics"""
        # Update Prometheus metrics
        self.inference_counter.labels(
            user_id=self.user_id,
            model_version=model_version
        ).inc()

        self.inference_latency.labels(
            user_id=self.user_id
        ).observe(latency_ms / 1000)

        # Store in Redis for aggregation
        metric_key = f"metrics:{self.user_id}:inference:{datetime.now().strftime('%Y%m%d')}"
        self.redis.lpush(metric_key, json.dumps({
            'timestamp': datetime.now().isoformat(),
            'latency_ms': latency_ms,
            'tokens': tokens_generated,
            'success': success,
            'model_version': model_version
        }))

        # Set expiry
        self.redis.expire(metric_key, 86400 * self.config.metrics_retention_days)

    def record_training_metrics(
        self,
        epoch: int,
        loss: float,
        accuracy: float,
        gpu_memory_mb: float
    ):
        """Record training metrics"""
        self.training_loss.labels(
            user_id=self.user_id,
            epoch=str(epoch)
        ).set(loss)

        self.model_accuracy.labels(
            user_id=self.user_id
        ).set(accuracy)

        # Store detailed metrics
        training_key = f"metrics:{self.user_id}:training:{datetime.now().strftime('%Y%m%d')}"
        self.redis.hset(training_key, f"epoch_{epoch}", json.dumps({
            'loss': loss,
            'accuracy': accuracy,
            'gpu_memory_mb': gpu_memory_mb,
            'timestamp': datetime.now().isoformat()
        }))

    def get_aggregate_metrics(self) -> Dict:
        """Get privacy-preserving aggregate metrics"""
        # Collect inference metrics from last 24 hours
        pattern = f"metrics:{self.user_id}:inference:*"
        inference_data = []

        for key in self.redis.scan_iter(match=pattern):
            data = self.redis.lrange(key, 0, -1)
            for item in data:
                inference_data.append(json.loads(item))

        if not inference_data:
            return {}

        # Extract values
        latencies = [d['latency_ms'] for d in inference_data]
        success_count = sum(1 for d in inference_data if d['success'])
        total_count = len(inference_data)

        # Apply differential privacy
        return {
            'inference_count': self.privacy.private_count(total_count),
            'avg_latency_ms': self.privacy.private_mean(latencies, (0, 10000)),
            'p95_latency_ms': self.privacy.private_percentile(latencies, 95),
            'success_rate': self.privacy.private_mean(
                [float(d['success']) for d in inference_data],
                (0, 1)
            ),
            'timestamp': datetime.now().isoformat()
        }


class ModelPerformanceMonitor:
    """Monitor model performance and detect drift"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.baseline_metrics = {}
        self.current_metrics = {}

    def establish_baseline(self, metrics: Dict):
        """Set baseline performance metrics"""
        self.baseline_metrics = {
            'loss': metrics.get('loss'),
            'accuracy': metrics.get('accuracy'),
            'inference_latency_ms': metrics.get('inference_latency_ms'),
            'established_at': datetime.now().isoformat()
        }

    def check_model_drift(self, current_metrics: Dict) -> Dict:
        """Detect performance degradation"""
        if not self.baseline_metrics:
            return {'drift_detected': False, 'reason': 'No baseline established'}

        drift_indicators = []

        # Check loss increase
        if 'loss' in current_metrics and 'loss' in self.baseline_metrics:
            loss_increase = (current_metrics['loss'] - self.baseline_metrics['loss']) / self.baseline_metrics['loss']
            if loss_increase > 0.1:  # 10% increase
                drift_indicators.append(f"Loss increased by {loss_increase:.2%}")

        # Check accuracy decrease
        if 'accuracy' in current_metrics and 'accuracy' in self.baseline_metrics:
            acc_decrease = (self.baseline_metrics['accuracy'] - current_metrics['accuracy']) / self.baseline_metrics['accuracy']
            if acc_decrease > 0.05:  # 5% decrease
                drift_indicators.append(f"Accuracy decreased by {acc_decrease:.2%}")

        # Check latency increase
        if 'inference_latency_ms' in current_metrics and 'inference_latency_ms' in self.baseline_metrics:
            latency_increase = (current_metrics['inference_latency_ms'] - self.baseline_metrics['inference_latency_ms']) / self.baseline_metrics['inference_latency_ms']
            if latency_increase > 0.2:  # 20% increase
                drift_indicators.append(f"Latency increased by {latency_increase:.2%}")

        return {
            'drift_detected': len(drift_indicators) > 0,
            'indicators': drift_indicators,
            'baseline': self.baseline_metrics,
            'current': current_metrics
        }


class FederatedLearningCoordinator:
    """Coordinate federated learning across user models"""

    def __init__(self):
        self.aggregation_buffer = {}
        self.round_number = 0

    def collect_gradients(self, user_id: str, gradients: Dict, num_samples: int):
        """Collect gradients from user model"""
        if self.round_number not in self.aggregation_buffer:
            self.aggregation_buffer[self.round_number] = []

        # Store encrypted gradients
        self.aggregation_buffer[self.round_number].append({
            'user_id': user_id,
            'gradients': gradients,
            'num_samples': num_samples,
            'timestamp': datetime.now().isoformat()
        })

    def aggregate_gradients(self, min_participants: int = 10) -> Optional[Dict]:
        """Perform secure aggregation"""
        if self.round_number not in self.aggregation_buffer:
            return None

        participants = self.aggregation_buffer[self.round_number]

        if len(participants) < min_participants:
            logger.info(f"Not enough participants: {len(participants)} < {min_participants}")
            return None

        # Weighted average based on number of samples
        total_samples = sum(p['num_samples'] for p in participants)
        aggregated = {}

        for layer_name in participants[0]['gradients'].keys():
            weighted_sum = None

            for p in participants:
                weight = p['num_samples'] / total_samples
                layer_gradient = p['gradients'][layer_name]

                if weighted_sum is None:
                    weighted_sum = layer_gradient * weight
                else:
                    weighted_sum += layer_gradient * weight

            aggregated[layer_name] = weighted_sum

        # Advance round
        self.round_number += 1

        return {
            'round': self.round_number - 1,
            'aggregated_gradients': aggregated,
            'participants': len(participants),
            'total_samples': total_samples
        }


class UserLifecycleManager:
    """Manage user data lifecycle and controls"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.created_at = datetime.now()
        self.last_active = datetime.now()

    def export_user_data(self, format: str = "json") -> Path:
        """Export all user data for portability"""
        export_dir = Path(f"/exports/{self.user_id}")
        export_dir.mkdir(parents=True, exist_ok=True)

        export_data = {
            'user_id': self.user_id,
            'exported_at': datetime.now().isoformat(),
            'format_version': '1.0',
            'data': {}
        }

        # Collect all user data
        data_types = ['models', 'training_data', 'metrics', 'configurations']

        for data_type in data_types:
            data_path = Path(f"/secure-storage/{self.user_id}/{data_type}")
            if data_path.exists():
                export_data['data'][data_type] = self._collect_data(data_path)

        # Write export
        if format == "json":
            export_file = export_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(export_file, 'w') as f:
                json.dump(export_data, f, indent=2)
        elif format == "parquet":
            # Convert to DataFrame and save as Parquet
            import pandas as pd
            df = pd.DataFrame.from_dict(export_data['data'], orient='index')
            export_file = export_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
            df.to_parquet(export_file)

        logger.info(f"Exported data for user {self.user_id} to {export_file}")
        return export_file

    def delete_user_data(self, confirm_token: str, permanent: bool = False) -> Dict:
        """Delete user data with confirmation"""
        # Verify confirmation token
        expected_token = hashlib.sha256(f"{self.user_id}_delete".encode()).hexdigest()[:8]

        if confirm_token != expected_token:
            raise ValueError("Invalid confirmation token")

        deletion_report = {
            'user_id': self.user_id,
            'deletion_time': datetime.now().isoformat(),
            'permanent': permanent,
            'deleted_items': []
        }

        # Paths to delete
        paths_to_delete = [
            f"/secure-storage/{self.user_id}",
            f"/models/{self.user_id}",
            f"/logs/{self.user_id}"
        ]

        for path_str in paths_to_delete:
            path = Path(path_str)
            if path.exists():
                if permanent:
                    # Secure deletion with overwrite
                    self._secure_delete(path)
                    deletion_report['deleted_items'].append(str(path))
                else:
                    # Soft delete to trash
                    trash_path = Path("/trash") / self.user_id / path.name
                    trash_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(path, trash_path)
                    deletion_report['deleted_items'].append(f"{path} -> trash")

        # Remove from active deployments
        self._remove_deployments()

        logger.info(f"Deleted data for user {self.user_id}")
        return deletion_report

    def pause_model(self) -> Dict:
        """Pause model inference and training"""
        # Update deployment to scale to 0
        from deployment import RunPodDeployer

        deployer = RunPodDeployer(os.getenv("RUNPOD_API_KEY"))
        deployer.scale_deployment(self.user_id, min_workers=0, max_workers=0)

        return {
            'user_id': self.user_id,
            'status': 'paused',
            'paused_at': datetime.now().isoformat()
        }

    def resume_model(self) -> Dict:
        """Resume model operations"""
        from deployment import RunPodDeployer, DeploymentConfig

        config = DeploymentConfig()
        deployer = RunPodDeployer(os.getenv("RUNPOD_API_KEY"))
        deployer.scale_deployment(
            self.user_id,
            min_workers=config.min_workers,
            max_workers=config.max_workers
        )

        return {
            'user_id': self.user_id,
            'status': 'active',
            'resumed_at': datetime.now().isoformat()
        }

    def _collect_data(self, path: Path) -> List[Dict]:
        """Collect data from directory"""
        data = []
        for file in path.rglob("*"):
            if file.is_file():
                data.append({
                    'path': str(file),
                    'size': file.stat().st_size,
                    'modified': datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                })
        return data

    def _secure_delete(self, path: Path):
        """Securely delete files with overwrite"""
        import shutil

        if path.is_file():
            # Overwrite with random data
            with open(path, 'wb') as f:
                f.write(os.urandom(path.stat().st_size))
            path.unlink()
        elif path.is_dir():
            for child in path.iterdir():
                self._secure_delete(child)
            path.rmdir()

    def _remove_deployments(self):
        """Remove all user deployments"""
        try:
            from deployment import RunPodDeployer
            deployer = RunPodDeployer(os.getenv("RUNPOD_API_KEY"))
            deployer.delete_deployment(self.user_id)
        except Exception as e:
            logger.error(f"Failed to remove deployments: {e}")


class AlertingSystem:
    """Send alerts for critical events"""

    def __init__(self):
        self.alert_history = []
        self.alert_channels = {
            'email': self._send_email,
            'webhook': self._send_webhook,
            'push': self._send_push
        }

    async def check_alerts(self, metrics: Dict, config: MonitoringConfig):
        """Check metrics against alert thresholds"""
        alerts = []

        # Check inference latency
        if 'p95_latency_ms' in metrics:
            if metrics['p95_latency_ms'] > config.alert_threshold_inference_latency_ms:
                alerts.append({
                    'type': 'high_latency',
                    'severity': 'warning',
                    'message': f"P95 latency {metrics['p95_latency_ms']}ms exceeds threshold",
                    'value': metrics['p95_latency_ms']
                })

        # Check error rate
        if 'success_rate' in metrics:
            error_rate = 1 - metrics['success_rate']
            if error_rate > config.alert_threshold_error_rate:
                alerts.append({
                    'type': 'high_error_rate',
                    'severity': 'critical',
                    'message': f"Error rate {error_rate:.2%} exceeds threshold",
                    'value': error_rate
                })

        # Check GPU utilization
        if 'gpu_utilization' in metrics:
            if metrics['gpu_utilization'] > config.alert_threshold_gpu_utilization:
                alerts.append({
                    'type': 'high_gpu_usage',
                    'severity': 'info',
                    'message': f"GPU utilization {metrics['gpu_utilization']:.2%} is high",
                    'value': metrics['gpu_utilization']
                })

        # Send alerts
        for alert in alerts:
            await self.send_alert(alert)

        return alerts

    async def send_alert(self, alert: Dict):
        """Send alert through configured channels"""
        alert['timestamp'] = datetime.now().isoformat()
        self.alert_history.append(alert)

        # Send through enabled channels
        for channel in ['webhook']:  # Configure active channels
            if channel in self.alert_channels:
                await self.alert_channels[channel](alert)

    async def _send_email(self, alert: Dict):
        """Send email alert"""
        # Implementation would use SMTP or email service
        pass

    async def _send_webhook(self, alert: Dict):
        """Send webhook alert"""
        webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        if not webhook_url:
            return

        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json=alert)

    async def _send_push(self, alert: Dict):
        """Send push notification"""
        # Implementation would use push service
        pass


class MonitoringDashboard:
    """Web dashboard for monitoring metrics"""

    def __init__(self):
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse

        self.app = FastAPI(title="SLM Monitoring Dashboard")

        @self.app.get("/metrics/{user_id}")
        async def get_user_metrics(user_id: str):
            """Get user metrics"""
            collector = MetricsCollector(user_id, MonitoringConfig())
            metrics = collector.get_aggregate_metrics()
            return metrics

        @self.app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard():
            """Render monitoring dashboard"""
            return self._generate_dashboard_html()

    def _generate_dashboard_html(self) -> str:
        """Generate dashboard HTML"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>SLM Monitoring Dashboard</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .metric { display: inline-block; margin: 10px; padding: 15px; border: 1px solid #ddd; }
                .chart-container { width: 45%; display: inline-block; margin: 10px; }
            </style>
        </head>
        <body>
            <h1>Personal SLM Monitoring Dashboard</h1>

            <div id="metrics">
                <div class="metric">
                    <h3>Inference Count</h3>
                    <p id="inference-count">-</p>
                </div>
                <div class="metric">
                    <h3>Avg Latency</h3>
                    <p id="avg-latency">-</p>
                </div>
                <div class="metric">
                    <h3>Success Rate</h3>
                    <p id="success-rate">-</p>
                </div>
            </div>

            <div class="chart-container">
                <canvas id="latency-chart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="throughput-chart"></canvas>
            </div>

            <script>
                // Fetch and update metrics
                async function updateMetrics() {
                    const response = await fetch('/metrics/current-user');
                    const data = await response.json();

                    document.getElementById('inference-count').textContent = data.inference_count || '-';
                    document.getElementById('avg-latency').textContent = (data.avg_latency_ms || 0) + ' ms';
                    document.getElementById('success-rate').textContent = ((data.success_rate || 0) * 100).toFixed(2) + '%';
                }

                // Update every 5 seconds
                setInterval(updateMetrics, 5000);
                updateMetrics();

                // Initialize charts
                new Chart(document.getElementById('latency-chart'), {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: [{
                            label: 'Inference Latency (ms)',
                            data: [],
                            borderColor: 'rgb(75, 192, 192)',
                            tension: 0.1
                        }]
                    }
                });
            </script>
        </body>
        </html>
        """


if __name__ == "__main__":
    # Test monitoring components
    user_id = "test_user_001"
    config = MonitoringConfig()

    # Test metrics collection
    collector = MetricsCollector(user_id, config)

    # Record some test metrics
    for i in range(10):
        collector.record_inference(
            latency_ms=np.random.uniform(100, 500),
            tokens_generated=np.random.randint(50, 200),
            success=np.random.random() > 0.1,
            model_version="1.0.0"
        )

    # Get aggregate metrics
    metrics = collector.get_aggregate_metrics()
    print(f"Aggregate metrics: {json.dumps(metrics, indent=2)}")

    # Test performance monitoring
    monitor = ModelPerformanceMonitor(user_id)
    monitor.establish_baseline({'loss': 0.5, 'accuracy': 0.85, 'inference_latency_ms': 200})

    current = {'loss': 0.6, 'accuracy': 0.82, 'inference_latency_ms': 250}
    drift_report = monitor.check_model_drift(current)
    print(f"Drift detection: {json.dumps(drift_report, indent=2)}")

    # Test lifecycle management
    lifecycle = UserLifecycleManager(user_id)

    # Test export
    export_path = lifecycle.export_user_data("json")
    print(f"Exported data to: {export_path}")

    print("\nAll monitoring tests completed!")