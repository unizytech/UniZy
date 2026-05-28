"""
Suggested Questions Service

Provides pre-defined question templates by category for the Q&A Engine.

Categories:
- Clinical: Clinical insights, patterns
- Risk: Risk assessment, severity
- Referrals: Referral patterns, allied health
- Interventions: Intervention tracking, outcomes
- Triage: Triage patterns, red flags
- Analytics: Usage stats, trends, counts
"""

import logging
from typing import Optional, List
from uuid import UUID

from models.qa_models import (
    SuggestedQuestion,
    QuestionCategory,
    QueryIntent,
    SuggestedQuestionsResponse
)

logger = logging.getLogger(__name__)

# Pre-defined suggested questions by category
SUGGESTED_QUESTIONS = [
    # ============================================================================
    # Clinical Questions
    # ============================================================================
    SuggestedQuestion(
        id="clinical_01",
        question="What are the most common diagnoses across my patients?",
        category=QuestionCategory.CLINICAL,
        description="View distribution of diagnoses",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["DIAGNOSIS"]
    ),
    SuggestedQuestion(
        id="clinical_02",
        question="Show patients with diabetes and hypertension",
        category=QuestionCategory.CLINICAL,
        description="Find patients with comorbidities",
        expected_intent=QueryIntent.HYBRID,
        expected_segment_codes=["DIAGNOSIS", "PAST_MEDICAL_HISTORY"]
    ),
    SuggestedQuestion(
        id="clinical_03",
        question="What medications are most frequently prescribed?",
        category=QuestionCategory.CLINICAL,
        description="Analyze prescription patterns",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["PRESCRIPTION"]
    ),
    SuggestedQuestion(
        id="clinical_04",
        question="Find patients with abnormal vital signs",
        category=QuestionCategory.CLINICAL,
        description="Identify patients needing attention",
        expected_intent=QueryIntent.HYBRID,
        expected_segment_codes=["VITAL_SIGNS"]
    ),
    SuggestedQuestion(
        id="clinical_05",
        question="What investigations are commonly ordered?",
        category=QuestionCategory.CLINICAL,
        description="Review investigation patterns",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["INVESTIGATIONS"]
    ),

    # ============================================================================
    # Risk Assessment Questions
    # ============================================================================
    SuggestedQuestion(
        id="risk_01",
        question="Which patients have high severity assessments?",
        category=QuestionCategory.RISK,
        description="Identify high-risk patients",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="risk_02",
        question="Show patients at risk of treatment non-compliance",
        category=QuestionCategory.RISK,
        description="Find compliance risk patients",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="risk_03",
        question="What are the common risk factors in critical cases?",
        category=QuestionCategory.RISK,
        description="Analyze critical case patterns",
        expected_intent=QueryIntent.SEMANTIC,
    ),
    SuggestedQuestion(
        id="risk_04",
        question="Patients with quality of care concerns",
        category=QuestionCategory.RISK,
        description="Review quality risk assessments",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="risk_05",
        question="Show patients with retention risk flags",
        category=QuestionCategory.RISK,
        description="Identify patients at risk of leaving",
        expected_intent=QueryIntent.HYBRID,
    ),

    # ============================================================================
    # Referral Questions
    # ============================================================================
    SuggestedQuestion(
        id="referral_01",
        question="Which patients need allied health referrals?",
        category=QuestionCategory.REFERRALS,
        description="Find patients needing support services",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="referral_02",
        question="Show physiotherapy referral recommendations",
        category=QuestionCategory.REFERRALS,
        description="Review physio referral needs",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="referral_03",
        question="Patients recommended for nutrition counseling",
        category=QuestionCategory.REFERRALS,
        description="Find nutrition referral candidates",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="referral_04",
        question="What specialist referrals are most common?",
        category=QuestionCategory.REFERRALS,
        description="Analyze referral patterns",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["FOLLOW_UP", "TREATMENT_PLAN"]
    ),
    SuggestedQuestion(
        id="referral_05",
        question="Show patients needing mental health support",
        category=QuestionCategory.REFERRALS,
        description="Identify mental health referral needs",
        expected_intent=QueryIntent.HYBRID,
    ),

    # ============================================================================
    # Intervention Questions
    # ============================================================================
    SuggestedQuestion(
        id="intervention_01",
        question="What interventions have been recommended this month?",
        category=QuestionCategory.INTERVENTIONS,
        description="Review recent interventions",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="intervention_02",
        question="Show pending intervention follow-ups",
        category=QuestionCategory.INTERVENTIONS,
        description="Find interventions needing action",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="intervention_03",
        question="Which interventions have the best conversion rates?",
        category=QuestionCategory.INTERVENTIONS,
        description="Analyze intervention effectiveness",
        expected_intent=QueryIntent.SQL,
    ),
    SuggestedQuestion(
        id="intervention_04",
        question="Patients with surgical consultation recommendations",
        category=QuestionCategory.INTERVENTIONS,
        description="Find OP-to-IP conversion candidates",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="intervention_05",
        question="Show prescription refill reminders due",
        category=QuestionCategory.INTERVENTIONS,
        description="Find RX refill opportunities",
        expected_intent=QueryIntent.HYBRID,
    ),

    # ============================================================================
    # Triage Questions
    # ============================================================================
    SuggestedQuestion(
        id="triage_01",
        question="Show patients with red flag symptoms",
        category=QuestionCategory.TRIAGE,
        description="Identify urgent cases",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="triage_02",
        question="What are the most common chief complaints?",
        category=QuestionCategory.TRIAGE,
        description="Analyze presenting complaints",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["CHIEF_COMPLAINT"]
    ),
    SuggestedQuestion(
        id="triage_03",
        question="Patients with urgent follow-up needs",
        category=QuestionCategory.TRIAGE,
        description="Find patients needing urgent attention",
        expected_intent=QueryIntent.HYBRID,
        expected_segment_codes=["FOLLOW_UP"]
    ),
    SuggestedQuestion(
        id="triage_04",
        question="Show cases with missing critical investigations",
        category=QuestionCategory.TRIAGE,
        description="Identify investigation gaps",
        expected_intent=QueryIntent.HYBRID,
    ),
    SuggestedQuestion(
        id="triage_05",
        question="Patients with medication safety alerts",
        category=QuestionCategory.TRIAGE,
        description="Review medication safety concerns",
        expected_intent=QueryIntent.HYBRID,
    ),

    # ============================================================================
    # Longitudinal/Temporal Questions (Patient History)
    # ============================================================================
    SuggestedQuestion(
        id="clinical_06",
        question="What changed since the last visit?",
        category=QuestionCategory.CLINICAL,
        description="Compare current vs previous consultation",
        expected_intent=QueryIntent.SEMANTIC,
    ),
    SuggestedQuestion(
        id="clinical_07",
        question="Compare medications with previous consultation",
        category=QuestionCategory.CLINICAL,
        description="Track medication changes over time",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["PRESCRIPTION"]
    ),
    SuggestedQuestion(
        id="clinical_08",
        question="Has blood pressure improved since first visit?",
        category=QuestionCategory.CLINICAL,
        description="Track vital sign trends over time",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["VITAL_SIGNS"]
    ),
    SuggestedQuestion(
        id="clinical_09",
        question="What diagnoses were added since last month?",
        category=QuestionCategory.CLINICAL,
        description="Track new diagnoses over time",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["DIAGNOSIS"]
    ),
    SuggestedQuestion(
        id="clinical_10",
        question="Show prescription history over the last 3 visits",
        category=QuestionCategory.CLINICAL,
        description="Review medication changes across visits",
        expected_intent=QueryIntent.HYBRID,
        expected_segment_codes=["PRESCRIPTION"]
    ),
    SuggestedQuestion(
        id="clinical_11",
        question="What complaints were resolved since last visit?",
        category=QuestionCategory.CLINICAL,
        description="Track complaint resolution over time",
        expected_intent=QueryIntent.SEMANTIC,
        expected_segment_codes=["CHIEF_COMPLAINT"]
    ),

    # ============================================================================
    # Analytics Questions
    # ============================================================================
    SuggestedQuestion(
        id="analytics_01",
        question="How many extractions were done this month?",
        category=QuestionCategory.ANALYTICS,
        description="View extraction volume",
        expected_intent=QueryIntent.SQL,
    ),
    SuggestedQuestion(
        id="analytics_02",
        question="Show extraction trends over the past week",
        category=QuestionCategory.ANALYTICS,
        description="View daily extraction trends",
        expected_intent=QueryIntent.SQL,
    ),
    SuggestedQuestion(
        id="analytics_03",
        question="Distribution of consultation types",
        category=QuestionCategory.ANALYTICS,
        description="Analyze consultation type mix",
        expected_intent=QueryIntent.SQL,
    ),
    SuggestedQuestion(
        id="analytics_04",
        question="Average severity score by consultation type",
        category=QuestionCategory.ANALYTICS,
        description="Compare severity across types",
        expected_intent=QueryIntent.SQL,
    ),
    SuggestedQuestion(
        id="analytics_05",
        question="Intervention conversion rate this month",
        category=QuestionCategory.ANALYTICS,
        description="Track intervention success",
        expected_intent=QueryIntent.SQL,
    ),
    SuggestedQuestion(
        id="analytics_06",
        question="Top 10 diagnoses this month",
        category=QuestionCategory.ANALYTICS,
        description="View most common diagnoses",
        expected_intent=QueryIntent.SQL,
    ),
]


class SuggestedQuestionsService:
    """
    Provides suggested questions for the Q&A Engine.

    Usage:
        service = SuggestedQuestionsService()

        # Get all questions
        questions = service.get_questions()

        # Get by category
        clinical_questions = service.get_questions(category=QuestionCategory.CLINICAL)
    """

    def __init__(self):
        self._questions = SUGGESTED_QUESTIONS

    def get_questions(
        self,
        category: Optional[QuestionCategory] = None,
        limit: int = 50
    ) -> SuggestedQuestionsResponse:
        """
        Get suggested questions, optionally filtered by category.

        Args:
            category: Optional category filter
            limit: Maximum questions to return

        Returns:
            SuggestedQuestionsResponse with questions
        """
        if category:
            filtered = [q for q in self._questions if q.category == category]
        else:
            filtered = self._questions

        return SuggestedQuestionsResponse(
            questions=filtered[:limit],
            category=category,
            count=len(filtered[:limit])
        )

    def get_question_by_id(self, question_id: str) -> Optional[SuggestedQuestion]:
        """Get a specific question by ID"""
        for q in self._questions:
            if q.id == question_id:
                return q
        return None

    def get_categories(self) -> List[QuestionCategory]:
        """Get list of available categories"""
        return list(QuestionCategory)

    def get_questions_for_role(
        self,
        role: str,
        category: Optional[QuestionCategory] = None
    ) -> SuggestedQuestionsResponse:
        """
        Get questions filtered by user role.

        Admin users see all questions.
        Doctors see clinical, risk, and referral questions.
        Nurses see triage and clinical questions.
        """
        questions = self.get_questions(category).questions

        # Role-based filtering
        if role == "doctor":
            allowed_categories = {
                QuestionCategory.CLINICAL,
                QuestionCategory.RISK,
                QuestionCategory.REFERRALS,
                QuestionCategory.TRIAGE,
                QuestionCategory.INTERVENTIONS
            }
            questions = [q for q in questions if q.category in allowed_categories]
        elif role == "nurse":
            allowed_categories = {
                QuestionCategory.CLINICAL,
                QuestionCategory.TRIAGE
            }
            questions = [q for q in questions if q.category in allowed_categories]
        # Admin and others see all

        return SuggestedQuestionsResponse(
            questions=questions,
            category=category,
            count=len(questions)
        )


# Singleton instance
suggested_questions_service = SuggestedQuestionsService()
