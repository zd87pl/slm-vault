"""
EVO2 (Evolutionary Optimization Version 2) Genetic Fitness Optimizer
Implements evolutionary algorithms for personalized fitness optimization
Copyright © 2025 Zygmunt Dyras. All rights reserved.
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import random
from enum import Enum


class FitnessGoal(Enum):
    """Training goals for optimization"""
    ENDURANCE = "endurance"
    STRENGTH = "strength"
    POWER = "power"
    HYPERTROPHY = "hypertrophy"
    WEIGHT_LOSS = "weight_loss"
    GENERAL_FITNESS = "general_fitness"
    RECOVERY = "recovery"


@dataclass
class TrainingIndividual:
    """Represents an individual training program in the population"""
    chromosome: List[float]  # Encoded training parameters
    fitness_score: float = 0.0
    genomic_compatibility: float = 0.0
    performance_metrics: Optional[Dict] = None


@dataclass
class TrainingProgram:
    """Optimized training program output"""
    weekly_volume: int  # Total weekly training volume in minutes
    intensity_distribution: Dict[str, float]  # Zone distribution
    exercise_selection: List[str]  # Recommended exercises
    recovery_days: int  # Rest days per week
    periodization: str  # Training periodization strategy
    nutrition_timing: Dict[str, str]  # Pre/post workout nutrition
    supplement_recommendations: List[str]  # Personalized supplements
    adaptation_timeline: int  # Expected weeks to adaptation


class EVO2GeneticOptimizer:
    """
    Evolutionary optimizer for genetic fitness programs
    Uses genomic profiles to evolve personalized training protocols
    """

    def __init__(self, population_size: int = 100, generations: int = 50,
                 mutation_rate: float = 0.1, crossover_rate: float = 0.8):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_size = max(2, population_size // 10)
        self.tournament_size = 5

    def optimize_fitness_program(self, genomic_profile: Dict,
                                fitness_metrics: Dict,
                                goal: FitnessGoal) -> TrainingProgram:
        """
        Evolve an optimal training program based on genetics and current fitness

        Args:
            genomic_profile: Processed genomic data from VCF processor
            fitness_metrics: Current fitness measurements
            goal: Training goal to optimize for

        Returns:
            Optimized personalized training program
        """
        # Initialize population
        population = self._initialize_population(genomic_profile, goal)

        # Evolution loop
        for generation in range(self.generations):
            # Evaluate fitness of each individual
            population = self._evaluate_population(
                population, genomic_profile, fitness_metrics, goal
            )

            # Selection
            parents = self._tournament_selection(population)

            # Crossover
            offspring = self._adaptive_crossover(parents, genomic_profile)

            # Mutation
            mutated_offspring = self._guided_mutation(
                offspring, genomic_profile, generation
            )

            # Create new population with elitism
            population = self._create_new_population(
                population, mutated_offspring
            )

            # Adaptive parameter adjustment
            self._adapt_parameters(generation, population)

        # Select best solution
        best_individual = max(population, key=lambda x: x.fitness_score)

        # Decode to training program
        return self._decode_to_program(best_individual, genomic_profile, goal)

    def _initialize_population(self, genomic_profile: Dict,
                              goal: FitnessGoal) -> List[TrainingIndividual]:
        """Initialize population with genomic-informed individuals"""
        population = []

        for _ in range(self.population_size):
            # Create chromosome with training parameters
            chromosome = self._create_chromosome(genomic_profile, goal)
            individual = TrainingIndividual(chromosome=chromosome)
            population.append(individual)

        return population

    def _create_chromosome(self, genomic_profile: Dict,
                          goal: FitnessGoal) -> List[float]:
        """Create chromosome encoding training parameters"""
        chromosome = []

        # Volume gene (150-600 minutes/week, adjusted by recovery genetics)
        base_volume = 300
        if genomic_profile.get("recovery_score", 0.5) > 0.7:
            base_volume = 400  # Can handle more volume
        chromosome.append(base_volume + random.gauss(0, 50))

        # Intensity distribution (5 zones)
        if goal == FitnessGoal.ENDURANCE:
            # More low-intensity work for endurance
            zones = [0.4, 0.3, 0.2, 0.08, 0.02]
        elif goal in [FitnessGoal.STRENGTH, FitnessGoal.POWER]:
            # More high-intensity work
            zones = [0.2, 0.2, 0.2, 0.25, 0.15]
        else:
            # Balanced distribution
            zones = [0.3, 0.25, 0.2, 0.15, 0.1]

        # Add genetic bias
        if genomic_profile.get("endurance_score", 0.5) > 0.7:
            zones[0] += 0.1  # More Zone 1
            zones[4] -= 0.1  # Less Zone 5
        elif genomic_profile.get("power_score", 0.5) > 0.7:
            zones[4] += 0.1  # More Zone 5
            zones[0] -= 0.1  # Less Zone 1

        chromosome.extend(zones)

        # Recovery days (1-4, adjusted by genetics)
        base_recovery = 2
        if genomic_profile.get("recovery_score", 0.5) < 0.4:
            base_recovery = 3  # Need more recovery
        chromosome.append(base_recovery + random.random())

        # Exercise type preferences (0-1 scale for different types)
        # [compound, isolation, cardio, plyometric, mobility]
        if goal == FitnessGoal.STRENGTH:
            exercise_prefs = [0.8, 0.2, 0.1, 0.1, 0.2]
        elif goal == FitnessGoal.ENDURANCE:
            exercise_prefs = [0.2, 0.1, 0.7, 0.1, 0.3]
        else:
            exercise_prefs = [0.5, 0.3, 0.4, 0.2, 0.3]

        chromosome.extend(exercise_prefs)

        # Periodization parameters
        # [block_length_weeks, intensity_progression, volume_progression]
        chromosome.extend([4 + random.gauss(0, 1),  # Block length
                         0.05 + random.random() * 0.1,  # Intensity progression
                         0.1 + random.random() * 0.15])  # Volume progression

        return chromosome

    def _evaluate_population(self, population: List[TrainingIndividual],
                           genomic_profile: Dict, fitness_metrics: Dict,
                           goal: FitnessGoal) -> List[TrainingIndividual]:
        """Evaluate fitness of each individual in population"""
        for individual in population:
            # Calculate genomic compatibility
            genomic_score = self._calculate_genomic_compatibility(
                individual.chromosome, genomic_profile
            )

            # Calculate performance potential
            performance_score = self._calculate_performance_potential(
                individual.chromosome, fitness_metrics, goal
            )

            # Calculate injury risk (negative factor)
            injury_risk = self._calculate_injury_risk(
                individual.chromosome, genomic_profile, fitness_metrics
            )

            # Calculate adherence probability
            adherence_score = self._calculate_adherence_score(
                individual.chromosome, fitness_metrics
            )

            # Combined fitness score
            individual.fitness_score = (
                0.3 * genomic_score +
                0.3 * performance_score +
                0.2 * adherence_score -
                0.2 * injury_risk
            )

            individual.genomic_compatibility = genomic_score

        return population

    def _calculate_genomic_compatibility(self, chromosome: List[float],
                                        genomic_profile: Dict) -> float:
        """Calculate how well program matches genetic profile"""
        score = 0.0

        # Volume compatibility
        volume = chromosome[0]
        recovery_score = genomic_profile.get("recovery_score", 0.5)

        if recovery_score > 0.7:
            # Good recovery genetics can handle more volume
            score += min(1.0, volume / 500)
        else:
            # Poor recovery needs moderate volume
            score += 1.0 - abs(volume - 300) / 300

        # Intensity distribution compatibility
        zones = chromosome[1:6]
        endurance_score = genomic_profile.get("endurance_score", 0.5)
        power_score = genomic_profile.get("power_score", 0.5)

        if endurance_score > 0.7:
            # Reward more low-intensity work
            score += zones[0] + zones[1] * 0.5
        if power_score > 0.7:
            # Reward more high-intensity work
            score += zones[3] * 0.5 + zones[4]

        # Recovery days compatibility
        recovery_days = chromosome[6]
        if recovery_score < 0.4:
            # Poor recovery needs more rest
            score += min(1.0, recovery_days / 3)
        else:
            # Good recovery can train more frequently
            score += max(0, 1.0 - recovery_days / 5)

        return min(1.0, score / 3)  # Normalize

    def _calculate_performance_potential(self, chromosome: List[float],
                                        fitness_metrics: Dict,
                                        goal: FitnessGoal) -> float:
        """Calculate expected performance improvement"""
        score = 0.0

        volume = chromosome[0]
        zones = chromosome[1:6]
        current_fitness = fitness_metrics.get("vo2_max", 40)

        if goal == FitnessGoal.ENDURANCE:
            # Endurance improvements from volume and low-intensity work
            score = (volume / 600) * 0.5 + (zones[0] + zones[1]) * 0.5

        elif goal == FitnessGoal.STRENGTH:
            # Strength improvements from high-intensity and compound exercises
            exercise_prefs = chromosome[7:12]
            score = zones[3] * 0.3 + zones[4] * 0.3 + exercise_prefs[0] * 0.4

        elif goal == FitnessGoal.WEIGHT_LOSS:
            # Weight loss from volume and metabolic work
            score = (volume / 500) * 0.6 + zones[2] * 0.4

        else:
            # General fitness from balanced approach
            score = 0.5 + 0.5 * (1 - np.std(zones))

        # Adjust for current fitness level
        if current_fitness < 35:
            score *= 1.2  # More room for improvement
        elif current_fitness > 50:
            score *= 0.8  # Harder to improve

        return min(1.0, score)

    def _calculate_injury_risk(self, chromosome: List[float],
                              genomic_profile: Dict,
                              fitness_metrics: Dict) -> float:
        """Calculate injury risk score (higher is worse)"""
        risk = 0.0

        volume = chromosome[0]
        zones = chromosome[1:6]
        recovery_days = chromosome[6]

        # Volume-based risk
        if volume > 500:
            risk += (volume - 500) / 200

        # Intensity-based risk
        high_intensity = zones[3] + zones[4]
        if high_intensity > 0.4:
            risk += (high_intensity - 0.4) * 2

        # Recovery-based risk
        recovery_score = genomic_profile.get("recovery_score", 0.5)
        if recovery_score < 0.4 and recovery_days < 2.5:
            risk += 0.3

        # Previous injury risk
        injury_history = fitness_metrics.get("injury_count", 0)
        risk += injury_history * 0.1

        # Age-based risk adjustment
        age = fitness_metrics.get("age", 30)
        if age > 40:
            risk *= 1.2
        elif age < 25:
            risk *= 0.8

        return min(1.0, risk)

    def _calculate_adherence_score(self, chromosome: List[float],
                                  fitness_metrics: Dict) -> float:
        """Calculate likelihood of program adherence"""
        score = 1.0

        volume = chromosome[0]
        recovery_days = chromosome[6]

        # Volume adherence (too much reduces adherence)
        current_volume = fitness_metrics.get("current_weekly_volume", 200)
        volume_increase = (volume - current_volume) / current_volume

        if volume_increase > 0.5:
            score -= 0.3  # Too big a jump
        elif volume_increase > 0.2:
            score -= 0.1  # Challenging but doable

        # Complexity penalty
        exercise_prefs = chromosome[7:12]
        complexity = np.sum(np.array(exercise_prefs) > 0.2)
        if complexity > 3:
            score -= 0.2  # Too many exercise types

        # Time availability
        available_time = fitness_metrics.get("available_hours_per_week", 5)
        if volume > available_time * 60:
            score -= 0.4  # Not enough time

        return max(0, score)

    def _tournament_selection(self, population: List[TrainingIndividual]) -> List[TrainingIndividual]:
        """Select parents using tournament selection"""
        parents = []

        while len(parents) < self.population_size:
            # Select random individuals for tournament
            tournament = random.sample(population, self.tournament_size)

            # Winner is individual with highest fitness
            winner = max(tournament, key=lambda x: x.fitness_score)
            parents.append(winner)

        return parents

    def _adaptive_crossover(self, parents: List[TrainingIndividual],
                          genomic_profile: Dict) -> List[TrainingIndividual]:
        """Perform adaptive crossover based on genomic profile"""
        offspring = []

        for i in range(0, len(parents) - 1, 2):
            if random.random() < self.crossover_rate:
                # Perform crossover
                parent1, parent2 = parents[i], parents[i + 1]

                # Choose crossover method based on genomic diversity
                if genomic_profile.get("genetic_diversity", 0.5) > 0.7:
                    # High diversity - use uniform crossover
                    child1_chr, child2_chr = self._uniform_crossover(
                        parent1.chromosome, parent2.chromosome
                    )
                else:
                    # Low diversity - use two-point crossover
                    child1_chr, child2_chr = self._two_point_crossover(
                        parent1.chromosome, parent2.chromosome
                    )

                offspring.append(TrainingIndividual(chromosome=child1_chr))
                offspring.append(TrainingIndividual(chromosome=child2_chr))
            else:
                # No crossover - copy parents
                offspring.append(parents[i])
                if i + 1 < len(parents):
                    offspring.append(parents[i + 1])

        return offspring

    def _uniform_crossover(self, parent1: List[float],
                          parent2: List[float]) -> Tuple[List[float], List[float]]:
        """Uniform crossover - each gene has 50% chance from each parent"""
        child1, child2 = [], []

        for gene1, gene2 in zip(parent1, parent2):
            if random.random() < 0.5:
                child1.append(gene1)
                child2.append(gene2)
            else:
                child1.append(gene2)
                child2.append(gene1)

        return child1, child2

    def _two_point_crossover(self, parent1: List[float],
                           parent2: List[float]) -> Tuple[List[float], List[float]]:
        """Two-point crossover"""
        size = len(parent1)
        point1 = random.randint(1, size - 2)
        point2 = random.randint(point1 + 1, size - 1)

        child1 = parent1[:point1] + parent2[point1:point2] + parent1[point2:]
        child2 = parent2[:point1] + parent1[point1:point2] + parent2[point2:]

        return child1, child2

    def _guided_mutation(self, offspring: List[TrainingIndividual],
                        genomic_profile: Dict, generation: int) -> List[TrainingIndividual]:
        """Apply guided mutation based on genomic insights"""
        for individual in offspring:
            if random.random() < self.mutation_rate:
                # Adaptive mutation rate (decreases over generations)
                adaptive_rate = self.mutation_rate * (1 - generation / self.generations)

                for i in range(len(individual.chromosome)):
                    if random.random() < adaptive_rate:
                        # Guided mutation based on gene type
                        if i == 0:  # Volume gene
                            # Mutate based on recovery genetics
                            if genomic_profile.get("recovery_score", 0.5) > 0.7:
                                individual.chromosome[i] += random.gauss(0, 30)
                            else:
                                individual.chromosome[i] += random.gauss(0, 15)
                        elif 1 <= i <= 5:  # Intensity zones
                            # Small mutations to maintain distribution
                            individual.chromosome[i] += random.gauss(0, 0.05)
                            individual.chromosome[i] = max(0, min(1, individual.chromosome[i]))
                        else:
                            # Standard mutation for other genes
                            individual.chromosome[i] += random.gauss(0, 0.1)

        return offspring

    def _create_new_population(self, old_population: List[TrainingIndividual],
                              offspring: List[TrainingIndividual]) -> List[TrainingIndividual]:
        """Create new population with elitism"""
        # Sort by fitness
        old_population.sort(key=lambda x: x.fitness_score, reverse=True)

        # Keep elite individuals
        new_population = old_population[:self.elite_size]

        # Fill rest with offspring
        offspring.sort(key=lambda x: x.fitness_score, reverse=True)
        new_population.extend(offspring[:self.population_size - self.elite_size])

        return new_population

    def _adapt_parameters(self, generation: int, population: List[TrainingIndividual]):
        """Adapt GA parameters based on population statistics"""
        # Calculate population diversity
        fitness_scores = [ind.fitness_score for ind in population]
        diversity = np.std(fitness_scores)

        # Adjust mutation rate based on diversity
        if diversity < 0.1:
            # Low diversity - increase mutation
            self.mutation_rate = min(0.3, self.mutation_rate * 1.1)
        elif diversity > 0.3:
            # High diversity - decrease mutation
            self.mutation_rate = max(0.05, self.mutation_rate * 0.95)

    def _decode_to_program(self, individual: TrainingIndividual,
                          genomic_profile: Dict, goal: FitnessGoal) -> TrainingProgram:
        """Decode chromosome to training program"""
        chromosome = individual.chromosome

        # Extract parameters
        weekly_volume = int(chromosome[0])
        zones = chromosome[1:6]
        recovery_days = int(chromosome[6])
        exercise_prefs = chromosome[7:12]
        block_length = int(chromosome[12])
        intensity_progression = chromosome[13]
        volume_progression = chromosome[14]

        # Calculate intensity distribution
        intensity_distribution = {
            "Zone 1 (Recovery)": f"{zones[0]*100:.1f}%",
            "Zone 2 (Aerobic)": f"{zones[1]*100:.1f}%",
            "Zone 3 (Threshold)": f"{zones[2]*100:.1f}%",
            "Zone 4 (VO2Max)": f"{zones[3]*100:.1f}%",
            "Zone 5 (Neuromuscular)": f"{zones[4]*100:.1f}%"
        }

        # Select exercises based on preferences and goal
        exercise_selection = self._select_exercises(exercise_prefs, goal)

        # Determine periodization strategy
        if goal == FitnessGoal.ENDURANCE:
            periodization = "Linear progression with base/build/peak phases"
        elif goal in [FitnessGoal.STRENGTH, FitnessGoal.POWER]:
            periodization = "Undulating periodization with heavy/medium/light days"
        else:
            periodization = f"Block periodization with {block_length}-week cycles"

        # Nutrition timing based on genetics
        nutrition_timing = self._determine_nutrition_timing(genomic_profile)

        # Supplement recommendations
        supplements = self._recommend_supplements(genomic_profile, goal)

        # Calculate adaptation timeline
        adaptation_timeline = self._calculate_adaptation_timeline(
            genomic_profile, goal, weekly_volume
        )

        return TrainingProgram(
            weekly_volume=weekly_volume,
            intensity_distribution=intensity_distribution,
            exercise_selection=exercise_selection,
            recovery_days=recovery_days,
            periodization=periodization,
            nutrition_timing=nutrition_timing,
            supplement_recommendations=supplements,
            adaptation_timeline=adaptation_timeline
        )

    def _select_exercises(self, exercise_prefs: List[float],
                         goal: FitnessGoal) -> List[str]:
        """Select exercises based on preferences and goal"""
        exercises = []

        # Map preferences to exercise types
        compound_pref = exercise_prefs[0]
        isolation_pref = exercise_prefs[1]
        cardio_pref = exercise_prefs[2]
        plyo_pref = exercise_prefs[3]
        mobility_pref = exercise_prefs[4]

        if compound_pref > 0.5:
            exercises.extend(["Squats", "Deadlifts", "Bench Press", "Pull-ups"])
        if isolation_pref > 0.3:
            exercises.extend(["Bicep Curls", "Leg Extensions", "Calf Raises"])
        if cardio_pref > 0.4:
            exercises.extend(["Running", "Cycling", "Swimming"])
        if plyo_pref > 0.2:
            exercises.extend(["Box Jumps", "Medicine Ball Throws"])
        if mobility_pref > 0.2:
            exercises.extend(["Dynamic Stretching", "Yoga", "Foam Rolling"])

        return exercises[:8]  # Limit to 8 exercises

    def _determine_nutrition_timing(self, genomic_profile: Dict) -> Dict[str, str]:
        """Determine optimal nutrition timing based on genetics"""
        timing = {}

        metabolism_score = genomic_profile.get("metabolism_score", 0.5)

        if metabolism_score > 0.7:
            # Fast metabolism - need more frequent feeding
            timing["pre_workout"] = "30-45 min before: Carbs (40g) + Protein (20g)"
            timing["post_workout"] = "Within 30 min: Carbs (60g) + Protein (30g)"
            timing["strategy"] = "Frequent meals every 3-4 hours"
        else:
            # Slower metabolism - strategic timing
            timing["pre_workout"] = "60-90 min before: Moderate carbs (25g)"
            timing["post_workout"] = "Within 60 min: Protein (25g) + Carbs (40g)"
            timing["strategy"] = "Time-restricted feeding window"

        return timing

    def _recommend_supplements(self, genomic_profile: Dict,
                              goal: FitnessGoal) -> List[str]:
        """Recommend supplements based on genetics and goal"""
        supplements = []

        # Base recommendations
        supplements.append("Vitamin D3 (2000-4000 IU/day)")

        # Genomic-based recommendations
        if genomic_profile.get("recovery_score", 0.5) < 0.4:
            supplements.append("Omega-3 (2-3g EPA/DHA daily)")
            supplements.append("Magnesium Glycinate (400mg)")

        if genomic_profile.get("power_score", 0.5) > 0.7:
            supplements.append("Creatine Monohydrate (5g daily)")
            supplements.append("Beta-Alanine (3-5g daily)")

        if genomic_profile.get("endurance_score", 0.5) > 0.7:
            supplements.append("Beetroot Extract (500mg)")
            supplements.append("L-Citrulline (6-8g)")

        # Goal-specific
        if goal == FitnessGoal.WEIGHT_LOSS:
            supplements.append("Green Tea Extract (EGCG 300-400mg)")
        elif goal == FitnessGoal.STRENGTH:
            supplements.append("HMB (3g daily)")

        return supplements[:5]  # Limit to 5 supplements

    def _calculate_adaptation_timeline(self, genomic_profile: Dict,
                                      goal: FitnessGoal,
                                      weekly_volume: int) -> int:
        """Calculate expected weeks to significant adaptation"""
        base_timeline = 8  # Base adaptation period

        # Adjust based on genetics
        adaptation_rate = genomic_profile.get("adaptation_rate", 0.5)
        if adaptation_rate > 0.7:
            base_timeline -= 2  # Fast adapter
        elif adaptation_rate < 0.3:
            base_timeline += 3  # Slow adapter

        # Adjust based on goal
        if goal == FitnessGoal.STRENGTH:
            base_timeline += 4  # Strength takes longer
        elif goal == FitnessGoal.ENDURANCE:
            base_timeline += 2  # Endurance adaptations

        # Adjust based on volume
        if weekly_volume > 400:
            base_timeline -= 1  # Higher volume = faster progress

        return max(4, min(16, base_timeline))