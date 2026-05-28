"""
Query Reframer Service

Preprocesses user queries before classification to:
1. Expand medical abbreviations (BP → blood pressure)
2. Correct typos and misspellings (diabeties → diabetes)
3. Normalize colloquial/layman terms (sugar → blood glucose)
4. Clarify vague queries (show patients → show patients with consultation details)
5. Normalize temporal expressions (last week → specific date context)
6. Remove noise/filler words (Can you please show me → show)
7. Add intent clarification hints for better classification

The reframed query is then passed to the classifier for better accuracy.
"""

import json
import logging
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from models.qa_models import (
    ReframedQuery,
    ReframeExpansion,
    ReframeCorrection,
    QAPriorContext
)

logger = logging.getLogger(__name__)

# =============================================================================
# LLM Prompt for Query Reframing
# =============================================================================

REFRAME_SYSTEM_PROMPT = """You are a medical query preprocessor. Your job is to reframe user queries to make them clearer and more searchable in a medical records database.

Your tasks:
1. EXPAND medical abbreviations to their full forms
2. CORRECT typos and misspellings in medical terms
3. NORMALIZE colloquial/layman terms to standard medical terminology
4. CLARIFY vague queries by adding context
5. NORMALIZE temporal expressions with context
6. REMOVE unnecessary filler words while preserving intent
7. ADD hints that help identify what type of medical data is being searched

IMPORTANT RULES:
- Preserve the user's original intent - do NOT change what they're asking for
- Keep the reframed query natural and readable
- Only make changes that improve searchability
- If the query is already clear and correct, return it unchanged
- Do NOT add information the user didn't ask for
- Do NOT remove important query elements

Common Medical Abbreviations to Expand:
- BP → blood pressure / hypertension
- DM → diabetes mellitus
- HTN → hypertension
- Rx → prescription / medication
- Dx → diagnosis
- Hx → history
- SOB → shortness of breath
- OPD/OP → outpatient
- IPD/IP → inpatient
- HR → heart rate
- RR → respiratory rate
- SpO2 → oxygen saturation
- CBC → complete blood count
- LFT → liver function test
- RFT → renal function test
- ECG/EKG → electrocardiogram
- USG → ultrasonography
- MRI → magnetic resonance imaging
- CT → computed tomography
- Pt → patient
- Tx → treatment
- Fx → fracture
- Sx → symptoms
- Px → prognosis

Common Colloquial Terms to Normalize:
- sugar / sugar levels → blood glucose / diabetes
- heart attack → myocardial infarction
- stroke → cerebrovascular accident
- water tablets → diuretics
- blood thinner → anticoagulant
- pain killer → analgesic
- fits → seizure / epilepsy
- loose motion → diarrhea
- cold → upper respiratory infection
- acidity → gastritis / GERD

Common Misspellings:
- diabeties/diabetis → diabetes
- hypertention → hypertension
- perscription → prescription
- asthama → asthma
- colestrol/cholestrol → cholesterol
- pneumonia → pneumonia
- diarrhoea/diarhea → diarrhea
- haemoglobin → hemoglobin
- anaemia → anemia

Respond with JSON only, no markdown."""

REFRAME_USER_PROMPT = """Reframe this medical query:
"{query}"

Current date for temporal context: {current_date}

Respond with JSON in this exact format:
{{
  "reframed_query": "the reframed query text",
  "expansions": [
    {{"original": "BP", "expanded": "blood pressure", "category": "abbreviation"}}
  ],
  "corrections": [
    {{"original": "diabeties", "corrected": "diabetes", "category": "typo"}}
  ],
  "was_modified": true,
  "confidence": 0.95
}}

If no changes needed, set was_modified to false and return the original query as reframed_query."""


# =============================================================================
# Fallback Dictionaries for Offline Reframing
# =============================================================================

ABBREVIATION_MAP = {
    # Vitals & Measurements
    "bp": "blood pressure",
    "hr": "heart rate",
    "rr": "respiratory rate",
    "spo2": "oxygen saturation",
    "temp": "temperature",
    "wt": "weight",
    "ht": "height",
    "bmi": "body mass index",

    # Conditions
    "dm": "diabetes mellitus",
    "htn": "hypertension",
    "cad": "coronary artery disease",
    "copd": "chronic obstructive pulmonary disease",
    "ckd": "chronic kidney disease",
    "chf": "congestive heart failure",
    "mi": "myocardial infarction",
    "cva": "cerebrovascular accident",
    "uti": "urinary tract infection",
    "uri": "upper respiratory infection",
    "rti": "respiratory tract infection",
    "gerd": "gastroesophageal reflux disease",
    "sob": "shortness of breath",
    "loc": "loss of consciousness",
    "nkda": "no known drug allergies",

    # Medical Actions
    "rx": "prescription",
    "dx": "diagnosis",
    "hx": "history",
    "tx": "treatment",
    "fx": "fracture",
    "sx": "symptoms",
    "px": "prognosis",
    "mx": "management",

    # Settings
    "opd": "outpatient department",
    "op": "outpatient",
    "ipd": "inpatient department",
    "ip": "inpatient",
    "icu": "intensive care unit",
    "er": "emergency room",
    "ot": "operation theater",

    # Tests & Investigations
    "cbc": "complete blood count",
    "lft": "liver function test",
    "rft": "renal function test",
    "tft": "thyroid function test",
    "ecg": "electrocardiogram",
    "ekg": "electrocardiogram",
    "usg": "ultrasonography",
    "mri": "magnetic resonance imaging",
    "ct": "computed tomography",
    "xray": "x-ray",
    "hba1c": "glycated hemoglobin",
    "fbs": "fasting blood sugar",
    "ppbs": "postprandial blood sugar",
    "rbs": "random blood sugar",
    "esr": "erythrocyte sedimentation rate",
    "crp": "c-reactive protein",

    # Other
    "pt": "patient",
    "pts": "patients",
    "f/u": "follow up",
    "fu": "follow up",
    "c/o": "complaining of",
    "h/o": "history of",
    "k/c/o": "known case of",
    "s/p": "status post",
    "r/o": "rule out",
    "w/": "with",
    "w/o": "without",
    "yo": "year old",
    "y/o": "year old",
}

COLLOQUIAL_MAP = {
    "sugar": "blood glucose",
    "sugar patient": "diabetic patient",
    "sugar patients": "diabetic patients",
    "heart attack": "myocardial infarction",
    "stroke": "cerebrovascular accident",
    "water tablet": "diuretic",
    "water tablets": "diuretics",
    "blood thinner": "anticoagulant",
    "blood thinners": "anticoagulants",
    "pain killer": "analgesic",
    "pain killers": "analgesics",
    "painkiller": "analgesic",
    "painkillers": "analgesics",
    "fits": "seizure",
    "loose motion": "diarrhea",
    "loose motions": "diarrhea",
    "cold": "upper respiratory infection",
    "common cold": "upper respiratory infection",
    "acidity": "gastritis",
    "gas": "bloating",
    "thyroid": "thyroid disorder",
    "pressure": "hypertension",
    "high pressure": "hypertension",
    "low pressure": "hypotension",
    "high sugar": "hyperglycemia",
    "low sugar": "hypoglycemia",
    "nerve problem": "neuropathy",
    "kidney problem": "renal dysfunction",
    "liver problem": "hepatic dysfunction",
    "heart problem": "cardiac condition",
    "breathing problem": "respiratory distress",
    "urine problem": "urinary disorder",
    "skin problem": "dermatological condition",
    "eye problem": "ophthalmic condition",
    "joint pain": "arthralgia",
    "back pain": "dorsalgia",
    "chest pain": "chest discomfort",
    "stomach pain": "abdominal pain",
    "headache": "cephalalgia",
}

TYPO_MAP = {
    "diabeties": "diabetes",
    "diabetis": "diabetes",
    "diabetese": "diabetes",
    "hypertention": "hypertension",
    "hypertenshun": "hypertension",
    "perscription": "prescription",
    "prescripton": "prescription",
    "asthama": "asthma",
    "asthema": "asthma",
    "colestrol": "cholesterol",
    "cholestrol": "cholesterol",
    "cholesteral": "cholesterol",
    "pneumonia": "pneumonia",
    "pnemonia": "pneumonia",
    "nuemonia": "pneumonia",
    "diarhea": "diarrhea",
    "diarrhoea": "diarrhea",
    "diarrea": "diarrhea",
    "haemoglobin": "hemoglobin",
    "hemogloben": "hemoglobin",
    "anaemia": "anemia",
    "anemia": "anemia",
    "arthiritis": "arthritis",
    "arthritus": "arthritis",
    "alergies": "allergies",
    "allergys": "allergies",
    "symtoms": "symptoms",
    "symptomes": "symptoms",
    "medicaton": "medication",
    "medicane": "medicine",
    "medecine": "medicine",
    "treatement": "treatment",
    "treatmant": "treatment",
    "diagnosys": "diagnosis",
    "diagnisis": "diagnosis",
    "investgation": "investigation",
    "investigaton": "investigation",
    "consultaton": "consultation",
    "consultaion": "consultation",
    "paitent": "patient",
    "patiant": "patient",
    "presure": "pressure",
    "pressue": "pressure",
}

# Noise words to remove from start of queries
NOISE_PREFIXES = [
    "can you please",
    "can you",
    "could you please",
    "could you",
    "please",
    "i want to",
    "i would like to",
    "i need to",
    "help me",
    "show me",
    "tell me",
    "give me",
    "find me",
    "get me",
    "hey",
    "hi",
    "hello",
]


# =============================================================================
# Query Reframer Service
# =============================================================================

class QueryReframerService:
    """
    Preprocesses user queries before classification.

    Usage:
        service = QueryReframerService()

        reframed = await service.reframe(
            query="BP patients with diabeties last week"
        )

        print(reframed.reframed_query)
        # "blood pressure patients with diabetes from the last 7 days"

        print(reframed.expansions)
        # [{"original": "BP", "expanded": "blood pressure", "category": "abbreviation"}]
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy load Gemini client"""
        if self._client is None:
            from services.gemini_client_factory import get_gemini_client
            self._client = get_gemini_client()
        return self._client

    async def reframe(
        self,
        query: str,
        use_llm: bool = True,
        prior_context: Optional[QAPriorContext] = None
    ) -> ReframedQuery:
        """
        Reframe a user query to improve classification and search accuracy.

        Args:
            query: The user's original query
            use_llm: If True, use Gemini for intelligent reframing.
                     If False, use dictionary-based fallback only.
            prior_context: Previous Q&A exchange for resolving follow-up references

        Returns:
            ReframedQuery with the reframed query and transformation details
        """
        start_time = time.time()

        # Always apply basic preprocessing first
        cleaned_query = self._basic_preprocess(query)

        if use_llm:
            try:
                result = await self._llm_reframe(cleaned_query, prior_context=prior_context)
                result.reframe_time_ms = int((time.time() - start_time) * 1000)
                return result
            except Exception as e:
                logger.warning(f"LLM reframing failed, using fallback: {e}")

        # Fallback to dictionary-based reframing
        result = self._fallback_reframe(cleaned_query)
        result.reframe_time_ms = int((time.time() - start_time) * 1000)
        return result

    def _basic_preprocess(self, query: str) -> str:
        """Basic preprocessing: trim, normalize whitespace"""
        # Trim and normalize whitespace
        query = " ".join(query.split())
        return query

    async def _llm_reframe(self, query: str, prior_context: Optional[QAPriorContext] = None) -> ReframedQuery:
        """Use Gemini to intelligently reframe the query"""
        client = self._get_client()

        current_date = datetime.now().strftime("%Y-%m-%d")

        user_prompt = REFRAME_USER_PROMPT.format(
            query=query,
            current_date=current_date
        )

        # Inject conversation context for follow-up reference resolution
        if prior_context:
            context_block = '\n\nPrevious conversation context:'
            context_block += f'\n- User asked: {prior_context.query}'
            if prior_context.narrative:
                # Truncate and sanitize to avoid breaking JSON output
                narrative_clean = prior_context.narrative[:200].replace('"', "'").replace('\n', ' ')
                context_block += f'\n- Assistant answered: {narrative_clean}'
            context_block += '\nUse this context to resolve references like "this", "that", "it", "this prescription", "that diagnosis" in the current query.'
            user_prompt += context_block

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {"role": "user", "parts": [{"text": REFRAME_SYSTEM_PROMPT}]},
                {"role": "model", "parts": [{"text": "I understand. I'll reframe medical queries and respond with JSON only."}]},
                {"role": "user", "parts": [{"text": user_prompt}]}
            ],
            config={
                "temperature": 0.1,
                "max_output_tokens": 800,
            }
        )

        # Parse response
        response_text = response.text.strip()

        # Clean markdown if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        result = json.loads(response_text)

        # Build expansion objects
        expansions = [
            ReframeExpansion(
                original=exp.get("original", ""),
                expanded=exp.get("expanded", ""),
                category=exp.get("category", "abbreviation")
            )
            for exp in result.get("expansions", [])
        ]

        # Build correction objects
        corrections = [
            ReframeCorrection(
                original=corr.get("original", ""),
                corrected=corr.get("corrected", ""),
                category=corr.get("category", "typo")
            )
            for corr in result.get("corrections", [])
        ]

        return ReframedQuery(
            original_query=query,
            reframed_query=result.get("reframed_query", query),
            expansions=expansions,
            corrections=corrections,
            confidence=float(result.get("confidence", 0.9)),
            was_modified=result.get("was_modified", False)
        )

    def _fallback_reframe(self, query: str) -> ReframedQuery:
        """Dictionary-based fallback reframing when LLM is unavailable"""
        original_query = query
        expansions: List[ReframeExpansion] = []
        corrections: List[ReframeCorrection] = []

        # 1. Remove noise prefixes
        query_lower = query.lower()
        for prefix in NOISE_PREFIXES:
            if query_lower.startswith(prefix):
                query = query[len(prefix):].strip()
                query_lower = query.lower()
                corrections.append(ReframeCorrection(
                    original=prefix,
                    corrected="(removed)",
                    category="noise"
                ))
                break

        # 2. Apply typo corrections (case-insensitive)
        words = query.split()
        corrected_words = []
        for word in words:
            word_lower = word.lower()
            # Remove punctuation for matching
            word_clean = word_lower.rstrip(".,;:!?")
            punctuation = word_lower[len(word_clean):]

            if word_clean in TYPO_MAP:
                corrected = TYPO_MAP[word_clean]
                corrections.append(ReframeCorrection(
                    original=word_clean,
                    corrected=corrected,
                    category="typo"
                ))
                # Preserve original case pattern if possible
                if word[0].isupper():
                    corrected = corrected.capitalize()
                corrected_words.append(corrected + punctuation)
            else:
                corrected_words.append(word)

        query = " ".join(corrected_words)

        # 3. Apply colloquial term normalization
        query_lower = query.lower()
        for colloquial, medical in sorted(COLLOQUIAL_MAP.items(), key=lambda x: -len(x[0])):
            if colloquial in query_lower:
                # Find and replace while trying to preserve case
                start_idx = query_lower.find(colloquial)
                if start_idx != -1:
                    original_text = query[start_idx:start_idx + len(colloquial)]
                    query = query[:start_idx] + medical + query[start_idx + len(colloquial):]
                    query_lower = query.lower()
                    expansions.append(ReframeExpansion(
                        original=original_text,
                        expanded=medical,
                        category="colloquial"
                    ))

        # 4. Apply abbreviation expansions
        words = query.split()
        expanded_words = []
        for word in words:
            word_lower = word.lower()
            # Remove punctuation for matching
            word_clean = word_lower.rstrip(".,;:!?")
            punctuation = word_lower[len(word_clean):]

            if word_clean in ABBREVIATION_MAP:
                expanded = ABBREVIATION_MAP[word_clean]
                expansions.append(ReframeExpansion(
                    original=word_clean.upper(),
                    expanded=expanded,
                    category="abbreviation"
                ))
                expanded_words.append(expanded + punctuation)
            else:
                expanded_words.append(word)

        query = " ".join(expanded_words)

        # Check if anything changed
        was_modified = query.lower() != original_query.lower() or len(corrections) > 0

        # Calculate confidence based on number of transformations
        # More transformations = slightly lower confidence
        num_changes = len(expansions) + len(corrections)
        confidence = max(0.6, 0.95 - (num_changes * 0.05))

        return ReframedQuery(
            original_query=original_query,
            reframed_query=query,
            expansions=expansions,
            corrections=corrections,
            confidence=confidence,
            was_modified=was_modified
        )

    def reframe_sync(self, query: str) -> ReframedQuery:
        """
        Synchronous fallback reframing (no LLM).
        Useful for quick preprocessing without async context.
        """
        cleaned_query = self._basic_preprocess(query)
        return self._fallback_reframe(cleaned_query)


# Singleton instance
query_reframer_service = QueryReframerService()
