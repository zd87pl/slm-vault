#!/usr/bin/env python3
"""
Check status of RunPod Axolotl training job
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.runpod_axolotl_v12 import RunPodAxolotlClient


def format_time(timestamp: str) -> str:
    """Format timestamp for display"""
    if not timestamp:
        return "N/A"

    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def calculate_duration(start: str, end: str) -> str:
    """Calculate duration between timestamps"""
    if not start or not end:
        return "N/A"

    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
    duration = end_dt - start_dt

    hours = duration.seconds // 3600
    minutes = (duration.seconds % 3600) // 60

    return f"{hours}h {minutes}m"


def main():
    parser = argparse.ArgumentParser(description="Check RunPod training status")
    parser.add_argument("--job-id", required=True, help="Job ID to check")
    parser.add_argument("--watch", action="store_true", help="Watch status continuously")
    parser.add_argument("--interval", type=int, default=30, help="Watch interval in seconds")

    args = parser.parse_args()

    # Initialize client
    api_key = os.getenv("RUNPOD_API_KEY")
    if not api_key:
        print("Error: RUNPOD_API_KEY environment variable not set")
        sys.exit(1)

    client = RunPodAxolotlClient(api_key)

    # Check status
    try:
        if args.watch:
            import time
            print(f"Watching job {args.job_id} (updating every {args.interval}s, Ctrl+C to stop)...\n")

            while True:
                status = client.get_job_status(args.job_id)

                # Clear screen (works on Unix-like systems)
                os.system('clear' if os.name == 'posix' else 'cls')

                print(f"Job Status Monitor - {datetime.now().strftime('%H:%M:%S')}")
                print("=" * 60)
                display_status(status)

                if status["status"] in ["COMPLETED", "FAILED"]:
                    print("\n✓ Job has finished!")
                    break

                time.sleep(args.interval)
        else:
            status = client.get_job_status(args.job_id)
            display_status(status)

    except KeyboardInterrupt:
        print("\nStopped watching.")
    except Exception as e:
        print(f"Error checking status: {e}")
        sys.exit(1)


def display_status(status: Dict):
    """Display formatted status information"""

    # Status indicator
    status_emoji = {
        "PENDING": "⏳",
        "RUNNING": "🔄",
        "COMPLETED": "✅",
        "FAILED": "❌"
    }.get(status["status"], "❓")

    print(f"{status_emoji} Status: {status['status']}")
    print(f"Job ID: {status['job_id']}")
    print()

    # Timing information
    print("Timeline:")
    print(f"  Created: {format_time(status.get('created_at'))}")
    print(f"  Started: {format_time(status.get('started_at'))}")

    if status.get('completed_at'):
        print(f"  Completed: {format_time(status.get('completed_at'))}")
        duration = calculate_duration(
            status.get('started_at'),
            status.get('completed_at')
        )
        print(f"  Duration: {duration}")

    # Output or error
    if status.get('output'):
        print("\nOutput:")
        output = status['output']
        if isinstance(output, dict):
            for key, value in output.items():
                print(f"  {key}: {value}")
        else:
            print(f"  {output}")

    if status.get('error'):
        print("\n❌ Error:")
        print(f"  {status['error']}")

    # Training metrics if available
    if status.get('output') and isinstance(status['output'], dict):
        metrics = status['output'].get('metrics', {})
        if metrics:
            print("\nTraining Metrics:")
            print(f"  Final Loss: {metrics.get('final_loss', 'N/A')}")
            print(f"  Eval Loss: {metrics.get('eval_loss', 'N/A')}")
            print(f"  Total Steps: {metrics.get('total_steps', 'N/A')}")

            # Model location
            if status['output'].get('model_url'):
                print(f"\nModel URL: {status['output']['model_url']}")
            if status['output'].get('hub_model_id'):
                print(f"HuggingFace Hub: https://huggingface.co/{status['output']['hub_model_id']}")


if __name__ == "__main__":
    main()