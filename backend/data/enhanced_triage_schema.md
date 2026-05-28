# Enhanced Clinical Triage RAG Schema v2

## Format Coverage

| STG Type | Example | Key Adaptations |
|----------|---------|-----------------|
| **Narrative Guidelines** | Hypertension | Chapters → sections, tables → structured data |
| **Visual Workflows** | Rhinosinusitis | Flowchart nodes → decision trees |
| **Step-wise Protocols** | Epistaxis | Numbered steps → ordered arrays with escalation |

---

## Enhanced JSON Schema

```json
{
  "document_meta": {
    "source": "Ministry of Health STG / ICMR STW",
    "specialty": "cardiology | ent | obstetrics_gynaecology",
    "document_type": "narrative_guideline | visual_workflow | step_protocol",
    "version": "2017",
    "icd_codes": ["I10", "I11.9"],
    "language": "en"
  },

  "conditions": [
    {
      "condition_id": "cardio_htn_001",
      "name": "Primary Hypertension",
      "aliases": ["Essential Hypertension", "High Blood Pressure"],
      "icd_codes": ["I10", "I11.9"],

      "classification": {
        "type": "graded",
        "grades": [
          {
            "grade": "Grade 1",
            "criteria": {
              "sbp_range": [140, 159],
              "dbp_range": [90, 99],
              "operator": "and/or"
            },
            "default_urgency": "routine"
          },
          {
            "grade": "Grade 2", 
            "criteria": {
              "sbp_range": [160, 179],
              "dbp_range": [100, 109],
              "operator": "and/or"
            },
            "default_urgency": "urgent"
          },
          {
            "grade": "Grade 3",
            "criteria": {
              "sbp_min": 180,
              "dbp_min": 110,
              "operator": "and/or"
            },
            "default_urgency": "emergency"
          },
          {
            "grade": "Hypertensive Emergency",
            "criteria": {
              "sbp_min": 180,
              "dbp_min": 110,
              "additional": "with acute target organ damage"
            },
            "default_urgency": "emergency",
            "symptoms_mnemonic": "ABCDEFG"
          }
        ]
      },

      "triage_metadata": {
        "urgency_levels": ["routine", "urgent", "emergency"],
        "default_urgency": "routine",
        
        "emergency_triggers": [
          {
            "trigger": "BP >180/110 with acute organ damage",
            "symptoms": ["altered consciousness", "breathlessness", "chest pain", "limb weakness", "decreased urine output", "papilledema", "seizures"],
            "mnemonic": "ABCDEFG"
          }
        ],
        
        "red_flags": [
          {
            "flag": "Resistant hypertension",
            "definition": "BP uncontrolled on 3 drugs",
            "action": "refer_specialist"
          },
          {
            "flag": "Suspected secondary hypertension",
            "clues": ["onset <30 or >60 years", "paroxysms of palpitation/headache/perspiration", "snoring with apnea"],
            "action": "comprehensive_evaluation"
          }
        ],
        
        "referral_triggers": [
          {
            "condition": "BP uncontrolled on 3 antihypertensives",
            "refer_to": "medical_college_specialist"
          },
          {
            "condition": "Hypertensive emergency",
            "refer_to": "emergency_department"
          }
        ]
      },

      "clinical_presentation": {
        "symptoms": [
          {"symptom": "headache", "frequency": "common", "note": "often occipital, morning"},
          {"symptom": "asymptomatic", "frequency": "most_common", "note": "silent killer"}
        ],
        "examination_findings": [
          "elevated BP on repeated measurements",
          "fundoscopy: hemorrhages, exudates, papilledema in severe cases"
        ],
        "when_to_suspect": "Adults >18 years with BP ≥140/90 on 2+ occasions"
      },

      "differential_diagnosis": [
        {
          "condition": "White coat hypertension",
          "distinguishing_feature": "Normal BP at home/ABPM",
          "prevalence": "32% of hypertensives"
        },
        {
          "condition": "Secondary hypertension",
          "causes": ["renal parenchymal disease", "renovascular", "pheochromocytoma", "Cushing syndrome", "coarctation of aorta"]
        }
      ],

      "investigations": {
        "essential": {
          "description": "All patients at PHC level",
          "tests": [
            {"test": "fasting blood glucose", "abnormal": ">126 mg/dl"},
            {"test": "urinalysis for proteinuria", "significance": "doubles mortality risk"}
          ]
        },
        "desirable": {
          "description": "Grade 2+ HT, diabetics, proteinuria",
          "tests": ["serum creatinine", "lipid profile", "ECG"]
        },
        "comprehensive": {
          "description": "Grade 3 HT, CKD, heart failure, suspected secondary",
          "tests": ["serum sodium/potassium", "ultrasound kidney", "echocardiography"]
        }
      },

      "treatment_by_care_level": {
        "phc_primary": {
          "lifestyle_modifications": [
            {"intervention": "salt restriction", "target": "<5g/day", "bp_reduction": "4-5 mmHg"},
            {"intervention": "weight reduction", "target": "BMI 18.5-22.9", "bp_reduction": "5-20 mmHg per 10kg"},
            {"intervention": "physical activity", "target": "30 min/day moderate", "bp_reduction": "4-9 mmHg"},
            {"intervention": "smoking cessation", "impact": "reduces CV risk significantly"}
          ],
          "drug_therapy": {
            "first_line": ["CCB (amlodipine)", "ACE inhibitor (enalapril)", "thiazide (HCTZ)"],
            "initiation_criteria": [
              "Grade 2/3 HT",
              "Grade 1 HT with: target organ damage, diabetes, CKD, CVD, ≥3 risk factors",
              "Grade 1 HT after 1-3 months lifestyle trial fails"
            ],
            "target_bp": {
              "age_lt_80": "<140/90 mmHg",
              "age_gte_80": "<150/90 mmHg",
              "diabetics": "<140/90 mmHg"
            }
          }
        },
        "district_hospital": {
          "additional_capabilities": [
            "ECG interpretation",
            "lipid profile",
            "serum creatinine monitoring",
            "resistant HT evaluation"
          ]
        },
        "tertiary_medical_college": {
          "referral_indications": [
            "Resistant hypertension (uncontrolled on 3 drugs)",
            "Suspected secondary hypertension",
            "Hypertensive emergencies requiring IV therapy"
          ],
          "additional_capabilities": [
            "echocardiography",
            "renal artery doppler",
            "24-hour ABPM",
            "endocrine workup"
          ]
        }
      },

      "comorbidity_pathways": [
        {
          "comorbidity": "diabetes",
          "preferred_drugs": ["ACE inhibitor (especially with proteinuria)", "CCB", "thiazide"],
          "avoid": ["high-dose thiazide (glucose intolerance)"],
          "target_bp": "<140/90 mmHg",
          "special_notes": "ACE inhibitor mandatory if proteinuria present"
        },
        {
          "comorbidity": "chronic_kidney_disease",
          "preferred_drugs": ["ACE inhibitor", "CCB"],
          "monitoring": "serum creatinine and potassium within 1 week of starting ACE-I",
          "special_notes": "Loop diuretic if eGFR <30"
        },
        {
          "comorbidity": "heart_failure",
          "preferred_drugs": ["ACE inhibitor", "diuretic", "beta-blocker", "spironolactone"],
          "avoid": ["non-dihydropyridine CCB (verapamil, diltiazem)"]
        },
        {
          "comorbidity": "coronary_artery_disease",
          "preferred_drugs": ["beta-blocker", "ACE inhibitor", "CCB"],
          "special_notes": "Post-MI: must have both BB and ACE-I"
        },
        {
          "comorbidity": "previous_stroke",
          "preferred_drugs": ["ACE inhibitor", "diuretic", "CCB"],
          "special_notes": "Do NOT lower BP in first 72 hours of ischemic stroke"
        }
      ],

      "drug_formulary": [
        {
          "drug_class": "CCB",
          "representative": "amlodipine",
          "initial_dose": "5 mg OD",
          "max_dose": "10 mg OD",
          "low_dose_situations": ["elderly", "low body weight", "add-on therapy"],
          "low_dose": "2.5 mg",
          "side_effects": ["pedal edema (10% at 10mg)", "headache", "flushing"],
          "contraindications": ["cardiogenic shock", "severe aortic stenosis"],
          "pregnancy_category": "C"
        },
        {
          "drug_class": "ACE inhibitor",
          "representative": "enalapril",
          "initial_dose": "5 mg OD-BD",
          "max_dose": "20 mg/day",
          "low_dose_situations": ["elderly >65", "on diuretics"],
          "low_dose": "2.5 mg",
          "side_effects": ["dry cough", "angioedema (rare)", "hyperkalemia"],
          "contraindications": ["pregnancy", "bilateral renal artery stenosis", "hyperkalemia"],
          "pregnancy_category": "D",
          "monitoring": "creatinine, potassium in renal impairment"
        },
        {
          "drug_class": "thiazide",
          "representative": "hydrochlorothiazide",
          "initial_dose": "12.5 mg OD",
          "max_dose": "25 mg OD",
          "side_effects": ["hypokalemia", "hyponatremia", "hyperglycemia", "hyperuricemia"],
          "contraindications": ["severe hypokalemia", "gout"],
          "special_notes": "Avoid in eGFR <30 (use loop diuretic instead)"
        }
      ],

      "step_wise_management": {
        "description": "Escalation protocol for BP control",
        "steps": [
          {
            "step": 1,
            "description": "Single drug therapy",
            "options": ["amlodipine 5mg", "enalapril 5mg", "HCTZ 12.5mg"],
            "duration_before_escalation": "2-4 weeks",
            "applies_to": ["Grade 1 HT", "Grade 2 HT"]
          },
          {
            "step": 2,
            "description": "Two drug combination",
            "options": ["CCB + ACE-I", "CCB + thiazide", "ACE-I + thiazide"],
            "avoid_combinations": ["ACE-I + ARB"],
            "applies_to": ["Grade 3 HT initial", "Step 1 failure"]
          },
          {
            "step": 3,
            "description": "Three drug combination",
            "recommended": "CCB + ACE-I + thiazide",
            "applies_to": ["Step 2 failure"]
          },
          {
            "step": 4,
            "description": "Resistant hypertension",
            "action": "refer_specialist",
            "applies_to": ["Step 3 failure"]
          }
        ]
      },

      "emergency_protocols": {
        "hypertensive_emergency": {
          "definition": "BP >180/110-120 with acute organ damage",
          "target": "Reduce MAP by ≤25% in first hour, then gradually to 160/110 over 2-6 hours",
          "drugs": [
            {"drug": "IV labetalol", "dose": "20-80mg IV", "onset": "5-10 min"},
            {"drug": "IV nicardipine", "dose": "5-15 mg/hr", "onset": "5-10 min"},
            {"drug": "IV nitroglycerine", "dose": "5-100 µg/min", "indication": "MI with hypertension"}
          ],
          "avoid": "sublingual nifedipine (unpredictable BP drop)"
        },
        "hypertensive_urgency": {
          "definition": "BP >180/110 WITHOUT acute organ damage",
          "management": "Gradual reduction over hours to days with oral drugs",
          "drugs": ["oral frusemide", "oral clonidine", "restart/intensify regular therapy"],
          "avoid": "Aggressive IV reduction"
        },
        "stroke_specific": {
          "ischemic_stroke": {
            "first_72_hours": "Do NOT lower BP unless >220/120 (or >185/110 if thrombolysis candidate)",
            "target": "Reduce by 15% in first hour, max 25% in 24 hours"
          },
          "hemorrhagic_stroke": {
            "sbp_150_220": "Can lower to SBP 140 safely",
            "sbp_gt_180": "Reduce to 160/90 with IV infusion"
          }
        }
      },

      "follow_up": {
        "frequency": {
          "uncontrolled": "every 1-2 weeks until target achieved",
          "controlled": "physician visit every 3-6 months",
          "stable": "annual comprehensive review"
        },
        "annual_review_components": [
          "BP control assessment",
          "lifestyle modification adherence",
          "target organ damage screening (proteinuria)",
          "medication side effects",
          "cardiovascular risk reassessment"
        ],
        "quality_metrics": [
          "percentage achieving target BP",
          "medication adherence rate",
          "complication rate (stroke, MI, CKD progression)"
        ]
      },

      "patient_education": {
        "key_messages": [
          "Hypertension is usually asymptomatic but causes serious complications",
          "Lifelong therapy required in most cases",
          "Lifestyle changes are essential even with medication",
          "Regular monitoring crucial for prevention"
        ],
        "self_monitoring": {
          "encouraged": true,
          "device": "validated automated BP device",
          "frequency": "as advised by physician"
        }
      }
    }
  ]
}
```

---

## Schema for Visual Workflow STGs (ENT Format)

```json
{
  "document_meta": {
    "source": "ICMR STW",
    "specialty": "ent",
    "document_type": "visual_workflow",
    "version": "October 2019"
  },

  "conditions": [
    {
      "condition_id": "ent_rhinosinusitis_001",
      "name": "Acute Rhinosinusitis",
      "icd_codes": ["J01.90"],

      "when_to_suspect": {
        "description": "Usually sequela of viral URTI causing ciliary impairment and bacterial superinfection",
        "diagnostic_criteria": "Persistence of nasal blockage/discharge and facial pain/hyposmia beyond 7 days (max 3 months)",
        "exclusion": "Symptoms <7 days = viral URTI"
      },

      "related_scenarios": [
        {
          "scenario": "Recurrent acute sinusitis",
          "definition": "Episodes interspersed with symptom-free intervals >3 months"
        },
        {
          "scenario": "Invasive fungal sinusitis",
          "additional_features": ["facial hypoesthesia", "facial/palatal/turbinate discoloration", "proptosis", "diplopia", "vision loss"],
          "urgency": "emergency"
        }
      ],

      "alternative_diagnoses": {
        "suspect_if": ["unilateral symptoms", "bleeding", "crusting", "cacosmia (foul smell)"],
        "contributory_factors": ["allergy", "dental caries", "DNS", "LPR", "smoking"]
      },

      "triage_metadata": {
        "red_flags_for_referral": [
          {"flag": "diabetic/immunocompromised", "action": "refer_district"},
          {"flag": "orbital involvement", "signs": ["periorbital edema", "displaced globe", "ophthalmoplegia", "visual disturbance"], "action": "refer_district_urgent"},
          {"flag": "meningitis/altered sensorium", "action": "refer_district_urgent"},
          {"flag": "frontal fullness", "action": "refer_district"},
          {"flag": "non-resolution with oral antibiotics x10 days", "action": "refer_district"},
          {"flag": "invasive fungal sinusitis features", "action": "refer_district_emergency"}
        ]
      },

      "clinical_examination": {
        "preliminary": [
          "anterior rhinoscopy: discharge, bleeding, crusting, polyposis",
          "oral exam: dental caries, post nasal drip, palatal discoloration",
          "assess contributory factors"
        ],
        "desirable": ["nasal endoscopy"]
      },

      "investigations": {
        "indication": "non-resolving/worsening despite antibiotics",
        "tests": [
          {"test": "endoscopy with guided nasal swabs/KOH smear", "purpose": "fungal diagnosis"},
          {"test": "CT PNS", "indication": "suspected complications or no response to 14 days antibiotics"},
          {"test": "diabetes/immunodeficiency screening", "indication": "suspected fungal sinusitis"}
        ]
      },

      "treatment_by_care_level": {
        "phc_primary": {
          "duration": "7-14 days",
          "medications": [
            {"drug": "amoxicillin/co-amoxiclav", "duration": "7-10 days", "first_line": true},
            {"drug": "levofloxacin/azithromycin", "indication": "penicillin intolerant"},
            {"drug": "budesonide/mometasone nasal spray", "dose": "OD-BD x 2 weeks", "benefit": "earlier symptom relief"},
            {"drug": "saline nasal wash", "benefit": "clears secretions, improves topical med effect"},
            {"drug": "oxymetazoline/pseudoephedrine", "duration": "3-5 days max", "benefit": "symptom relief"},
            {"drug": "antihistamines", "indication": "co-existing allergy"}
          ],
          "supportive": ["adequate hydration", "steam inhalation"]
        },
        "district_hospital": {
          "surgical_indications": [
            "underlying anatomical conditions (DNS, adenoid hypertrophy)",
            "anatomical variations on CT"
          ],
          "referrals": [
            {"to": "ophthalmology", "for": "suspected intraorbital complications"},
            {"to": "dental", "for": "suspected dental origin"}
          ],
          "fungal_sinusitis": {
            "management": ["start antifungals", "control immunocompromising comorbidity", "consider debridement"]
          }
        },
        "tertiary": {
          "indications": [
            "acute invasive fungal sinusitis",
            "complicated acute bacterial sinusitis",
            "immunocompromised patients"
          ]
        }
      },

      "parenteral_antibiotic_indications": [
        "orbital/intracranial complications",
        "non-resolution with ≥7 days oral antibiotics",
        "worsening symptoms on oral antibiotics"
      ]
    },

    {
      "condition_id": "ent_epistaxis_001",
      "name": "Epistaxis",
      "icd_codes": ["R04.0"],

      "clinical_scenarios": [
        {"scenario": "Post-trauma/barotrauma/nose picking/exertion", "urgency": "varies"},
        {"scenario": "Hypertensive/hematological disorders", "urgency": "urgent"},
        {"scenario": "No obvious cause", "urgency": "requires_investigation"}
      ],

      "clinical_pearls": [
        "In children: almost always anterior from Little's area, due to mucosal drying",
        "In adults: often posterior from inferior turbinate, related to hypertension",
        "Initial non-invasive methods suffice in majority"
      ],

      "triage_metadata": {
        "red_flags": [
          {"flag": "features of neoplasia", "signs": ["unilateral bleeding", "nasal obstruction", "visual/orbital symptoms", "mass lesion"]},
          {"flag": "persistent bleeding despite nasal packing", "action": "tertiary_referral"},
          {"flag": "altered blood counts/coagulation", "action": "hematology_workup"},
          {"flag": "recurrent profuse bleeding in teenage boys", "consider": "JNA", "action": "tertiary_referral"}
        ]
      },

      "clinical_examination": {
        "essential": [
          "anterior rhinoscopy/endoscopy for bleeding source",
          "check Little's area for bleeder/clot/congestion",
          "look for sharp septal spur",
          "assess for URTI (congested mucosa)",
          "general physical exam (CV/respiratory/neurological)"
        ],
        "systemic_assessment": "screen for coagulation disorders, anticoagulant medications, hematological malignancies"
      },

      "investigations": {
        "essential": ["hemoglobin", "coagulation profile", "CBC"],
        "desirable": {
          "test": "CT with contrast",
          "indication": "no obvious cause OR suspected benign/malignant lesion"
        }
      },

      "step_wise_management": {
        "steps": [
          {"step": 1, "action": "Ensure patent airway, avoid aspiration (head down/lateral positioning)"},
          {"step": 2, "action": "Restore hemodynamic stability (IV fluids/transfusion)"},
          {"step": 3, "action": "Control bleeding", "methods": [
            "bidigital compression x10 min in Trotter's position",
            "cotton pledgets with 4% xylocaine + adrenaline",
            "labetalol for uncontrolled hypertension",
            "chemical/electrocautery of Little's area bleeder"
          ]},
          {"step": 4, "action": "Tamponade with anterior nasal packing/epistaxis balloon"},
          {"step": 5, "action": "Posterior nasal packing if anterior fails"},
          {"step": 6, "action": "Antibiotic prophylaxis + hospitalization after packing"},
          {"step": 7, "action": "H2 blockers/PPI if blood aspiration (prevent gastritis)"},
          {"step": 8, "action": "Arterial ligation if packing fails (sphenopalatine/anterior ethmoidal)"},
          {"step": 9, "action": "Selective embolization as surgery alternative"},
          {"step": 10, "action": "Address identified etiology"}
        ]
      },

      "follow_up": {
        "interventions": [
          "continued nasal lubrication x2 weeks (liquid paraffin)",
          "repeat anterior rhinoscopy/endoscopy to confirm cause",
          "oral hematinics if needed"
        ],
        "quality_metrics": [
          "recurrence of episodes",
          "hemoglobin improvement over time"
        ]
      }
    }
  ]
}
```

---

## Chunking Strategy by Document Type

| Document Type | Chunking Approach | Chunk Size |
|---------------|-------------------|------------|
| **Narrative (Hypertension)** | By section + comorbidity pathway | 400-600 tokens |
| **Visual Workflow (Rhinosinusitis)** | Entire condition as 1-2 chunks | 300-400 tokens |
| **Step Protocol (Epistaxis)** | Steps as one chunk, red flags separate | 200-300 tokens |

### Recommended Chunk Types

```python
chunk_types = [
    "triage_criteria",      # Red flags, emergency triggers, thresholds
    "classification",       # Grades, staging
    "presentation",         # Symptoms, when to suspect
    "investigation",        # Labs, imaging
    "treatment_primary",    # PHC-level management
    "treatment_escalation", # District/tertiary options
    "drug_formulary",       # Dosing, contraindications
    "comorbidity_pathway",  # Condition-specific management
    "emergency_protocol",   # Urgency/emergency handling
    "follow_up",           # Monitoring, quality metrics
    "step_protocol"        # Ordered management steps
]
```

---

## Supabase Schema (Enhanced)

```sql
CREATE TABLE clinical_chunks_v2 (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Condition identifiers
  condition_id TEXT NOT NULL,
  condition_name TEXT NOT NULL,
  icd_codes TEXT[],
  
  -- Document metadata
  specialty TEXT NOT NULL,
  document_type TEXT NOT NULL, -- 'narrative', 'visual_workflow', 'step_protocol'
  section_type TEXT NOT NULL,
  
  -- Content
  content JSONB NOT NULL,
  content_text TEXT NOT NULL, -- Flattened for embedding
  embedding VECTOR(768),
  
  -- Triage-critical filters
  urgency_default TEXT,
  has_emergency_triggers BOOLEAN DEFAULT FALSE,
  has_red_flags BOOLEAN DEFAULT FALSE,
  care_level TEXT[], -- ['phc', 'district', 'tertiary']
  
  -- Comorbidity pathway (if applicable)
  comorbidity TEXT, -- 'diabetes', 'ckd', 'heart_failure', NULL
  
  -- Numeric thresholds (for quantitative triage)
  numeric_thresholds JSONB, -- {"sbp_min": 180, "dbp_min": 110}
  
  -- Source tracking
  source_document TEXT,
  page_numbers INT[],
  
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for hybrid retrieval
CREATE INDEX ON clinical_chunks_v2 USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON clinical_chunks_v2 (specialty, section_type);
CREATE INDEX ON clinical_chunks_v2 (comorbidity) WHERE comorbidity IS NOT NULL;
CREATE INDEX ON clinical_chunks_v2 USING GIN (care_level);
CREATE INDEX ON clinical_chunks_v2 USING GIN (icd_codes);
```

---

## Key Enhancements Summary

| Gap | Solution |
|-----|----------|
| Numeric BP thresholds | `classification.grades[].criteria` with ranges |
| Step-wise protocols | `step_wise_management.steps[]` ordered array |
| 3-tier care levels | `treatment_by_care_level.phc_primary/district/tertiary` |
| Comorbidity pathways | `comorbidity_pathways[]` with drug preferences |
| Drug formulary | `drug_formulary[]` with dosing, contraindications |
| ICD codes | Top-level `icd_codes[]` array |
| Quality metrics | `follow_up.quality_metrics[]` |
| Emergency protocols | Dedicated `emergency_protocols{}` section |
| Visual workflow support | `when_to_suspect`, `related_scenarios`, `clinical_pearls` |
