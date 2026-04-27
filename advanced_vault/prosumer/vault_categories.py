"""
Personal Data Vault Categories

Defines semantic document categories for prosumer use cases.
Each category has:
- Associated file types and MIME patterns
- RAG configuration (chunk size, overlap, retrieval strategy)
- Training preset recommendation
- Privacy level and encryption requirements
- Example documents and keywords for auto-classification
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from enum import Enum
import re


class PrivacyLevel(Enum):
    """Privacy classification for vault categories."""
    STANDARD = "standard"      # Encrypted at rest, standard access
    SENSITIVE = "sensitive"    # Encrypted at rest, additional logging
    CRITICAL = "critical"      # Encrypted at rest, HSM key storage, audit all access


@dataclass
class VaultCategory:
    """Definition of a personal data vault category."""
    
    id: str
    name: str
    description: str
    icon: str  # Emoji or icon identifier
    color: str  # Hex color for UI
    
    # Document type detection
    file_extensions: Set[str] = field(default_factory=set)
    mime_patterns: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    header_patterns: List[re.Pattern] = field(default_factory=list)
    
    # RAG configuration
    chunk_size: int = 512
    chunk_overlap: int = 128
    retrieval_top_k: int = 5
    retrieval_strategy: str = "semantic"  # semantic, keyword, hybrid
    
    # Training configuration
    recommended_preset: str = "general"
    training_data_requirements: str = ""
    min_documents_for_training: int = 5
    
    # Privacy
    privacy_level: PrivacyLevel = PrivacyLevel.STANDARD
    requires_explicit_consent: bool = False
    retention_days: Optional[int] = None  # None = indefinite
    
    # Examples for onboarding
    example_documents: List[str] = field(default_factory=list)
    example_questions: List[str] = field(default_factory=list)
    
    def matches_file(self, filename: str, mime_type: str = "") -> float:
        """Return confidence score (0.0-1.0) that a file belongs to this category."""
        score = 0.0
        
        # Check file extension
        ext = filename.lower().split('.')[-1] if '.' in filename else ""
        if ext in self.file_extensions:
            score += 0.4
        
        # Check MIME type
        if mime_type:
            for pattern in self.mime_patterns:
                if mime_type.startswith(pattern.replace("/*", "")):
                    score += 0.3
                    break
        
        # Check filename keywords
        filename_lower = filename.lower()
        for keyword in self.keywords:
            if keyword.lower() in filename_lower:
                score += 0.2
                break
        
        return min(score, 1.0)
    
    def classify_content(self, text: str) -> float:
        """Classify document content and return confidence score."""
        text_lower = text.lower()
        score = 0.0
        
        # Check keywords in content
        keyword_hits = sum(1 for kw in self.keywords if kw.lower() in text_lower)
        score += min(keyword_hits * 0.15, 0.5)
        
        # Check header patterns
        for pattern in self.header_patterns:
            if pattern.search(text):
                score += 0.3
                break
        
        return min(score, 1.0)


# Define vault categories

HEALTH_VAULT = VaultCategory(
    id="health",
    name="Health Vault",
    description="Medical records, prescriptions, lab results, and health history",
    icon="🏥",
    color="#E53935",
    file_extensions={"pdf", "jpg", "jpeg", "png", "txt", "csv", "json", "xml", "hl7", "fhir"},
    mime_patterns=["application/pdf", "image/", "text/", "application/json", "application/xml"],
    keywords=[
        "medical", "prescription", "diagnosis", "lab", "blood", "test", "hospital",
        "doctor", "patient", "medication", "allergy", "vaccine", "immunization",
        "insurance", "claim", "treatment", "symptom", "x-ray", "mri", "ct",
        "pharmacy", "dosage", "mg", "tablet", "capsule", "injection",
        "blood pressure", "cholesterol", "glucose", "a1c", "bmi",
    ],
    header_patterns=[
        re.compile(r"patient\s+(name|id|date\s+of\s+birth)", re.IGNORECASE),
        re.compile(r"medical\s+record", re.IGNORECASE),
        re.compile(r"prescription\s+ #(\d+)", re.IGNORECASE),
        re.compile(r"laboratory\s+results", re.IGNORECASE),
        re.compile(r"diagnosis:\s*", re.IGNORECASE),
        re.compile(r"vital\s+signs", re.IGNORECASE),
        re.compile(r"medication\s+list", re.IGNORECASE),
        re.compile(r"allergies:\s*", re.IGNORECASE),
    ],
    chunk_size=256,
    chunk_overlap=64,
    retrieval_top_k=8,
    retrieval_strategy="hybrid",
    recommended_preset="health_advisor",
    training_data_requirements="Medical records, prescriptions, lab results, discharge summaries",
    min_documents_for_training=3,
    privacy_level=PrivacyLevel.CRITICAL,
    requires_explicit_consent=True,
    example_documents=[
        "Annual physical exam results",
        "Prescription list from CVS",
        "Blood test results (CBC, lipid panel)",
        "Insurance Explanation of Benefits",
        "Vaccination record",
    ],
    example_questions=[
        "What medications am I currently taking?",
        "When was my last blood test and what were the results?",
        "Do any of my medications interact with each other?",
        "What was my diagnosis from the hospital visit in March?",
    ],
)

FINANCE_VAULT = VaultCategory(
    id="finance",
    name="Financial Vault",
    description="Bank statements, tax returns, investment records, and financial documents",
    icon="💰",
    color="#43A047",
    file_extensions={"pdf", "csv", "xls", "xlsx", "ofx", "qfx", "txt"},
    mime_patterns=["application/pdf", "text/csv", "application/vnd.ms-excel", "text/"],
    keywords=[
        "bank", "statement", "transaction", "deposit", "withdrawal", "balance",
        "tax", "irs", "return", "deduction", "refund", "w-2", "1099", "1040",
        "investment", "portfolio", "stock", "bond", "dividend", "capital", "gain",
        "mortgage", "loan", "credit", "debt", "interest", "apr", "payment",
        "budget", "expense", "income", "salary", "revenue", "profit",
        "retirement", "401k", "ira", "pension", "social security",
        "insurance", "premium", "claim", "policy",
    ],
    header_patterns=[
        re.compile(r"bank\s+statement", re.IGNORECASE),
        re.compile(r"account\s+(number|ending\s+in)", re.IGNORECASE),
        re.compile(r"form\s+1040", re.IGNORECASE),
        re.compile(r"w-2\s+wage", re.IGNORECASE),
        re.compile(r"1099-[a-z]+", re.IGNORECASE),
        re.compile(r"investment\s+summary", re.IGNORECASE),
        re.compile(r"portfolio\s+(value|balance)", re.IGNORECASE),
        re.compile(r"transaction\s+history", re.IGNORECASE),
    ],
    chunk_size=512,
    chunk_overlap=128,
    retrieval_top_k=5,
    retrieval_strategy="semantic",
    recommended_preset="tax_assistant",
    training_data_requirements="Bank statements, tax returns, investment statements, receipts",
    min_documents_for_training=5,
    privacy_level=PrivacyLevel.SENSITIVE,
    example_documents=[
        "2024 Tax Return (Form 1040)",
        "Chase Bank Statement - March 2025",
        "Fidelity Investment Summary",
        "Mortgage statement",
        "W-2 from employer",
    ],
    example_questions=[
        "How much did I spend on groceries last quarter?",
        "What deductions can I claim for 2024?",
        "What's my current investment allocation?",
        "When is my mortgage payment due?",
    ],
)

LEGAL_VAULT = VaultCategory(
    id="legal",
    name="Legal Vault",
    description="Contracts, wills, immigration papers, and legal documents",
    icon="⚖️",
    color="#1E88E5",
    file_extensions={"pdf", "doc", "docx", "txt", "rtf"},
    mime_patterns=["application/pdf", "application/msword", "text/"],
    keywords=[
        "contract", "agreement", "terms", "conditions", "clause", "provision",
        "will", "testament", "estate", "trust", "executor", "beneficiary",
        "immigration", "visa", "green card", "citizenship", "passport",
        "court", "lawsuit", "plaintiff", "defendant", "attorney", "lawyer",
        "nda", "non-disclosure", "confidentiality", "ip", "patent", "trademark",
        "lease", "rental", "property", "deed", "title", "hoa",
        "power of attorney", "notary", "affidavit", "subpoena",
    ],
    header_patterns=[
        re.compile(r"contract\s+(between|for|agreement)", re.IGNORECASE),
        re.compile(r"last\s+will\s+and\s+testament", re.IGNORECASE),
        re.compile(r"non-disclosure\s+agreement", re.IGNORECASE),
        re.compile(r"lease\s+agreement", re.IGNORECASE),
        re.compile(r"power\s+of\s+attorney", re.IGNORECASE),
        re.compile(r"immigration\s+form\s+i-\d+", re.IGNORECASE),
        re.compile(r"employment\s+agreement", re.IGNORECASE),
    ],
    chunk_size=1024,
    chunk_overlap=256,
    retrieval_top_k=3,
    retrieval_strategy="semantic",
    recommended_preset="legal_companion",
    training_data_requirements="Contracts, legal correspondence, court filings, immigration forms",
    min_documents_for_training=3,
    privacy_level=PrivacyLevel.SENSITIVE,
    example_documents=[
        "Employment contract",
        "Last Will and Testament",
        "Lease agreement",
        "NDA with client",
        "Immigration Form I-485",
    ],
    example_questions=[
        "When does my employment contract expire?",
        "What are the termination clauses in my lease?",
        "What immigration forms do I need to file next?",
        "Who are the beneficiaries in my will?",
    ],
)

PERSONAL_VAULT = VaultCategory(
    id="personal",
    name="Personal Knowledge Vault",
    description="Journals, notes, emails, and personal knowledge",
    icon="🧠",
    color="#8E24AA",
    file_extensions={"txt", "md", "pdf", "doc", "docx", "html", "json", "csv"},
    mime_patterns=["text/", "application/pdf", "application/json"],
    keywords=[
        "journal", "diary", "entry", "note", "thought", "idea", "reflection",
        "email", "correspondence", "letter", "message", "communication",
        "book", "highlight", "quote", "summary", "review",
        "travel", "itinerary", "booking", "reservation", "ticket",
        "family", "genealogy", "history", "memory", "photo",
        "goal", "plan", "project", "todo", "task", "reminder",
        "recipe", "cooking", "ingredient", "meal", "nutrition",
        "workout", "exercise", "fitness", "training", "run", "yoga",
    ],
    header_patterns=[
        re.compile(r"dear\s+", re.IGNORECASE),
        re.compile(r"journal\s+entry", re.IGNORECASE),
        re.compile(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+\w+\s+\d{1,2}", re.IGNORECASE),
        re.compile(r"from:\s*\S+@\S+", re.IGNORECASE),
        re.compile(r"subject:\s*", re.IGNORECASE),
        re.compile(r"itinerary\s+for", re.IGNORECASE),
        re.compile(r"booking\s+confirmation", re.IGNORECASE),
    ],
    chunk_size=512,
    chunk_overlap=128,
    retrieval_top_k=6,
    retrieval_strategy="hybrid",
    recommended_preset="life_archivist",
    training_data_requirements="Journals, emails, notes, book highlights, travel itineraries",
    min_documents_for_training=10,
    privacy_level=PrivacyLevel.STANDARD,
    example_documents=[
        "Daily journal entries",
        "Email exports from Gmail",
        "Kindle book highlights",
        "Travel itineraries",
        "Project notes and ideas",
    ],
    example_questions=[
        "What did I write about my trip to Japan?",
        "Summarize my goals from last year",
        "What books have I read recently?",
        "Find emails about the apartment search",
    ],
)

# Registry of all vault categories
VAULT_CATEGORIES: Dict[str, VaultCategory] = {
    "health": HEALTH_VAULT,
    "finance": FINANCE_VAULT,
    "legal": LEGAL_VAULT,
    "personal": PERSONAL_VAULT,
}


def get_category_for_document(
    filename: str,
    mime_type: str = "",
    content_preview: str = "",
    min_confidence: float = 0.3
) -> Tuple[Optional[VaultCategory], float]:
    """
    Determine the best vault category for a document.
    
    Args:
        filename: Name of the file
        mime_type: MIME type if known
        content_preview: First ~2000 characters of content for text analysis
        min_confidence: Minimum confidence threshold
    
    Returns:
        Tuple of (category, confidence) or (None, 0.0) if no match
    """
    scores: List[Tuple[VaultCategory, float]] = []
    
    for category in VAULT_CATEGORIES.values():
        # Score based on filename and MIME type
        file_score = category.matches_file(filename, mime_type)
        
        # Score based on content if available
        content_score = 0.0
        if content_preview:
            content_score = category.classify_content(content_preview)
        
        # Combined score (content has higher weight if available)
        if content_preview:
            combined = file_score * 0.3 + content_score * 0.7
        else:
            combined = file_score
        
        scores.append((category, combined))
    
    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    
    best_category, best_score = scores[0]
    
    if best_score >= min_confidence:
        return best_category, best_score
    
    # If no strong match, default to personal vault
    return PERSONAL_VAULT, 0.0


def get_category_by_id(category_id: str) -> Optional[VaultCategory]:
    """Get a vault category by its ID."""
    return VAULT_CATEGORIES.get(category_id)


def list_categories() -> List[VaultCategory]:
    """List all available vault categories."""
    return list(VAULT_CATEGORIES.values())
