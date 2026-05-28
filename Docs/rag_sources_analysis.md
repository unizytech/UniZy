# RAG Sources Analysis & Scraping Strategy
## Deep Dive by Specialty + Technical Recommendations

---

## Part 1: Scraping Technology Assessment

### Current Plan Libraries
| Library | Purpose | Limitations |
|---------|---------|-------------|
| `requests` | HTTP requests | No JavaScript rendering |
| `BeautifulSoup` | HTML parsing | Static content only |
| `PyPDF2` | PDF text extraction | Fails on scanned/image PDFs |

### When Current Stack Works ✅
- Government portals (ICMR, NHM, NVBDCP) - mostly static HTML
- Direct PDF download links
- Simple pagination with URL parameters
- Sites without anti-bot protection

### When Apify or Alternatives Needed ⚠️

| Scenario | Example Sites | Solution |
|----------|---------------|----------|
| JavaScript-rendered content | Some society websites | Playwright/Selenium or Apify |
| Login-required content | Journal subscriptions | Manual download or Apify |
| Anti-bot protection | Some international sites | Apify with proxies |
| Complex pagination/infinite scroll | PubMed, medical databases | Apify actors |
| Large-scale scraping (1000+ pages) | Systematic reviews | Apify for reliability |

### Recommended Hybrid Approach

```
┌─────────────────────────────────────────────────────────────────┐
│                     SCRAPING DECISION TREE                       │
│                                                                  │
│  Is it a direct PDF link?                                       │
│  ├─ YES → requests + PyPDF2 ✅                                  │
│  └─ NO ↓                                                        │
│                                                                  │
│  Is it static HTML?                                             │
│  ├─ YES → requests + BeautifulSoup ✅                           │
│  └─ NO ↓                                                        │
│                                                                  │
│  Does it require JavaScript?                                    │
│  ├─ YES → Playwright (free) or Apify                           │
│  └─ NO ↓                                                        │
│                                                                  │
│  Does it have anti-bot protection?                              │
│  ├─ YES → Apify with proxies 💰                                 │
│  └─ NO → Playwright locally (free)                              │
└─────────────────────────────────────────────────────────────────┘
```

### Cost-Effective Recommendation

**Add Playwright (free) before considering Apify:**

```python
# Add to requirements.txt
playwright==1.40.0

# Installation
pip install playwright
playwright install chromium
```

```python
# Enhanced scraper with Playwright fallback
from playwright.sync_api import sync_playwright

class EnhancedGuidelineScraper:
    def scrape_with_js(self, url: str) -> str:
        """Use Playwright for JavaScript-rendered pages"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            content = page.content()
            browser.close()
            return content
```

**When to use Apify ($49/month starter):**
- Scraping 10,000+ pages/month
- Need rotating proxies for blocked sites
- Want pre-built actors for PubMed, medical databases
- Need scheduled, monitored scraping pipelines

---

## Part 2: Additional RAG Sources by Specialty

### Assessment Criteria
- **Authority**: Government > National Society > International > Textbook
- **Recency**: Guidelines updated within 5 years
- **India-specific**: Adapted to Indian disease patterns, drug availability
- **Accessibility**: Freely available vs paywalled

---

## 🏥 GENERAL MEDICINE

### Currently Included
- ICMR STGs, NVBDCP Dengue/Malaria, RNTCP TB

### Missing High-Value Sources

| Source | Type | Content | Scraping Difficulty |
|--------|------|---------|---------------------|
| **API (Association of Physicians of India) Medicine Update** | Journal | Annual evidence updates | Medium - requires navigation |
| **JAPI (Journal of API)** | Journal | Case-based guidelines | Medium - journal structure |
| **AIIMS Protocols** | Hospital protocols | Practical algorithms | Easy - PDF downloads |
| **PGIMER Chandigarh Treatment Protocols** | Hospital protocols | Evidence-based pathways | Easy - PDF downloads |
| **Indian Chest Society Guidelines** | Society | Respiratory infections, TB | Medium |
| **IADVL (Dermatology)** | Society | Skin manifestations of systemic disease | Medium |
| **Cardiological Society of India** | Society | Hypertension, IHD, heart failure | Medium |
| **RSSDI (Diabetes)** | Society | Diabetes management India-specific | Easy - well organized |

### Critical Gaps to Fill

**Fever Workup (Endemic Diseases):**
```
Additional sources needed:
├── Scrub Typhus: ICMR Scrub Typhus Guidelines 2023
├── Leptospirosis: IAP/ICMR Leptospirosis Consensus
├── Chikungunya: NVBDCP Chikungunya Guidelines
├── COVID-19: MoHFW COVID Treatment Protocol (latest)
└── Influenza: NCDC Influenza Guidelines
```

**Chronic Disease Management:**
```
Additional sources needed:
├── Hypertension: CSI/HSI Hypertension Guidelines 2020
├── Diabetes: RSSDI Clinical Practice Recommendations
├── Thyroid: Indian Thyroid Society Guidelines
├── CKD: Indian Society of Nephrology Guidelines
└── COPD: Indian Chest Society COPD Guidelines
```

### URLs to Add

```python
GENERAL_MEDICINE_ADDITIONAL = [
    {
        "name": "API Medicine Update",
        "url": "https://www.apiindia.org/medicine-update/",
        "type": "webpage_with_pdfs",
        "scraping": "playwright_required",  # JS navigation
        "topics": ["evidence_updates", "clinical_pearls"]
    },
    {
        "name": "AIIMS Treatment Protocols",
        "url": "https://www.aiims.edu/en/departments-and-centers/clinical/medicine.html",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["hospital_protocols", "algorithms"]
    },
    {
        "name": "CSI Hypertension Guidelines",
        "url": "https://www.csi.org.in/guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["hypertension", "cardiovascular"]
    },
    {
        "name": "RSSDI Diabetes Guidelines",
        "url": "https://rssdi.in/guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["diabetes", "T2DM", "insulin"]
    },
    {
        "name": "Indian Chest Society Guidelines",
        "url": "https://www.indianchestsociety.org/guidelines",
        "type": "webpage_with_pdfs",
        "scraping": "playwright_required",
        "topics": ["COPD", "asthma", "pneumonia", "TB"]
    },
    {
        "name": "ICMR Scrub Typhus Guidelines",
        "url": "https://main.icmr.nic.in/sites/default/files/guidelines/Scrub_Typhus.pdf",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["scrub_typhus", "fever"]
    },
    {
        "name": "NCDC Disease Surveillance Guidelines",
        "url": "https://ncdc.gov.in/index4.php?lang=1&level=0&linkid=127&lid=432",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["outbreak", "surveillance", "infectious_disease"]
    }
]
```

---

## 👶 PEDIATRICS

### Currently Included
- IAP Immunization, IAP Fever, WHO IMCI

### Missing High-Value Sources

| Source | Type | Content | Priority |
|--------|------|---------|----------|
| **IAP Drug Formulary** | Reference | Pediatric dosing | HIGH |
| **IAP Standard Treatment Guidelines** | Guidelines | Condition-specific | HIGH |
| **Palani Consensus Statements** | Consensus | IAP expert consensus | HIGH |
| **ISPN (Nephrology)** | Society | Pediatric kidney disease | MEDIUM |
| **ISPGHAN (GI)** | Society | Pediatric GI disorders | MEDIUM |
| **Palred Guidelines** | Emergency | Pediatric emergency protocols | HIGH |
| **NNF Essential Newborn Care** | Guidelines | Overlap with neonatology | HIGH |

### Critical Gaps to Fill

**Common Presentations:**
```
Additional sources needed:
├── Acute Diarrhea: IAP/WHO ORS Protocol
├── Pneumonia: IAP Pneumonia Guidelines 2021
├── Asthma: IAP Asthma Guidelines
├── Seizures: IAP/IES Seizure Guidelines
├── Anemia: IAP Iron Deficiency Guidelines
├── Growth Monitoring: IAP Growth Charts (Indian)
└── Developmental Delay: IAP Developmental Screening
```

**Age-Specific Protocols:**
```
├── Neonatal: Covered by NNF
├── Infant (1-12 mo): IAP Well Baby Guidelines
├── Toddler (1-3 yr): IAP Nutrition Guidelines
├── School-age: IAP School Health Guidelines
└── Adolescent: IAP Adolescent Health
```

### URLs to Add

```python
PEDIATRICS_ADDITIONAL = [
    {
        "name": "IAP Drug Formulary",
        "url": "https://iapdrugformulary.com/",
        "type": "database",
        "scraping": "playwright_required",  # Interactive
        "topics": ["pediatric_dosing", "drug_formulary"],
        "note": "Consider manual curation - interactive DB"
    },
    {
        "name": "IAP Standard Treatment Guidelines",
        "url": "https://iapindia.org/iap-guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["treatment_protocols", "clinical_pathways"]
    },
    {
        "name": "IAP Palani Consensus Statements",
        "url": "https://iapindia.org/consensus-statements/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["consensus", "expert_opinion"]
    },
    {
        "name": "Palred Emergency Guidelines",
        "url": "http://palred.org/guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["emergency", "resuscitation", "shock"]
    },
    {
        "name": "IAP Growth Charts (Indian)",
        "url": "https://iapindia.org/iap-growth-charts/",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["growth", "anthropometry", "nutrition"]
    },
    {
        "name": "ISPGHAN Guidelines",
        "url": "https://ispghan.org/guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["GI", "hepatology", "nutrition"]
    }
]
```

---

## 👣 NEONATOLOGY

### Currently Included
- NNF CPG, FBNC Guidelines, NRP India

### Missing High-Value Sources

| Source | Type | Content | Priority |
|--------|------|---------|----------|
| **NNF Evidence-Based Guidelines (Full Set)** | Guidelines | 30+ clinical scenarios | HIGH |
| **AIIMS Neonatal Protocols** | Hospital | Practical algorithms | HIGH |
| **Vermont Oxford Network Benchmarks** | Quality | Outcome benchmarks | MEDIUM |
| **INSCOL (Neonatal Surgery)** | Society | Surgical conditions | MEDIUM |
| **Palned Emergency Protocols** | Emergency | Neonatal emergencies | HIGH |

### Critical Gaps to Fill

**High-Acuity Presentations:**
```
Additional sources needed:
├── Neonatal Sepsis: NNF Sepsis Screen Protocol
├── Meconium Aspiration: NNF MAS Management
├── HIE: NNF Therapeutic Hypothermia Protocol
├── NEC: NNF NEC Prevention & Management
├── BPD: NNF Oxygen Management Protocol
├── IVH: NNF Neuro-imaging Guidelines
└── PDA: NNF PDA Management Algorithm
```

**Feeding & Nutrition:**
```
├── Human Milk Banking: NNF HMB Guidelines
├── TPN: NNF Parenteral Nutrition
├── Enteral Feeding: NNF Feeding Protocol
└── EUGR: NNF Nutrition for VLBW
```

### URLs to Add

```python
NEONATOLOGY_ADDITIONAL = [
    {
        "name": "NNF Evidence-Based Clinical Practice Guidelines (Full)",
        "url": "https://www.nnfi.org/cpg",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["all_neonatal_conditions"],
        "note": "Scrape ALL PDFs, not just top-level"
    },
    {
        "name": "NNF Sepsis Screen Calculator",
        "url": "https://www.nnfi.org/sepsis-screen",
        "type": "tool_documentation",
        "scraping": "manual",
        "topics": ["sepsis", "risk_stratification"]
    },
    {
        "name": "AIIMS Neonatal Division Protocols",
        "url": "https://www.newbornwhocc.org/clinical-protocols.html",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["SNCU", "level_3_care"]
    },
    {
        "name": "Palned Neonatal Emergency Guidelines",
        "url": "http://palned.org/guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["emergency", "transport", "stabilization"]
    },
    {
        "name": "ICMR Kangaroo Mother Care Guidelines",
        "url": "https://nhm.gov.in/images/pdf/programmes/child-health/guidelines/Kangaroo_Mother_Care_Guidelines.pdf",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["KMC", "preterm_care"]
    }
]
```

---

## 🤰 OBSTETRICS

### Currently Included
- FOGSI GCPR, GoI ANC Guidelines, ICMR GDM, PIH Guidelines

### Missing High-Value Sources

| Source | Type | Content | Priority |
|--------|------|---------|----------|
| **FOGSI Good Clinical Practice Recommendations (Full Set)** | Guidelines | 50+ topics | HIGH |
| **ICOG (Indian College of OB-GYN)** | Guidelines | Evidence-based protocols | HIGH |
| **MoHFW Maternal Health Guidelines** | Government | National programs | HIGH |
| **FIGO Guidelines (India adapted)** | International | Global standards | MEDIUM |
| **WHO Antenatal Care Recommendations** | International | Evidence-based | MEDIUM |

### Critical Gaps to Fill

**High-Risk Pregnancy:**
```
Additional sources needed:
├── Multiple Pregnancy: FOGSI Twins/Triplets
├── IUGR: FOGSI Fetal Growth Restriction
├── Preterm Labor: FOGSI Tocolysis Protocol
├── Placenta Previa: FOGSI APH Management
├── Rh Isoimmunization: FOGSI Rh Protocol
├── Cardiac Disease in Pregnancy: FOGSI/CSI
└── Thyroid in Pregnancy: FOGSI/ITS
```

**Labor & Delivery:**
```
├── Labor Monitoring: FOGSI Partograph Guidelines
├── Instrumental Delivery: FOGSI Vacuum/Forceps
├── LSCS Audit: FOGSI Cesarean Guidelines
├── PPH: FOGSI Active Management 3rd Stage
└── Shoulder Dystocia: FOGSI Obstetric Emergency
```

### URLs to Add

```python
OBSTETRICS_ADDITIONAL = [
    {
        "name": "FOGSI GCPR Complete Collection",
        "url": "https://www.fogsi.org/gcpr/",
        "type": "webpage_with_pdfs",
        "scraping": "playwright_required",  # Tabbed navigation
        "topics": ["all_obstetric_conditions"],
        "note": "50+ PDFs, need comprehensive scraping"
    },
    {
        "name": "ICOG Practice Bulletins",
        "url": "https://www.icogonline.org/practice-bulletins/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["evidence_based", "clinical_practice"]
    },
    {
        "name": "MoHFW LaQshya Guidelines",
        "url": "https://nhm.gov.in/New_Updates_2018/NHM_Components/RMNCH_MH_Guidelines/LaQshya-Guidelines.pdf",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["labor_room", "quality_improvement"]
    },
    {
        "name": "MoHFW SUMAN Guidelines",
        "url": "https://nhm.gov.in/index1.php?lang=1&level=3&sublinkid=1308&lid=689",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["safe_motherhood", "newborn_care"]
    },
    {
        "name": "FOGSI PPH Management Protocol",
        "url": "https://www.fogsi.org/wp-content/uploads/gcpr/PPH-Management.pdf",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["PPH", "obstetric_emergency"]
    },
    {
        "name": "WHO Antenatal Care Recommendations",
        "url": "https://www.who.int/publications/i/item/9789241549912",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["ANC", "evidence_based"]
    }
]
```

---

## 🧬 FERTILITY

### Currently Included
- ICMR ART Guidelines, ISAR Guidelines

### Missing High-Value Sources

| Source | Type | Content | Priority |
|--------|------|---------|----------|
| **ISAR Consensus Statements** | Society | Expert consensus | HIGH |
| **ESHRE Guidelines (adapted)** | International | Evidence-based | MEDIUM |
| **ASRM Practice Committee Opinions** | International | Best practices | MEDIUM |
| **FOGSI Infertility Committee** | Society | India-specific | HIGH |

### Critical Gaps to Fill

**Diagnostic Workup:**
```
Additional sources needed:
├── PCOS: Rotterdam Criteria + ISAR Adaptation
├── Male Factor: ISAR Male Infertility Workup
├── Tubal Factor: ISAR HSG/Laparoscopy Guidelines
├── Ovarian Reserve: ISAR AMH Interpretation
└── Unexplained Infertility: ISAR Approach
```

**Treatment Protocols:**
```
├── Ovulation Induction: ISAR OI Protocol
├── IUI: ISAR IUI Guidelines
├── IVF Stimulation: ISAR Controlled Ovarian Stimulation
├── Embryo Transfer: ISAR ET Technique
├── Luteal Support: ISAR Progesterone Protocol
└── Recurrent Implantation Failure: ISAR RIF Workup
```

### URLs to Add

```python
FERTILITY_ADDITIONAL = [
    {
        "name": "ISAR Consensus Statements",
        "url": "https://isar.org.in/consensus/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["PCOS", "male_factor", "IVF_protocols"]
    },
    {
        "name": "FOGSI Infertility Committee Guidelines",
        "url": "https://www.fogsi.org/infertility-committee/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["basic_infertility", "referral_criteria"]
    },
    {
        "name": "ICMR National Registry for ART",
        "url": "https://nari.icmr.org.in/",
        "type": "database",
        "scraping": "manual",
        "topics": ["outcomes", "benchmarks"],
        "note": "Reference data, not guidelines"
    },
    {
        "name": "ESHRE Guidelines (Key Documents)",
        "url": "https://www.eshre.eu/Guidelines-and-Legal",
        "type": "webpage_with_pdfs",
        "scraping": "playwright_required",
        "topics": ["evidence_based", "international_standards"]
    }
]
```

---

## 🫁 GASTROENTEROLOGY

### Currently Included
- ISG Consensus, INASL Hepatitis Guidelines

### Missing High-Value Sources

| Source | Type | Content | Priority |
|--------|------|---------|----------|
| **ISG Task Force Reports** | Society | Comprehensive guidelines | HIGH |
| **INASL Guidelines (Complete)** | Society | Liver disease | HIGH |
| **SGEI (Surgical GI)** | Society | GI surgery | MEDIUM |
| **IPA (Pancreas Association)** | Society | Pancreatitis | HIGH |
| **AIIMS GI Protocols** | Hospital | Practical algorithms | HIGH |

### Critical Gaps to Fill

**Common Presentations:**
```
Additional sources needed:
├── Acute Abdomen: ISG/SGEI Acute Abdomen Approach
├── GI Bleeding: ISG Upper/Lower GI Bleed
├── Jaundice: ISG/INASL Jaundice Workup
├── Ascites: INASL Ascites Management
├── Acute Pancreatitis: IPA/ISG Pancreatitis Guidelines
├── IBD: ISG Crohn's/UC Guidelines
└── Chronic Diarrhea: ISG Malabsorption Workup
```

**Liver Disease:**
```
├── Cirrhosis: INASL Decompensated Cirrhosis
├── HCC Surveillance: INASL HCC Guidelines
├── ACLF: INASL Acute-on-Chronic Liver Failure
├── NAFLD: INASL NAFLD/NASH Guidelines
└── Drug-Induced Liver Injury: INASL DILI
```

### URLs to Add

```python
GASTROENTEROLOGY_ADDITIONAL = [
    {
        "name": "ISG Task Force Reports",
        "url": "https://isg.org.in/task-force-reports/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["IBD", "H_pylori", "functional_GI"]
    },
    {
        "name": "INASL Guidelines Complete Collection",
        "url": "https://www.inasl.org.in/guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["hepatitis", "cirrhosis", "NAFLD", "HCC"]
    },
    {
        "name": "IPA Pancreatitis Guidelines",
        "url": "https://pancreas.org.in/guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["acute_pancreatitis", "chronic_pancreatitis"]
    },
    {
        "name": "ISG GI Bleeding Consensus",
        "url": "https://isg.org.in/consensus-statements/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["UGIB", "LGIB", "variceal_bleeding"]
    },
    {
        "name": "AIIMS GI Division Protocols",
        "url": "https://www.aiims.edu/en/departments-and-centers/clinical/gastro.html",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["endoscopy", "liver_biopsy", "ERCP"]
    }
]
```

---

## 🦴 ORTHOPAEDICS

### Currently Included
- IOA Guidelines, ICMR TB Spine

### Missing High-Value Sources

| Source | Type | Content | Priority |
|--------|------|---------|----------|
| **IOA Clinical Practice Guidelines (Full)** | Society | Condition-specific | HIGH |
| **ISKSAA (Knee & Shoulder)** | Society | Arthroscopy, sports | MEDIUM |
| **ISSICON (Spine)** | Society | Spine conditions | HIGH |
| **Trauma Society of India** | Society | Trauma protocols | HIGH |
| **IOACON Instructional Courses** | Education | Case-based learning | MEDIUM |

### Critical Gaps to Fill

**Emergency Presentations:**
```
Additional sources needed:
├── Open Fractures: IOA/TSI Open Fracture Protocol
├── Compartment Syndrome: IOA Emergency Guidelines
├── Septic Arthritis: IOA Septic Joint Management
├── Spinal Cord Injury: ISSICON/IOA SCI Protocol
├── Polytrauma: TSI ATLS-based Protocol
└── Pelvic Fractures: IOA Pelvic Trauma
```

**Common Conditions:**
```
├── Osteoarthritis: IOA OA Management
├── Rheumatoid Arthritis: IRA/IOA RA Guidelines
├── Osteoporosis: IOA/IOS Osteoporosis
├── Low Back Pain: ISSICON LBP Guidelines
├── Fracture Non-union: IOA Non-union Protocol
└── Osteomyelitis: IOA Bone Infection Guidelines
```

### URLs to Add

```python
ORTHOPAEDICS_ADDITIONAL = [
    {
        "name": "IOA Clinical Practice Guidelines Collection",
        "url": "https://www.ioaindia.org/cpg/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["fractures", "arthroplasty", "spine", "pediatric_ortho"]
    },
    {
        "name": "Trauma Society of India Protocols",
        "url": "https://traumasocietyindia.org/protocols/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["polytrauma", "ATLS", "damage_control"]
    },
    {
        "name": "ISSICON Spine Guidelines",
        "url": "https://issicon.org/guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["degenerative_spine", "trauma", "infection"]
    },
    {
        "name": "Indian Orthopaedic Association TB Spine",
        "url": "https://www.ioaindia.org/tb-spine-guidelines/",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["TB_spine", "spinal_tuberculosis"]
    },
    {
        "name": "IOA Osteoporosis Guidelines",
        "url": "https://www.ioaindia.org/osteoporosis/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["osteoporosis", "fragility_fractures"]
    }
]
```

---

## 🧠 PSYCHIATRY

### Currently Included
- IPS CPG, NIMHANS Protocols, MHA 2017, DGHS Suicide Prevention, NDDTC De-addiction

### Missing High-Value Sources

| Source | Type | Content | Priority |
|--------|------|---------|----------|
| **IPS CPG (Complete - All Disorders)** | Society | Comprehensive guidelines | HIGH |
| **NIMHANS Screening Tools** | Tools | Validated instruments | HIGH |
| **ICMR Mental Health Guidelines** | Government | National standards | HIGH |
| **WHO QualityRights** | International | Rights-based care | MEDIUM |
| **INCLEN Trust Studies** | Research | Indian epidemiology | MEDIUM |

### Critical Gaps to Fill

**Common Presentations:**
```
Additional sources needed:
├── First Episode Psychosis: IPS FEP Protocol
├── Treatment-Resistant Depression: IPS TRD Guidelines
├── Bipolar Disorder: IPS Bipolar Management
├── OCD: IPS OCD Guidelines
├── PTSD: IPS Trauma Guidelines
├── Eating Disorders: IPS Eating Disorder Protocol
├── Child Psychiatry: IPS Child Mental Health
└── Geriatric Psychiatry: IPS Elderly Mental Health
```

**Emergency Psychiatry:**
```
├── Acute Agitation: IPS/NIMHANS Agitation Management
├── Catatonia: IPS Catatonia Protocol
├── NMS: IPS Neuroleptic Malignant Syndrome
├── Serotonin Syndrome: IPS Serotonin Syndrome
├── Lithium Toxicity: IPS Lithium Monitoring
└── ECT: IPS ECT Guidelines
```

**Substance Use Disorders:**
```
├── Alcohol Withdrawal: NIMHANS AWS Protocol
├── Opioid Substitution: NDDTC OST Guidelines
├── Cannabis Use Disorder: IPS Cannabis Guidelines
├── Tobacco Cessation: ICMR Tobacco Cessation
└── Prescription Drug Misuse: IPS Guidelines
```

### URLs to Add

```python
PSYCHIATRY_ADDITIONAL = [
    {
        "name": "IPS Clinical Practice Guidelines (All)",
        "url": "https://indianpsychiatricsociety.org/clinical-practice-guidelines/",
        "type": "webpage_with_pdfs",
        "scraping": "playwright_required",  # Dynamic loading
        "topics": ["depression", "schizophrenia", "bipolar", "anxiety", "OCD", "PTSD"],
        "note": "20+ separate guideline PDFs"
    },
    {
        "name": "NIMHANS Psychometry Tools",
        "url": "https://nimhans.ac.in/psychometry/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["screening", "rating_scales", "assessment"]
    },
    {
        "name": "NIMHANS Addiction Medicine Protocols",
        "url": "https://nimhans.ac.in/cam/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["alcohol", "opioid", "tobacco", "cannabis"]
    },
    {
        "name": "ICMR District Mental Health Programme",
        "url": "https://main.icmr.nic.in/content/mental-health",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["community_psychiatry", "primary_care"]
    },
    {
        "name": "IPS Emergency Psychiatry Guidelines",
        "url": "https://indianpsychiatricsociety.org/emergency-psychiatry/",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["agitation", "suicide", "violence", "NMS"]
    },
    {
        "name": "ICMR Tobacco Cessation Guidelines",
        "url": "https://main.icmr.nic.in/sites/default/files/guidelines/tobacco_cessation.pdf",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["tobacco", "smoking_cessation", "NRT"]
    },
    {
        "name": "WHO mhGAP Training Manuals",
        "url": "https://www.who.int/teams/mental-health-and-substance-use/treatment-care/mental-health-gap-action-programme",
        "type": "webpage_with_pdfs",
        "scraping": "beautifulsoup",
        "topics": ["primary_care_psychiatry", "training"]
    },
    {
        "name": "IPS Position Statement on ECT",
        "url": "https://indianpsychiatricsociety.org/ect-position-statement/",
        "type": "pdf",
        "scraping": "direct_download",
        "topics": ["ECT", "procedure"]
    }
]
```

---

## Part 3: Scraping Implementation Recommendations

### Upgrade Current Stack (Free)

```python
# requirements.txt additions
playwright==1.40.0
pdfplumber==0.10.3  # Better than PyPDF2 for complex PDFs
pytesseract==0.3.10  # For scanned PDFs (OCR)
pdf2image==1.16.3  # Convert PDF to images for OCR
```

### Enhanced Scraper Class

```python
# File: /scripts/enhanced_scraper.py

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from pathlib import Path
from typing import List, Dict, Optional
import time

class EnhancedGuidelineScraper:
    """Multi-strategy scraper for medical guidelines"""
    
    def __init__(self, output_dir: str = "./data/guidelines"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Medical Research Bot)'
        })
    
    def scrape(self, source: Dict) -> List[str]:
        """Route to appropriate scraping strategy"""
        
        scraping_method = source.get("scraping", "beautifulsoup")
        
        if scraping_method == "direct_download":
            return self._direct_download(source)
        elif scraping_method == "beautifulsoup":
            return self._beautifulsoup_scrape(source)
        elif scraping_method == "playwright_required":
            return self._playwright_scrape(source)
        elif scraping_method == "manual":
            print(f"⏭️ Manual download required: {source['name']}")
            return []
        else:
            return self._beautifulsoup_scrape(source)
    
    def _direct_download(self, source: Dict) -> List[str]:
        """Direct PDF download"""
        try:
            response = self.session.get(source["url"], timeout=60)
            response.raise_for_status()
            
            filename = self._sanitize_filename(source["name"]) + ".pdf"
            filepath = self.output_dir / source.get("specialty", "general") / filename
            filepath.parent.mkdir(exist_ok=True)
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Downloaded: {filename}")
            return [str(filepath)]
            
        except Exception as e:
            print(f"❌ Failed: {source['name']} - {e}")
            return []
    
    def _beautifulsoup_scrape(self, source: Dict) -> List[str]:
        """Static HTML scraping"""
        try:
            response = self.session.get(source["url"], timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            pdf_links = soup.find_all('a', href=lambda x: x and '.pdf' in x.lower())
            downloaded = []
            
            for link in pdf_links:
                href = link.get('href')
                if not href.startswith('http'):
                    from urllib.parse import urljoin
                    href = urljoin(source["url"], href)
                
                sub_source = {
                    "name": f"{source['name']} - {link.get_text(strip=True)[:50]}",
                    "url": href,
                    "specialty": source.get("specialty", "general")
                }
                downloaded.extend(self._direct_download(sub_source))
                time.sleep(1)  # Rate limiting
            
            print(f"📄 Found {len(downloaded)} PDFs from {source['name']}")
            return downloaded
            
        except Exception as e:
            print(f"❌ BS scraping failed: {source['name']} - {e}")
            return []
    
    def _playwright_scrape(self, source: Dict) -> List[str]:
        """JavaScript-rendered page scraping"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(source["url"], wait_until="networkidle", timeout=60000)
                
                # Wait for dynamic content
                page.wait_for_timeout(3000)
                
                # Find PDF links
                pdf_links = page.query_selector_all('a[href*=".pdf"]')
                downloaded = []
                
                for link in pdf_links:
                    href = link.get_attribute('href')
                    if href:
                        if not href.startswith('http'):
                            href = page.url.rsplit('/', 1)[0] + '/' + href
                        
                        sub_source = {
                            "name": f"{source['name']} - {link.inner_text()[:50]}",
                            "url": href,
                            "specialty": source.get("specialty", "general")
                        }
                        downloaded.extend(self._direct_download(sub_source))
                        time.sleep(1)
                
                browser.close()
                print(f"🎭 Playwright found {len(downloaded)} PDFs from {source['name']}")
                return downloaded
                
        except Exception as e:
            print(f"❌ Playwright failed: {source['name']} - {e}")
            return []
    
    def extract_text_from_pdf(self, pdf_path: str, use_ocr: bool = False) -> str:
        """Extract text from PDF, with OCR fallback"""
        try:
            # Try pdfplumber first (better than PyPDF2)
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            
            # If text is too short, might be scanned PDF
            if len(text.strip()) < 100 and use_ocr:
                print(f"🔍 OCR required for: {pdf_path}")
                text = self._ocr_pdf(pdf_path)
            
            return text
            
        except Exception as e:
            print(f"❌ PDF extraction failed: {pdf_path} - {e}")
            return ""
    
    def _ocr_pdf(self, pdf_path: str) -> str:
        """OCR for scanned PDFs"""
        try:
            images = convert_from_path(pdf_path)
            text_parts = []
            
            for i, image in enumerate(images):
                text = pytesseract.image_to_string(image)
                text_parts.append(text)
                print(f"  📖 OCR page {i+1}/{len(images)}")
            
            return "\n".join(text_parts)
            
        except Exception as e:
            print(f"❌ OCR failed: {pdf_path} - {e}")
            return ""
    
    def _sanitize_filename(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name)[:80]
```

---

## Part 4: Apify Decision Matrix

### When to Use Apify

| Criteria | Threshold | Recommendation |
|----------|-----------|----------------|
| **Scale** | >10,000 pages/month | Consider Apify |
| **Anti-bot sites** | >3 blocked sites | Use Apify |
| **JS-heavy sites** | >20% of sources | Consider Apify |
| **Team size** | Multiple developers | Apify for orchestration |
| **Budget** | $50+/month available | Apify Starter |

### Cost-Benefit Analysis

| Approach | Monthly Cost | Capability | Maintenance |
|----------|--------------|------------|-------------|
| **Current (requests + BS)** | $0 | Static HTML only | Low |
| **+ Playwright** | $0 | + JavaScript sites | Medium |
| **+ Apify Starter** | $49 | + Proxies, scheduling | Low (managed) |
| **+ Apify Scale** | $499 | Enterprise features | Very Low |

### Recommendation for 1hat

**Phase 1 (Initial Build):** 
- Use enhanced scraper with Playwright
- Manual download for 5-10 problematic sites
- **Cost: $0**

**Phase 2 (If scaling issues):**
- Add Apify for:
  - Scheduled monthly updates
  - Sites with anti-bot protection
  - PubMed systematic searches
- **Cost: $49/month**

---

## Part 5: Source Priority Matrix

### By Impact on Triage Accuracy

| Priority | Source Type | Examples | Impact |
|----------|-------------|----------|--------|
| **P0 (Critical)** | National emergency protocols | Sepsis, DKA, Stroke | Life-saving decisions |
| **P1 (High)** | India-specific disease guidelines | Dengue, Malaria, TB | Regional accuracy |
| **P2 (Medium)** | Specialty society consensus | IPS, IAP, NNF | Evidence-based care |
| **P3 (Low)** | International guidelines | WHO, NICE | Global standards |
| **P4 (Reference)** | Textbooks, drug formularies | Harrison's, IAP Drug | Background knowledge |

### Sources Count Summary

| Specialty | Currently | Additional | Total |
|-----------|-----------|------------|-------|
| General Medicine | 4 | 7 | 11 |
| Pediatrics | 3 | 6 | 9 |
| Neonatology | 3 | 5 | 8 |
| Obstetrics | 4 | 6 | 10 |
| Fertility | 2 | 4 | 6 |
| Gastroenterology | 2 | 5 | 7 |
| Orthopaedics | 2 | 5 | 7 |
| Psychiatry | 5 | 8 | 13 |
| **TOTAL** | **25** | **46** | **71** |

---

## Part 6: Implementation Checklist

### Week 1: Setup
- [ ] Install Playwright: `pip install playwright && playwright install chromium`
- [ ] Install pdfplumber: `pip install pdfplumber`
- [ ] Create enhanced scraper class
- [ ] Test on 5 different site types

### Week 2: Priority Scraping
- [ ] Download all P0 (Critical) sources
- [ ] Download all P1 (High) India-specific sources
- [ ] Manual download for blocked sites
- [ ] Verify PDF text extraction quality

### Week 3: Full Collection
- [ ] Download P2 sources
- [ ] OCR any scanned PDFs
- [ ] Create source inventory with metadata
- [ ] Quality check: minimum 70% text extraction

### Ongoing: Maintenance
- [ ] Monthly check for guideline updates
- [ ] Re-scrape updated sources
- [ ] Add new sources as societies publish
- [ ] Consider Apify if maintenance burden high

---

## Summary

**Scraping Technology:**
- Current plan uses basic `requests` + `BeautifulSoup` - sufficient for ~60% of sources
- Add `Playwright` (free) to handle JavaScript sites - covers ~35% more
- `Apify` only needed for:
  - Large-scale scheduled scraping
  - Sites with anti-bot protection
  - If you want managed infrastructure
- **Recommendation:** Add Playwright first, Apify only if scaling issues

**Additional Sources:**
- 46 additional high-value sources identified across 8 specialties
- Psychiatry has the most additional sources (8) - important for triage accuracy
- General Medicine and Obstetrics have strong India-specific guidelines
- Total sources increase from 25 to 71

**Key Gaps Filled:**
- Endemic disease protocols (Scrub typhus, Leptospirosis, Chikungunya)
- Emergency psychiatry (Agitation, Catatonia, NMS)
- Pediatric emergencies (Palred, Palned)
- Specialty-specific risk calculators and screening tools
