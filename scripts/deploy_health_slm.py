#!/usr/bin/env python3
"""
Deploy Personal Health SLM using RunPod Axolotl v0.12.2
Complete end-to-end deployment script
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.runpod_axolotl_v12 import (
    PersonalSLMOrchestrator,
    PersonalHealthDataFormatter,
    RunPodAxolotlClient
)
from src.data_pipeline import DataPipelineManager
from src.security import SecureStorage, DataEncryption


def load_user_data(user_id: str) -> Tuple[Dict, List[Dict], Dict]:
    """Load and decrypt user's health data"""

    # Initialize secure storage
    storage = SecureStorage(user_id)

    # Load genetic data
    genetic_data = json.loads(
        storage.retrieve_data("genetic_profile.json").decode()
    )

    # Load fitness history (last 90 days)
    fitness_history = json.loads(
        storage.retrieve_data("fitness_history.json").decode()
    )

    # Load user context
    user_context = json.loads(
        storage.retrieve_data("user_profile.json").decode()
    )

    return genetic_data, fitness_history, user_context


def generate_mock_data(user_id: str) -> Tuple[Dict, List[Dict], Dict]:
    """Generate mock data for testing"""

    genetic_data = {
        "polygenic_scores": {
            "endurance": 0.72,
            "strength": 0.65,
            "recovery": 0.70,
            "vo2max": 0.68,
            "muscle_composition": 0.55,
            "metabolic_efficiency": 0.62
        },
        "actionable_variants": [
            {
                "rsid": "rs1815739",
                "gene": "ACTN3",
                "genotype": "CT",
                "impact": "mixed_muscle_composition",
                "recommendation": "Balanced power and endurance training"
            },
            {
                "rsid": "rs1049434",
                "gene": "MCT1",
                "genotype": "AA",
                "impact": "enhanced_lactate_clearance",
                "recommendation": "Can handle higher intensity intervals"
            },
            {
                "rsid": "rs1799752",
                "gene": "ACE",
                "genotype": "ID",
                "impact": "balanced_endurance",
                "recommendation": "Moderate endurance capacity"
            },
            {
                "rsid": "rs1800795",
                "gene": "IL6",
                "genotype": "GG",
                "impact": "normal_inflammation_response",
                "recommendation": "Standard recovery protocols"
            }
        ],
        "health_risks": {
            "cardiovascular": 0.15,
            "diabetes": 0.08,
            "injury_prone": 0.12
        },
        "nutrient_metabolism": {
            "caffeine": "fast",
            "lactose": "tolerant",
            "gluten": "sensitive",
            "omega3_needs": "elevated"
        }
    }

    # Generate 30 days of fitness data
    fitness_history = []
    base_date = datetime.now() - timedelta(days=30)

    for i in range(30):
        date = base_date + timedelta(days=i)

        # Simulate realistic variations
        import random

        fitness_history.append({
            "date": date.strftime("%Y-%m-%d"),
            "sleep_hours": 6.5 + random.random() * 2.5,
            "sleep_quality": 0.6 + random.random() * 0.35,
            "deep_sleep_pct": 0.15 + random.random() * 0.1,
            "rem_sleep_pct": 0.20 + random.random() * 0.1,

            "hrv": 35 + random.random() * 30,
            "resting_hr": 55 + random.random() * 15,
            "hrv_trend": random.choice(["improving", "stable", "declining"]),

            "steps": random.randint(4000, 15000),
            "active_calories": random.randint(200, 800),
            "total_calories": random.randint(1800, 3000),

            "workout_type": random.choice(["rest", "easy", "moderate", "hard", "intervals"]),
            "workout_duration_min": random.randint(0, 90),
            "avg_heart_rate": random.randint(110, 160) if random.random() > 0.3 else 0,
            "max_heart_rate": random.randint(140, 185) if random.random() > 0.3 else 0,

            "training_load": random.random() * 10,
            "recovery_score": 0.3 + random.random() * 0.6,
            "stress_level": random.randint(1, 10),
            "energy_level": random.randint(3, 10),
            "soreness_level": random.randint(0, 7),

            "hydration_oz": random.randint(40, 100),
            "protein_g": random.randint(60, 150),
            "carbs_g": random.randint(150, 350),
            "fat_g": random.randint(40, 100)
        })

    user_context = {
        "user_id": user_id,
        "age": 35,
        "sex": "male",
        "height_cm": 180,
        "weight_kg": 75,
        "bmi": 23.1,
        "body_fat_pct": 15,

        "fitness_level": "intermediate",
        "years_training": 5,
        "primary_sport": "running",

        "goals": {
            "primary": "improve marathon time",
            "secondary": ["increase VO2max", "reduce injury risk"],
            "target_race": "2024-10-15",
            "target_time": "3:30:00"
        },

        "preferences": {
            "training_days_per_week": 5,
            "preferred_workout_time": "morning",
            "diet_type": "mediterranean",
            "supplements": ["vitamin_d", "omega3", "magnesium"]
        },

        "medical_history": {
            "injuries": ["mild_it_band_2023"],
            "conditions": [],
            "medications": [],
            "allergies": ["peanuts"]
        },

        "location": {
            "timezone": "America/New_York",
            "climate": "temperate",
            "altitude_m": 200
        }
    }

    return genetic_data, fitness_history, user_context


def main():
    parser = argparse.ArgumentParser(description="Deploy Personal Health SLM")
    parser.add_argument("--user-id", required=True, help="User ID")
    parser.add_argument("--use-mock-data", action="store_true", help="Use mock data for testing")
    parser.add_argument("--base-model", default="NousResearch/Llama-3.2-1B", help="Base model to fine-tune")
    parser.add_argument("--wait", action="store_true", help="Wait for training to complete")
    parser.add_argument("--deploy", action="store_true", help="Deploy model after training")

    args = parser.parse_args()

    # Check environment variables
    required_env = ["RUNPOD_API_KEY", "HF_TOKEN"]
    missing = [e for e in required_env if not os.getenv(e)]
    if missing:
        print(f"Error: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Load or generate data
    if args.use_mock_data:
        print(f"Generating mock data for user {args.user_id}...")
        genetic_data, fitness_history, user_context = generate_mock_data(args.user_id)
    else:
        print(f"Loading real data for user {args.user_id}...")
        try:
            genetic_data, fitness_history, user_context = load_user_data(args.user_id)
        except FileNotFoundError:
            print("No real data found, using mock data instead...")
            genetic_data, fitness_history, user_context = generate_mock_data(args.user_id)

    # Initialize orchestrator
    print("\nInitializing Personal SLM Orchestrator...")
    orchestrator = PersonalSLMOrchestrator(args.user_id)

    # Start training
    print(f"\nStarting training with base model: {args.base_model}")
    print(f"- Genetic variants: {len(genetic_data['actionable_variants'])}")
    print(f"- Fitness history: {len(fitness_history)} days")
    print(f"- Primary goal: {user_context['goals']['primary']}")

    result = orchestrator.train_personal_slm(
        genetic_data=genetic_data,
        fitness_history=fitness_history,
        user_context=user_context,
        base_model=args.base_model
    )

    print(f"\n✅ Training job submitted!")
    print(f"Job ID: {result['job_id']}")
    print(f"Model ID: {result['model_id']}")
    print(f"Dataset: {result['dataset_repo']}")

    # Save job info
    job_file = Path(f"jobs/{args.user_id}_{result['job_id']}.json")
    job_file.parent.mkdir(exist_ok=True)
    with open(job_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nJob info saved to: {job_file}")

    # Wait for completion if requested
    if args.wait:
        print("\n⏳ Waiting for training to complete...")
        print("This may take 30-60 minutes depending on dataset size...")

        try:
            final_status = orchestrator.client.wait_for_completion(
                result['job_id'],
                timeout=7200  # 2 hours
            )

            print(f"\n✅ Training completed!")
            print(f"Output: {json.dumps(final_status.get('output', {}), indent=2)}")

            # Deploy if requested
            if args.deploy:
                print("\n🚀 Deploying model for inference...")
                deployment = orchestrator.deploy_trained_model(result['job_id'])
                print(f"Deployment: {json.dumps(deployment, indent=2)}")

        except TimeoutError:
            print("\n⏱️ Training is taking longer than expected. Check status with:")
            print(f"python scripts/check_training_status.py --job-id {result['job_id']}")
        except Exception as e:
            print(f"\n❌ Training failed: {e}")
            sys.exit(1)
    else:
        print("\nTo check training status, run:")
        print(f"python scripts/check_training_status.py --job-id {result['job_id']}")

        print("\nTo deploy after training completes:")
        print(f"python scripts/deploy_trained_model.py --job-id {result['job_id']} --user-id {args.user_id}")


if __name__ == "__main__":
    main()