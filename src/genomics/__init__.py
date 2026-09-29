"""
Genomics Processing Pipeline for WDVA Genetic Fitness Platform
Copyright © 2025 Zygmunt Dyras. Licensed under the Apache License 2.0 (see LICENSE).
"""

from .vcf_processor import (
    VCFProcessor,
    GeneticVariant,
    ClinicalSignificance
)

from .evo2_optimizer import (
    EVO2GeneticOptimizer,
    TrainingProgram,
    TrainingIndividual,
    FitnessGoal
)

__all__ = [
    "VCFProcessor",
    "GeneticVariant",
    "ClinicalSignificance",
    "EVO2GeneticOptimizer",
    "TrainingProgram",
    "TrainingIndividual",
    "FitnessGoal"
]

__version__ = "1.0.0"
__author__ = "Zygmunt Dyras"