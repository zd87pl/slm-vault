"""
Progressive Onboarding System - Zero to DNA
Start with questionnaires, gradually add genetic data
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from scipy import stats
import hashlib


class DataConfidenceLevel(Enum):
    """Confidence levels for different data sources"""
    BEHAVIORAL = 0.4
    QUESTIONNAIRE = 0.5
    FAMILY_HISTORY = 0.6
    PHYSICAL_TRAITS = 0.7
    INFERRED_GENETICS = 0.75
    IMPORTED_GENETICS = 0.9
    CLINICAL_GENETICS = 0.95


class OnboardingStage(Enum):
    """User's current onboarding stage"""
    CONNECTED_WEARABLE = "connected_wearable"
    COMPLETED_BASIC_QUESTIONNAIRE = "completed_basic"
    COMPLETED_FAMILY_HISTORY = "completed_family"
    ADDED_BEHAVIORAL_DATA = "added_behavioral"
    ANALYZED_PHYSICAL_TRAITS = "analyzed_physical"
    IMPORTED_CONSUMER_GENETICS = "imported_consumer"
    COMPLETED_CLINICAL_GENETICS = "clinical_genetics"


@dataclass
class GeneticPrediction:
    """Predicted genetic trait with confidence"""
    trait: str
    value: Any
    confidence: float
    source: str
    evidence: List[str] = field(default_factory=list)


class FamilyHistoryQuestionnaire:
    """Convert family history into genetic predictions"""

    def __init__(self):
        self.questions = self._load_question_bank()
        self.population_frequencies = self._load_population_data()

    def _load_question_bank(self) -> List[Dict]:
        """Load progressive questionnaire bank"""
        return [
            # Athletic Performance
            {
                "id": "athletic_family",
                "category": "fitness",
                "question": "Do you have family members who are naturally athletic?",
                "options": [
                    {"text": "Yes, professional or college athletes", "score": 0.9},
                    {"text": "Yes, very active and fit", "score": 0.7},
                    {"text": "Some are athletic", "score": 0.5},
                    {"text": "Not particularly athletic", "score": 0.3}
                ],
                "genetic_inference": {
                    "ACTN3": {"RR": 0.7, "RX": 0.2, "XX": 0.1},  # Power gene
                    "ACE": {"II": 0.2, "ID": 0.3, "DD": 0.5}  # Endurance gene
                },
                "follow_up": "athletic_type"
            },
            {
                "id": "athletic_type",
                "category": "fitness",
                "condition": "athletic_family > 0.5",
                "question": "What type of sports do they excel at?",
                "options": [
                    {"text": "Sprinting, weightlifting (power)", "score": "power"},
                    {"text": "Marathon, cycling (endurance)", "score": "endurance"},
                    {"text": "Mixed sports", "score": "balanced"},
                    {"text": "Not sure", "score": "unknown"}
                ],
                "genetic_inference": {
                    "power": {"ACTN3_RR": 0.8, "fast_twitch": 0.7},
                    "endurance": {"ACE_II": 0.7, "slow_twitch": 0.8},
                    "balanced": {"mixed_fiber": 0.6}
                }
            },

            # Health Conditions
            {
                "id": "heart_disease",
                "category": "health",
                "question": "Has anyone in your immediate family had heart disease before age 60?",
                "options": [
                    {"text": "Multiple family members", "score": 0.9},
                    {"text": "One parent", "score": 0.7},
                    {"text": "One grandparent", "score": 0.5},
                    {"text": "No or after 60", "score": 0.2}
                ],
                "genetic_inference": {
                    "APOE": {"e4e4": 0.3, "e3e4": 0.5, "e3e3": 0.2},
                    "cardiovascular_risk": {"high": 0.7, "moderate": 0.2, "low": 0.1}
                }
            },
            {
                "id": "diabetes_family",
                "category": "health",
                "question": "Does Type 2 diabetes run in your family?",
                "options": [
                    {"text": "Both parents", "score": 0.9},
                    {"text": "One parent", "score": 0.6},
                    {"text": "Grandparents only", "score": 0.4},
                    {"text": "No", "score": 0.1}
                ],
                "genetic_inference": {
                    "TCF7L2": {"risk_allele": 0.7},
                    "metabolic_efficiency": {"low": 0.6, "moderate": 0.3, "high": 0.1}
                }
            },

            # Metabolism & Response
            {
                "id": "caffeine_response",
                "category": "metabolism",
                "question": "How does coffee affect you?",
                "options": [
                    {"text": "Can drink anytime, even before bed", "score": "fast"},
                    {"text": "Need to stop by afternoon", "score": "normal"},
                    {"text": "Very sensitive, only morning", "score": "slow"},
                    {"text": "Can't tolerate coffee", "score": "very_slow"}
                ],
                "genetic_inference": {
                    "CYP1A2": {
                        "fast": {"AA": 0.8, "AC": 0.2},
                        "slow": {"CC": 0.7, "AC": 0.3}
                    }
                }
            },
            {
                "id": "alcohol_flush",
                "category": "metabolism",
                "question": "Do you or family members get red/flushed from alcohol?",
                "options": [
                    {"text": "Yes, very quickly", "score": 0.9},
                    {"text": "Sometimes", "score": 0.5},
                    {"text": "Never", "score": 0.1}
                ],
                "genetic_inference": {
                    "ALDH2": {"deficient": 0.8, "normal": 0.2}
                }
            },

            # Recovery & Adaptation
            {
                "id": "recovery_speed",
                "category": "recovery",
                "question": "How quickly do you recover from hard workouts?",
                "options": [
                    {"text": "Very fast (next day)", "score": 0.9},
                    {"text": "Normal (2-3 days)", "score": 0.5},
                    {"text": "Slow (4+ days)", "score": 0.2},
                    {"text": "Very slow, injury prone", "score": 0.1}
                ],
                "genetic_inference": {
                    "IL6": {"GG": 0.3, "CG": 0.5, "CC": 0.2},  # Inflammation
                    "MCT1": {"AA": 0.7, "AT": 0.2, "TT": 0.1}  # Lactate clearance
                }
            },

            # Ancestry & Population
            {
                "id": "ancestry",
                "category": "demographic",
                "question": "What is your primary ethnic background?",
                "options": [
                    {"text": "European", "score": "european"},
                    {"text": "African", "score": "african"},
                    {"text": "East Asian", "score": "east_asian"},
                    {"text": "South Asian", "score": "south_asian"},
                    {"text": "Middle Eastern", "score": "middle_eastern"},
                    {"text": "Latin American", "score": "latin_american"},
                    {"text": "Mixed/Other", "score": "mixed"}
                ],
                "population_genetics": True
            }
        ]

    def _load_population_data(self) -> Dict:
        """Load population-specific allele frequencies"""
        return {
            "european": {
                "ACTN3_RR": 0.30,
                "ACE_II": 0.25,
                "ALDH2_deficient": 0.01,
                "lactose_tolerant": 0.90
            },
            "african": {
                "ACTN3_RR": 0.45,
                "ACE_II": 0.15,
                "ALDH2_deficient": 0.01,
                "lactose_tolerant": 0.20
            },
            "east_asian": {
                "ACTN3_RR": 0.25,
                "ACE_II": 0.35,
                "ALDH2_deficient": 0.35,
                "lactose_tolerant": 0.10
            }
        }

    def calculate_genetic_probability(
        self,
        answers: Dict[str, Any],
        user_ancestry: str = "mixed"
    ) -> List[GeneticPrediction]:
        """Calculate genetic probabilities from questionnaire"""
        predictions = []

        # Start with population baseline
        if user_ancestry in self.population_frequencies:
            baseline = self.population_frequencies[user_ancestry]
        else:
            baseline = self._get_global_averages()

        # Adjust based on family history
        for question_id, answer in answers.items():
            question = self._get_question(question_id)
            if not question:
                continue

            if "genetic_inference" in question:
                inference = question["genetic_inference"]

                # Calculate updated probability
                if isinstance(answer, dict) and "score" in answer:
                    score = answer["score"]

                    # Bayesian update
                    for gene, alleles in inference.items():
                        if isinstance(alleles, dict):
                            for allele, prob in alleles.items():
                                prior = baseline.get(f"{gene}_{allele}", 0.5)
                                posterior = self._bayesian_update(prior, prob, score)

                                predictions.append(GeneticPrediction(
                                    trait=f"{gene}_{allele}",
                                    value=posterior,
                                    confidence=DataConfidenceLevel.FAMILY_HISTORY.value,
                                    source="family_history",
                                    evidence=[question_id]
                                ))

        return predictions

    def _bayesian_update(self, prior: float, likelihood: float, evidence: float) -> float:
        """Bayesian probability update"""
        # P(A|B) = P(B|A) * P(A) / P(B)
        posterior = (likelihood * evidence * prior) / (
            (likelihood * evidence * prior) + ((1 - likelihood) * (1 - evidence) * (1 - prior))
        )
        return min(max(posterior, 0.01), 0.99)  # Bound between 0.01 and 0.99

    def _get_question(self, question_id: str) -> Optional[Dict]:
        """Get question by ID"""
        for q in self.questions:
            if q["id"] == question_id:
                return q
        return None

    def _get_global_averages(self) -> Dict:
        """Get global average frequencies"""
        return {
            "ACTN3_RR": 0.30,
            "ACE_II": 0.25,
            "ALDH2_deficient": 0.10,
            "lactose_tolerant": 0.35
        }


class BehavioralGeneticsInference:
    """Infer genetic traits from observable behaviors"""

    def __init__(self):
        self.behavioral_markers = {
            "caffeine_metabolism": {
                "indicators": [
                    "coffee_after_3pm",
                    "sleep_quality_post_caffeine",
                    "caffeine_daily_intake"
                ],
                "inference_rules": self._infer_caffeine_metabolism
            },
            "lactose_tolerance": {
                "indicators": [
                    "dairy_consumption",
                    "digestive_comfort",
                    "dairy_avoidance"
                ],
                "inference_rules": self._infer_lactose_tolerance
            },
            "muscle_fiber_type": {
                "indicators": [
                    "preferred_exercise_type",
                    "muscle_growth_rate",
                    "fatigue_pattern"
                ],
                "inference_rules": self._infer_muscle_fiber_type
            },
            "recovery_rate": {
                "indicators": [
                    "hrv_recovery_slope",
                    "soreness_duration",
                    "performance_bounce_back"
                ],
                "inference_rules": self._infer_recovery_genetics
            }
        }

    def analyze_behavior_patterns(self, user_data: Dict) -> List[GeneticPrediction]:
        """Analyze behavior patterns to infer genetics"""
        predictions = []

        for trait, config in self.behavioral_markers.items():
            # Check if we have sufficient data
            if self._has_sufficient_data(user_data, config["indicators"]):
                inference = config["inference_rules"](user_data)
                if inference:
                    predictions.append(inference)

        return predictions

    def _has_sufficient_data(self, user_data: Dict, required_indicators: List[str]) -> bool:
        """Check if user has enough behavioral data"""
        available = sum(1 for ind in required_indicators if ind in user_data and user_data[ind] is not None)
        return available >= len(required_indicators) * 0.7  # Need 70% of indicators

    def _infer_caffeine_metabolism(self, user_data: Dict) -> GeneticPrediction:
        """Infer CYP1A2 gene variant from caffeine response"""
        score = 0.5  # Start neutral

        # Late coffee consumption without sleep issues = fast metabolizer
        if user_data.get("coffee_after_3pm", False):
            if user_data.get("sleep_quality_post_caffeine", 0) > 0.7:
                score += 0.3
            else:
                score -= 0.3

        # High daily intake tolerance = fast metabolizer
        daily_cups = user_data.get("caffeine_daily_intake", 0) / 100  # mg to cups
        if daily_cups > 4:
            score += 0.2
        elif daily_cups < 1:
            score -= 0.2

        metabolism_type = "fast" if score > 0.6 else "slow" if score < 0.4 else "normal"

        return GeneticPrediction(
            trait="CYP1A2_metabolism",
            value=metabolism_type,
            confidence=DataConfidenceLevel.BEHAVIORAL.value,
            source="behavioral_analysis",
            evidence=["coffee_consumption_pattern", "sleep_analysis"]
        )

    def _infer_lactose_tolerance(self, user_data: Dict) -> GeneticPrediction:
        """Infer lactose tolerance from dairy consumption patterns"""
        dairy_freq = user_data.get("dairy_consumption", 0)
        comfort = user_data.get("digestive_comfort", 1.0)
        avoidance = user_data.get("dairy_avoidance", False)

        if avoidance or (dairy_freq < 2 and comfort < 0.5):
            tolerance = "intolerant"
            confidence = 0.7
        elif dairy_freq > 5 and comfort > 0.8:
            tolerance = "tolerant"
            confidence = 0.8
        else:
            tolerance = "partial"
            confidence = 0.5

        return GeneticPrediction(
            trait="lactose_tolerance",
            value=tolerance,
            confidence=confidence * DataConfidenceLevel.BEHAVIORAL.value,
            source="dietary_behavior",
            evidence=["dairy_consumption", "digestive_tracking"]
        )

    def _infer_muscle_fiber_type(self, user_data: Dict) -> GeneticPrediction:
        """Infer ACTN3 variant from exercise preferences and response"""
        pref = user_data.get("preferred_exercise_type", "mixed")
        growth = user_data.get("muscle_growth_rate", "normal")
        fatigue = user_data.get("fatigue_pattern", "normal")

        score = 0.5

        # Exercise preference
        if pref == "sprints" or pref == "weights":
            score += 0.2
        elif pref == "endurance":
            score -= 0.2

        # Muscle growth response
        if growth == "fast":
            score += 0.15
        elif growth == "slow":
            score -= 0.15

        # Fatigue pattern
        if fatigue == "quick_power_loss":
            score += 0.1  # Fast twitch fatigues quickly
        elif fatigue == "slow_steady":
            score -= 0.1  # Slow twitch

        fiber_type = "fast_twitch" if score > 0.6 else "slow_twitch" if score < 0.4 else "mixed"

        return GeneticPrediction(
            trait="ACTN3_fiber_type",
            value=fiber_type,
            confidence=DataConfidenceLevel.BEHAVIORAL.value,
            source="exercise_response",
            evidence=["workout_preferences", "adaptation_pattern"]
        )

    def _infer_recovery_genetics(self, user_data: Dict) -> GeneticPrediction:
        """Infer recovery-related genetics from HRV and soreness patterns"""
        hrv_slope = user_data.get("hrv_recovery_slope", 0)
        soreness = user_data.get("soreness_duration", 3)
        bounce = user_data.get("performance_bounce_back", 3)

        # Calculate recovery score
        recovery_score = (
            (hrv_slope * 0.4) +
            ((5 - soreness) / 5 * 0.3) +
            ((5 - bounce) / 5 * 0.3)
        )

        if recovery_score > 0.7:
            recovery = "fast"
        elif recovery_score < 0.3:
            recovery = "slow"
        else:
            recovery = "normal"

        return GeneticPrediction(
            trait="recovery_genetics",
            value=recovery,
            confidence=DataConfidenceLevel.BEHAVIORAL.value,
            source="recovery_patterns",
            evidence=["hrv_analysis", "soreness_tracking", "performance_data"]
        )


class ProgressiveProfileBuilder:
    """Build user's health profile progressively"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.profile = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "stage": OnboardingStage.CONNECTED_WEARABLE.value,
            "predictions": [],
            "confidence_score": 0.0,
            "data_sources": []
        }
        self.questionnaire = FamilyHistoryQuestionnaire()
        self.behavior_analyzer = BehavioralGeneticsInference()

    def add_wearable_data(self, wearable_data: Dict) -> Dict:
        """Process initial wearable data"""
        self.profile["data_sources"].append("wearable")

        # Extract behavioral patterns
        behavioral_predictions = self.behavior_analyzer.analyze_behavior_patterns(wearable_data)
        self.profile["predictions"].extend([p.__dict__ for p in behavioral_predictions])

        self._update_confidence()
        return self._generate_insights()

    def add_questionnaire_answers(self, answers: Dict, ancestry: str = "mixed") -> Dict:
        """Process questionnaire responses"""
        self.profile["data_sources"].append("questionnaire")
        self.profile["stage"] = OnboardingStage.COMPLETED_FAMILY_HISTORY.value

        # Generate predictions
        family_predictions = self.questionnaire.calculate_genetic_probability(answers, ancestry)
        self.profile["predictions"].extend([p.__dict__ for p in family_predictions])

        self._update_confidence()
        return self._generate_insights()

    def import_genetic_data(self, genetic_file: str, source: str = "23andme") -> Dict:
        """Import existing genetic data"""
        self.profile["data_sources"].append(f"genetics_{source}")
        self.profile["stage"] = OnboardingStage.IMPORTED_CONSUMER_GENETICS.value

        # Parse genetic data
        genetic_markers = self._parse_genetic_file(genetic_file, source)

        # Replace predictions with actual data
        self._update_predictions_with_genetics(genetic_markers)

        self._update_confidence()
        return self._generate_insights()

    def _parse_genetic_file(self, file_content: str, source: str) -> Dict:
        """Parse genetic data file"""
        markers = {}

        if source == "23andme":
            # Parse 23andMe format
            for line in file_content.split('\n'):
                if line.startswith('#') or not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 4:
                    rsid = parts[0]
                    genotype = parts[3]
                    markers[rsid] = genotype

        elif source == "ancestry":
            # Parse AncestryDNA format
            pass  # Implementation for each format

        return markers

    def _update_predictions_with_genetics(self, genetic_markers: Dict):
        """Update predictions with real genetic data"""
        # Map known SNPs to traits
        snp_to_trait = {
            "rs1815739": "ACTN3",  # Sprinter gene
            "rs1049434": "MCT1",   # Lactate clearance
            "rs1799752": "ACE",    # Endurance
            "rs1800795": "IL6",    # Recovery/inflammation
        }

        for rsid, genotype in genetic_markers.items():
            if rsid in snp_to_trait:
                # Replace prediction with actual
                trait = snp_to_trait[rsid]
                self.profile["predictions"] = [
                    p for p in self.profile["predictions"]
                    if not p.get("trait", "").startswith(trait)
                ]

                # Add actual genetic data
                self.profile["predictions"].append({
                    "trait": f"{trait}_{rsid}",
                    "value": genotype,
                    "confidence": DataConfidenceLevel.IMPORTED_GENETICS.value,
                    "source": "genetic_data",
                    "evidence": [rsid]
                })

    def _update_confidence(self):
        """Update overall profile confidence"""
        if not self.profile["predictions"]:
            self.profile["confidence_score"] = 0.0
            return

        # Weighted average of prediction confidences
        total_confidence = sum(p.get("confidence", 0) for p in self.profile["predictions"])
        self.profile["confidence_score"] = total_confidence / len(self.profile["predictions"])

    def _generate_insights(self) -> Dict:
        """Generate personalized insights based on current profile"""
        insights = {
            "user_id": self.user_id,
            "confidence": self.profile["confidence_score"],
            "stage": self.profile["stage"],
            "recommendations": []
        }

        # Generate insights based on available predictions
        for prediction in self.profile["predictions"]:
            insight = self._prediction_to_insight(prediction)
            if insight:
                insights["recommendations"].append(insight)

        # Add upgrade prompts based on stage
        if self.profile["stage"] == OnboardingStage.CONNECTED_WEARABLE.value:
            insights["upgrade_prompt"] = "Complete our health questionnaire to unlock genetic insights"
        elif self.profile["stage"] == OnboardingStage.COMPLETED_FAMILY_HISTORY.value:
            insights["upgrade_prompt"] = "Import your DNA results for precision recommendations"

        return insights

    def _prediction_to_insight(self, prediction: Dict) -> Optional[str]:
        """Convert prediction to actionable insight"""
        trait = prediction.get("trait", "")
        value = prediction.get("value", "")
        confidence = prediction.get("confidence", 0)

        if confidence < 0.3:
            return None  # Too uncertain

        insights_map = {
            "CYP1A2_metabolism": {
                "fast": "You can enjoy caffeine throughout the day without affecting sleep",
                "slow": "Limit caffeine to mornings for better sleep quality"
            },
            "ACTN3_fiber_type": {
                "fast_twitch": "Your genetics favor power and sprint training",
                "slow_twitch": "You're built for endurance - embrace longer workouts",
                "mixed": "You can excel at both power and endurance training"
            },
            "recovery_genetics": {
                "fast": "Your quick recovery allows more frequent intense training",
                "slow": "Prioritize recovery days and active rest for optimal gains"
            },
            "lactose_tolerance": {
                "intolerant": "Consider dairy alternatives for better digestion",
                "tolerant": "Dairy products are a good protein source for you"
            }
        }

        if trait in insights_map and value in insights_map[trait]:
            base_insight = insights_map[trait][value]

            # Add confidence qualifier
            if confidence < 0.6:
                return f"Likely: {base_insight}"
            elif confidence < 0.9:
                return f"Probable: {base_insight}"
            else:
                return base_insight

        return None


# Example Usage
if __name__ == "__main__":
    # New user signs up
    user = ProgressiveProfileBuilder(user_id="user_123")

    # Day 1: Connect wearable
    wearable_data = {
        "coffee_after_3pm": True,
        "sleep_quality_post_caffeine": 0.8,
        "caffeine_daily_intake": 400,
        "preferred_exercise_type": "weights",
        "muscle_growth_rate": "fast",
        "hrv_recovery_slope": 0.7
    }
    insights = user.add_wearable_data(wearable_data)
    print(f"Day 1 Insights: {json.dumps(insights, indent=2)}")

    # Day 3: Complete questionnaire
    questionnaire_answers = {
        "athletic_family": {"score": 0.7},
        "heart_disease": {"score": 0.2},
        "caffeine_response": {"score": "fast"},
        "recovery_speed": {"score": 0.9}
    }
    insights = user.add_questionnaire_answers(questionnaire_answers, ancestry="european")
    print(f"Day 3 Insights: {json.dumps(insights, indent=2)}")

    # Month 2: Import 23andMe
    genetic_data = """# rsid  chromosome  position  genotype
rs1815739   11  66328095    CC
rs1049434   1   165774431   AA"""

    insights = user.import_genetic_data(genetic_data, source="23andme")
    print(f"Month 2 Insights: {json.dumps(insights, indent=2)}")

    print(f"\nFinal Profile Confidence: {user.profile['confidence_score']:.2%}")