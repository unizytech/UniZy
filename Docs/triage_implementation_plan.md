# Clinical Triage Suggestion Engine - Implementation Plan

## Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        IMPLEMENTATION PHASES                             │
│                                                                          │
│  Phase 1        Phase 2        Phase 3        Phase 4        Phase 5    │
│  ────────       ────────       ────────       ────────       ────────   │
│  Document       RAG            Integration    Triage         Testing &  │
│  Collection     Pipeline       Layer          Engine         Deployment │
│                                                                          │
│  Week 1-2       Week 2-3       Week 3         Week 3-4       Week 4-5   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Summary

- **Approach:** Simple RAG + Pre-computed lookup tables (not Graph RAG)
- **Latency Target:** 100-150ms retrieval + 8-15s LLM processing
- **Model:** Gemini 2.0 Flash/Pro
- **Database:** Supabase with pgvector
- **Specialties:** General Medicine, Pediatrics, Neonatology, Obstetrics, Fertility, Gastroenterology, Orthopaedics, Psychiatry (8 total)

---

## Phase 1: Document Collection & Organization

**Duration:** 1-2 weeks  
**Goal:** Gather all clinical guidelines, organize by specialty, prepare for ingestion

### 1.0 Requirements & Dependencies

```bash
# Install scraping dependencies
pip install requests beautifulsoup4 playwright pdfplumber pytesseract pdf2image

# Install Playwright browser (required for JavaScript-rendered sites)
playwright install chromium

# For OCR (scanned PDFs), install Tesseract system dependency:
# Ubuntu/Debian: sudo apt-get install tesseract-ocr
# macOS: brew install tesseract
# Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
```

**requirements.txt additions:**
```
requests>=2.31.0
beautifulsoup4>=4.12.0
playwright>=1.40.0
pdfplumber>=0.10.3
pytesseract>=0.3.10
pdf2image>=1.16.3
```

**Scraping Strategy Decision Tree:**
```
┌─────────────────────────────────────────────────────────────────┐
│                     SCRAPING DECISION TREE                       │
│                                                                  │
│  Is it a direct PDF link?                                       │
│  ├─ YES → requests (direct_download) ✅                         │
│  └─ NO ↓                                                        │
│                                                                  │
│  Is the page static HTML?                                       │
│  ├─ YES → BeautifulSoup (beautifulsoup) ✅                      │
│  └─ NO ↓                                                        │
│                                                                  │
│  Does it need JavaScript to load?                               │
│  ├─ YES → Playwright (playwright_required) ✅                   │
│  └─ NO ↓                                                        │
│                                                                  │
│  Is it actively blocking bots?                                  │
│  ├─ YES → Manual download or Apify ($49/mo)                     │
│  └─ NO → Playwright works                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

### 1.1 Guideline Registry (71 Sources Total)

Create a registry of all documents to download:

```python
# File: /data/guideline_registry.py

GUIDELINE_REGISTRY = {
    "general_medicine": {
        "priority_1_must_have": [
            {
                "name": "ICMR Standard Treatment Guidelines",
                "url": "https://main.icmr.nic.in/content/standard-treatment-guidelines",
                "type": "pdf_collection",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["fever", "hypertension", "diabetes", "infections"]
            },
            {
                "name": "NVBDCP Dengue Guidelines",
                "url": "https://nvbdcp.gov.in/WriteReadData/l892s/Dengue-National-Guidelines-2014.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["dengue", "fever", "vector_borne"]
            },
            {
                "name": "NVBDCP Malaria Guidelines",
                "url": "https://nvbdcp.gov.in/Doc/National-Drug-Policy-on-Malaria-2013.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["malaria", "fever"]
            },
            {
                "name": "RNTCP TB Guidelines",
                "url": "https://tbcindia.gov.in/index1.php?sublinkid=4573&level=2&lid=3177&lang=1",
                "type": "pdf_collection",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["tuberculosis", "fever", "cough"]
            },
            {
                "name": "ICMR Scrub Typhus Guidelines",
                "url": "https://main.icmr.nic.in/sites/default/files/guidelines/Scrub_Typhus.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["scrub_typhus", "fever", "endemic"]
            },
            {
                "name": "CSI Hypertension Guidelines",
                "url": "https://www.csi.org.in/guidelines/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["hypertension", "cardiovascular"]
            },
            {
                "name": "RSSDI Diabetes Guidelines",
                "url": "https://rssdi.in/guidelines/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["diabetes", "T2DM", "insulin"]
            }
        ],
        "priority_2_good_to_have": [
            {
                "name": "API Medicine Update",
                "url": "https://www.apiindia.org/medicine-update/",
                "type": "webpage_with_pdfs",
                "scraping": "playwright_required",
                "status": "pending",
                "topics": ["evidence_updates", "clinical_pearls"]
            },
            {
                "name": "AIIMS Treatment Protocols",
                "url": "https://www.aiims.edu/en/departments-and-centers/clinical/medicine.html",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["hospital_protocols", "algorithms"]
            },
            {
                "name": "Indian Chest Society Guidelines",
                "url": "https://www.indianchestsociety.org/guidelines",
                "type": "webpage_with_pdfs",
                "scraping": "playwright_required",
                "status": "pending",
                "topics": ["COPD", "asthma", "pneumonia", "TB"]
            },
            {
                "name": "NCDC Disease Surveillance Guidelines",
                "url": "https://ncdc.gov.in/index4.php?lang=1&level=0&linkid=127&lid=432",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["outbreak", "surveillance", "infectious_disease"]
            }
        ]
    },
    
    "pediatrics": {
        "priority_1_must_have": [
            {
                "name": "IAP Immunization Guidelines 2024",
                "url": "https://iapindia.org/pdf/IAP-Immunization-Guidelines-2024.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["immunization", "vaccines"]
            },
            {
                "name": "IAP Consensus on Fever Management",
                "url": "https://iapindia.org/guidelines",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["fever", "antipyretics"]
            },
            {
                "name": "WHO IMCI Chart Booklet (India adapted)",
                "url": "https://www.who.int/publications/i/item/9789241506823",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["fever", "cough", "diarrhea", "danger_signs"]
            },
            {
                "name": "IAP Standard Treatment Guidelines",
                "url": "https://iapindia.org/iap-guidelines/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["treatment_protocols", "clinical_pathways"]
            },
            {
                "name": "IAP Growth Charts (Indian)",
                "url": "https://iapindia.org/iap-growth-charts/",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["growth", "anthropometry", "nutrition"]
            },
            {
                "name": "Palred Emergency Guidelines",
                "url": "http://palred.org/guidelines/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["emergency", "resuscitation", "shock"]
            }
        ],
        "priority_2_good_to_have": [
            {
                "name": "IAP Drug Formulary",
                "url": "https://iapdrugformulary.com/",
                "type": "database",
                "scraping": "manual",
                "status": "pending",
                "topics": ["pediatric_dosing", "drug_formulary"],
                "note": "Interactive database - consider manual curation"
            },
            {
                "name": "IAP Palani Consensus Statements",
                "url": "https://iapindia.org/consensus-statements/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["consensus", "expert_opinion"]
            },
            {
                "name": "ISPGHAN Guidelines",
                "url": "https://ispghan.org/guidelines/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["GI", "hepatology", "nutrition"]
            }
        ]
    },
    
    "neonatology": {
        "priority_1_must_have": [
            {
                "name": "NNF Clinical Practice Guidelines",
                "url": "https://www.nnfi.org/cpg",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["resuscitation", "sepsis", "jaundice", "feeding", "RDS"],
                "note": "Scrape ALL PDFs - 30+ clinical scenarios"
            },
            {
                "name": "FBNC Operational Guidelines",
                "url": "https://nhm.gov.in/images/pdf/programmes/child-health/guidelines/Facility_Based_Newborn_Care_Operational_Guide.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["SNCU", "essential_newborn_care", "KMC"]
            },
            {
                "name": "NRP India Guidelines",
                "url": "https://www.nnfi.org/nrp",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["resuscitation", "APGAR", "delivery_room"]
            },
            {
                "name": "AIIMS Neonatal Division Protocols",
                "url": "https://www.newbornwhocc.org/clinical-protocols.html",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["SNCU", "level_3_care", "practical_algorithms"]
            },
            {
                "name": "ICMR Kangaroo Mother Care Guidelines",
                "url": "https://nhm.gov.in/images/pdf/programmes/child-health/guidelines/Kangaroo_Mother_Care_Guidelines.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["KMC", "preterm_care", "low_birth_weight"]
            }
        ],
        "priority_2_good_to_have": [
            {
                "name": "Palned Neonatal Emergency Guidelines",
                "url": "http://palned.org/guidelines/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["emergency", "transport", "stabilization"]
            },
            {
                "name": "NNF Sepsis Screen Calculator Documentation",
                "url": "https://www.nnfi.org/sepsis-screen",
                "type": "tool_documentation",
                "scraping": "manual",
                "status": "pending",
                "topics": ["sepsis", "risk_stratification"]
            },
            {
                "name": "WHO Essential Newborn Care",
                "url": "https://www.who.int/publications/i/item/9789241506106",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["essential_care", "immediate_newborn"]
            }
        ]
    },
    
    "obstetrics": {
        "priority_1_must_have": [
            {
                "name": "FOGSI Good Clinical Practice Recommendations",
                "url": "https://www.fogsi.org/gcpr",
                "type": "webpage_with_pdfs",
                "scraping": "playwright_required",
                "status": "pending",
                "topics": ["antenatal", "high_risk", "labor", "complications"],
                "note": "50+ PDFs with tabbed navigation"
            },
            {
                "name": "Government of India ANC Guidelines",
                "url": "https://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/Antenatal_Care_Guidelines.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["ANC", "screening", "high_risk"]
            },
            {
                "name": "ICMR GDM Guidelines",
                "url": "https://main.icmr.nic.in/sites/default/files/guidelines/GDM_Guidelines.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["GDM", "diabetes", "pregnancy"]
            },
            {
                "name": "PIH/Eclampsia Management Protocol",
                "url": "https://nhm.gov.in/images/pdf/programmes/maternal-health/guidelines/PIH_Guidelines.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["preeclampsia", "eclampsia", "hypertension"]
            },
            {
                "name": "FOGSI PPH Management Protocol",
                "url": "https://www.fogsi.org/wp-content/uploads/gcpr/PPH-Management.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["PPH", "obstetric_emergency", "third_stage"]
            },
            {
                "name": "MoHFW LaQshya Guidelines",
                "url": "https://nhm.gov.in/New_Updates_2018/NHM_Components/RMNCH_MH_Guidelines/LaQshya-Guidelines.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["labor_room", "quality_improvement"]
            }
        ],
        "priority_2_good_to_have": [
            {
                "name": "ICOG Practice Bulletins",
                "url": "https://www.icogonline.org/practice-bulletins/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["evidence_based", "clinical_practice"]
            },
            {
                "name": "MoHFW SUMAN Guidelines",
                "url": "https://nhm.gov.in/index1.php?lang=1&level=3&sublinkid=1308&lid=689",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["safe_motherhood", "newborn_care"]
            },
            {
                "name": "WHO Antenatal Care Recommendations",
                "url": "https://www.who.int/publications/i/item/9789241549912",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["ANC", "evidence_based", "international"]
            }
        ]
    },
    
    "fertility": {
        "priority_1_must_have": [
            {
                "name": "ICMR National Guidelines for ART",
                "url": "https://main.icmr.nic.in/sites/default/files/guidelines/ART_Guidelines_2021.pdf",
                "type": "pdf",
                "scraping": "direct_download",
                "status": "pending",
                "topics": ["IVF", "ART", "infertility"]
            },
            {
                "name": "ISAR Guidelines",
                "url": "https://isar.org.in/guidelines",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["infertility_workup", "IUI", "IVF", "PCOS"]
            },
            {
                "name": "ISAR Consensus Statements",
                "url": "https://isar.org.in/consensus/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["PCOS", "male_factor", "IVF_protocols"]
            },
            {
                "name": "FOGSI Infertility Committee Guidelines",
                "url": "https://www.fogsi.org/infertility-committee/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["basic_infertility", "referral_criteria"]
            }
        ],
        "priority_2_good_to_have": [
            {
                "name": "ESHRE Guidelines (Key Documents)",
                "url": "https://www.eshre.eu/Guidelines-and-Legal",
                "type": "webpage_with_pdfs",
                "scraping": "playwright_required",
                "status": "pending",
                "topics": ["evidence_based", "international_standards"]
            }
        ]
    },
    
    "gastroenterology": {
        "priority_1_must_have": [
            {
                "name": "ISG Consensus Statements",
                "url": "https://isg.org.in/consensus-statements",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["hepatitis", "IBD", "cirrhosis", "pancreatitis"]
            },
            {
                "name": "INASL Guidelines on Hepatitis",
                "url": "https://www.inasl.org.in/guidelines",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["hepatitis_B", "hepatitis_C", "liver", "NAFLD", "HCC"]
            },
            {
                "name": "ISG Task Force Reports",
                "url": "https://isg.org.in/task-force-reports/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["IBD", "H_pylori", "functional_GI"]
            },
            {
                "name": "IPA Pancreatitis Guidelines",
                "url": "https://pancreas.org.in/guidelines/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["acute_pancreatitis", "chronic_pancreatitis"]
            }
        ],
        "priority_2_good_to_have": [
            {
                "name": "ISG GI Bleeding Consensus",
                "url": "https://isg.org.in/consensus-statements/",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["UGIB", "LGIB", "variceal_bleeding"]
            },
            {
                "name": "AIIMS GI Division Protocols",
                "url": "https://www.aiims.edu/en/departments-and-centers/clinical/gastro.html",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["endoscopy", "liver_biopsy", "ERCP"]
            }
        ]
    },
    
    "orthopaedics": {
        "priority_1_must_have": [
            {
                "name": "IOA Clinical Guidelines",
                "url": "https://www.ioaindia.org/guidelines",
                "type": "webpage_with_pdfs",
                "scraping": "beautifulsoup",
                "status": "pending",
                "topics": ["fractures", "joint_replacement", "spine"]
            },
            {
                "name": "ICMR TB Spine Guidelines",
                "url": "https://main.icmr.nic.in/content/tuberculosis",
                "type": "pdf",
                "status": "pending",
                "topics": ["TB_spine", "spinal_tuberculosis"]
            }
        ]
    },
    
    "psychiatry": {
        "priority_1_must_have": [
            {
                "name": "IPS Clinical Practice Guidelines",
                "url": "https://indianpsychiatricsociety.org/clinical-practice-guidelines/",
                "type": "webpage_with_pdfs",
                "status": "pending",
                "topics": ["depression", "anxiety", "schizophrenia", "bipolar", "OCD"]
            },
            {
                "name": "NIMHANS Treatment Protocols",
                "url": "https://nimhans.ac.in/treatment-protocols/",
                "type": "webpage_with_pdfs",
                "status": "pending",
                "topics": ["psychosis", "mood_disorders", "substance_use", "child_psychiatry"]
            },
            {
                "name": "MHA 2017 Guidelines",
                "url": "https://main.mohfw.gov.in/acts-rules-and-standards-health-sector/acts/mental-healthcare-act-2017",
                "type": "pdf",
                "status": "pending",
                "topics": ["involuntary_admission", "rights", "capacity_assessment"]
            },
            {
                "name": "DGHS Suicide Prevention Guidelines",
                "url": "https://dghs.gov.in/content/1350_3_NationalSuicidePreventionStrategy.aspx",
                "type": "pdf",
                "status": "pending",
                "topics": ["suicide_risk", "self_harm", "crisis_intervention"]
            },
            {
                "name": "De-addiction Treatment Guidelines (NDDTC)",
                "url": "https://aiaborisha.assam.gov.in/sites/default/files/swf_utility_folder/departments/aiaborisha_medhassu_in_oid_3/menu/document/Treatment%20Standards%20for%20De-addiction%20.pdf",
                "type": "pdf",
                "status": "pending",
                "topics": ["alcohol_dependence", "opioid_dependence", "withdrawal", "detoxification"]
            }
        ],
        "priority_2_good_to_have": [
            {
                "name": "WHO mhGAP Intervention Guide",
                "url": "https://www.who.int/publications/i/item/9789241549790",
                "type": "pdf",
                "status": "pending",
                "topics": ["depression", "psychosis", "epilepsy", "substance_use", "child_mental_health"]
            },
            {
                "name": "IPS Position Statements",
                "url": "https://indianpsychiatricsociety.org/position-statements/",
                "type": "webpage_with_pdfs",
                "status": "pending",
                "topics": ["ECT", "telepsychiatry", "perinatal_mental_health"]
            }
        ]
    }
}
```

### 1.2 Document Download Script

```python
# File: /scripts/download_guidelines.py

import os
import requests
from pathlib import Path
from datetime import datetime
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin

class GuidelineDownloader:
    def __init__(self, output_dir: str = "./data/guidelines"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Clinical Research Bot)'
        })
        self.download_log = []
    
    def download_all(self, registry: dict):
        """Download all documents from registry"""
        
        for specialty, priority_groups in registry.items():
            specialty_dir = self.output_dir / specialty
            specialty_dir.mkdir(exist_ok=True)
            
            for priority, documents in priority_groups.items():
                for doc in documents:
                    if doc.get("type") == "manual":
                        print(f"⏭️  Skipping manual: {doc['name']}")
                        continue
                    
                    if doc.get("type") == "pdf":
                        self._download_pdf(doc, specialty_dir, specialty)
                    
                    elif doc.get("type") in ["webpage_with_pdfs", "pdf_collection"]:
                        self._scrape_pdfs_from_page(doc, specialty_dir, specialty)
        
        self._save_log()
    
    def _download_pdf(self, doc: dict, output_dir: Path, specialty: str):
        """Download a single PDF"""
        try:
            url = doc["url"]
            filename = self._sanitize_filename(doc["name"]) + ".pdf"
            filepath = output_dir / filename
            
            print(f"⬇️  Downloading: {doc['name']}")
            
            response = self.session.get(url, timeout=60)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            doc["status"] = "downloaded"
            doc["local_path"] = str(filepath)
            
            self.download_log.append({
                "name": doc["name"],
                "specialty": specialty,
                "url": url,
                "local_path": str(filepath),
                "status": "success",
                "timestamp": datetime.now().isoformat()
            })
            
            print(f"✅ Downloaded: {filename}")
            
        except Exception as e:
            print(f"❌ Failed: {doc['name']} - {e}")
            self.download_log.append({
                "name": doc["name"],
                "specialty": specialty,
                "url": doc.get("url"),
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    def _scrape_pdfs_from_page(self, doc: dict, output_dir: Path, specialty: str):
        """Scrape PDFs from a webpage"""
        try:
            print(f"🔍 Scraping: {doc['name']}")
            
            response = self.session.get(doc["url"], timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            pdf_links = soup.find_all('a', href=lambda x: x and '.pdf' in x.lower())
            
            pdf_count = 0
            for link in pdf_links:
                href = link.get('href')
                full_url = urljoin(doc["url"], href)
                pdf_name = link.get_text(strip=True) or href.split('/')[-1]
                
                sub_doc = {
                    "name": f"{doc['name']} - {pdf_name}",
                    "url": full_url,
                    "topics": doc.get("topics", [])
                }
                
                self._download_pdf(sub_doc, output_dir, specialty)
                pdf_count += 1
            
            print(f"📄 Found {pdf_count} PDFs on page")
            
        except Exception as e:
            print(f"❌ Scraping failed: {doc['name']} - {e}")
    
    def _sanitize_filename(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name)[:100]
    
    def _save_log(self):
        log_path = self.output_dir / "download_log.json"
        with open(log_path, 'w') as f:
            json.dump(self.download_log, f, indent=2)
        print(f"\n📋 Download log saved to: {log_path}")
```

### 1.3 Differential Trees (Manual Curation)

```python
# File: /data/differential_trees.py

DIFFERENTIAL_TREES = {
    "general_medicine": {
        "fever": {
            "age_groups": ["adult"],
            "must_rule_out": [
                {
                    "diagnosis": "Dengue",
                    "features": ["high_fever", "thrombocytopenia", "leucopenia", "retro_orbital_pain"],
                    "tests": ["NS1_antigen", "Dengue_IgM_IgG"],
                    "timeframe": "Day 1-5: NS1, Day 5+: IgM"
                },
                {
                    "diagnosis": "Malaria",
                    "features": ["fever_with_chills", "periodicity", "splenomegaly", "anemia"],
                    "tests": ["MP_smear", "Malaria_RDT"]
                },
                {
                    "diagnosis": "Typhoid",
                    "features": ["step_ladder_fever", "relative_bradycardia", "coated_tongue"],
                    "tests": ["Blood_culture", "Widal_test"],
                    "note": "Widal unreliable in endemic areas"
                },
                {
                    "diagnosis": "Scrub_Typhus",
                    "features": ["eschar", "lymphadenopathy", "hepatosplenomegaly"],
                    "tests": ["Scrub_typhus_IgM"],
                    "high_risk": ["rural_exposure", "agricultural_work"]
                },
                {
                    "diagnosis": "Leptospirosis",
                    "features": ["conjunctival_suffusion", "severe_myalgia", "jaundice"],
                    "tests": ["Leptospira_IgM"],
                    "high_risk": ["flood_exposure", "water_contact"]
                }
            ],
            "high_probability": [
                {"diagnosis": "Viral_fever", "features": ["self_limiting", "myalgia"]},
                {"diagnosis": "UTI", "features": ["dysuria", "frequency"]},
                {"diagnosis": "URTI", "features": ["cough", "cold", "sore_throat"]}
            ],
            "red_flags": [
                "Altered sensorium",
                "Bleeding manifestations",
                "Hypotension (SBP <90)",
                "Respiratory distress",
                "Platelets <20,000",
                "Renal dysfunction"
            ],
            "first_line_investigations": [
                {"test": "CBC", "rationale": "Leucocytosis/leucopenia, thrombocytopenia", "cost": "LOW"},
                {"test": "CRP", "rationale": "Inflammatory marker", "cost": "LOW"},
                {"test": "Dengue NS1/IgM", "rationale": "Endemic area screening", "cost": "LOW"},
                {"test": "MP smear/RDT", "rationale": "Rule out malaria", "cost": "LOW"},
                {"test": "Urine routine", "rationale": "Rule out UTI", "cost": "LOW"}
            ],
            "history_essentials": [
                "Fever pattern and duration",
                "Associated symptoms",
                "Travel history",
                "Occupational exposure",
                "Recent antibiotic use",
                "Comorbidities"
            ],
            "source": "ICMR_STG_NVBDCP"
        }
    },
    
    "pediatrics": {
        "fever": {
            "age_groups": ["neonate", "infant", "child"],
            "must_rule_out": [
                {
                    "diagnosis": "Sepsis",
                    "features": ["lethargy", "poor_feeding", "poor_perfusion"],
                    "tests": ["Blood_culture", "CBC", "CRP"],
                    "high_risk": ["age_<3_months"]
                },
                {
                    "diagnosis": "Meningitis",
                    "features": ["bulging_fontanelle", "neck_stiffness", "seizures"],
                    "tests": ["LP_CSF_analysis", "Blood_culture"]
                },
                {
                    "diagnosis": "Pneumonia",
                    "features": ["tachypnea", "chest_indrawing", "grunting"],
                    "tests": ["Chest_Xray", "SpO2"],
                    "who_criteria": "Tachypnea: <2mo: >60, 2-12mo: >50, 1-5yr: >40"
                },
                {
                    "diagnosis": "UTI",
                    "features": ["unexplained_fever", "poor_feeding", "irritability"],
                    "tests": ["Urine_routine", "Urine_culture"]
                }
            ],
            "red_flags": [
                "Age <3 months with fever",
                "Lethargy / inconsolable",
                "Not feeding",
                "Bulging fontanelle",
                "Seizures",
                "Respiratory distress",
                "Petechiae / purpura"
            ],
            "first_line_investigations": [
                {"test": "CBC", "rationale": "Infection markers", "cost": "LOW"},
                {"test": "CRP", "rationale": "Bacterial vs viral", "cost": "LOW"},
                {"test": "Urine routine + culture", "rationale": "Occult UTI", "cost": "LOW"}
            ],
            "source": "IAP_IMCI"
        }
    },
    
    "obstetrics": {
        "hypertension": {
            "must_rule_out": [
                {
                    "diagnosis": "Preeclampsia",
                    "features": ["BP_>140/90_after_20weeks", "proteinuria", "edema"],
                    "tests": ["BP", "Urine_protein", "LFT", "RFT", "Platelet"]
                },
                {
                    "diagnosis": "Severe preeclampsia",
                    "features": ["BP_>160/110", "headache", "visual_disturbances", "epigastric_pain"],
                    "tests": ["As above + coagulation profile"]
                },
                {
                    "diagnosis": "HELLP syndrome",
                    "features": ["hemolysis", "elevated_liver_enzymes", "low_platelets"],
                    "tests": ["LDH", "LFT", "Platelet_count", "Peripheral_smear"]
                }
            ],
            "red_flags": [
                "BP >160/110",
                "Severe headache",
                "Visual disturbances",
                "Epigastric pain",
                "Oliguria",
                "Pulmonary edema"
            ],
            "source": "FOGSI_GCPR_PIH"
        }
    },
    
    "neonatology": {
        "respiratory_distress": {
            "must_rule_out": [
                {
                    "diagnosis": "RDS",
                    "features": ["preterm", "grunting", "retraction", "cyanosis"],
                    "tests": ["Chest_Xray", "ABG"],
                    "xray": "Ground glass, air bronchogram"
                },
                {
                    "diagnosis": "TTN",
                    "features": ["term_or_near_term", "LSCS_delivery", "tachypnea"],
                    "tests": ["Chest_Xray"]
                },
                {
                    "diagnosis": "MAS",
                    "features": ["meconium_stained_liquor", "post_term"],
                    "tests": ["Chest_Xray"]
                },
                {
                    "diagnosis": "Pneumothorax",
                    "features": ["sudden_deterioration", "asymmetric_chest"],
                    "tests": ["Chest_Xray", "Transillumination"]
                },
                {
                    "diagnosis": "Congenital heart disease",
                    "features": ["cyanosis", "murmur", "poor_response_to_O2"],
                    "tests": ["Hyperoxia_test", "2D_Echo"]
                }
            ],
            "red_flags": [
                "Severe distress (Downe score >6)",
                "Cyanosis not responding to O2",
                "Apnea",
                "Bradycardia",
                "Shock"
            ],
            "source": "NNF_CPG"
        }
    },
    
    "psychiatry": {
        "depression": {
            "age_groups": ["adolescent", "adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Major Depressive Disorder",
                    "features": ["persistent_sadness", "anhedonia", "sleep_disturbance", "appetite_change", "fatigue", "worthlessness", "concentration_difficulty"],
                    "tests": ["PHQ-9", "HAM-D"],
                    "duration": ">2 weeks of symptoms"
                },
                {
                    "diagnosis": "Bipolar Depression",
                    "features": ["history_of_mania", "family_history_bipolar", "early_onset", "antidepressant_induced_mania"],
                    "tests": ["MDQ", "YMRS_if_manic_features"],
                    "note": "Screen for past manic/hypomanic episodes before starting antidepressants"
                },
                {
                    "diagnosis": "Organic causes",
                    "features": ["hypothyroidism", "B12_deficiency", "anemia", "chronic_illness"],
                    "tests": ["TFT", "CBC", "Vitamin_B12", "blood_glucose"],
                    "note": "Rule out medical causes especially in elderly"
                },
                {
                    "diagnosis": "Substance-induced depression",
                    "features": ["alcohol_use", "benzodiazepine_use", "steroid_use"],
                    "tests": ["Detailed_substance_history", "UDS_if_indicated"]
                }
            ],
            "high_probability": [
                {"diagnosis": "Adjustment disorder with depressed mood", "features": ["identifiable_stressor", "symptoms_<6_months"]},
                {"diagnosis": "Dysthymia", "features": ["chronic_low_mood", ">2_years", "less_severe"]}
            ],
            "red_flags": [
                "Suicidal ideation (active)",
                "Suicide plan or intent",
                "Access to means (pesticides, medications, weapons)",
                "Recent suicide attempt",
                "Psychotic features (delusions, hallucinations)",
                "Severe functional impairment",
                "Refusal to eat/drink",
                "Catatonic features"
            ],
            "history_essentials": [
                "Duration and severity of symptoms",
                "Suicidal ideation - MUST ASK DIRECTLY",
                "Past psychiatric history (previous episodes, hospitalizations)",
                "Past suicide attempts - method, intent, lethality",
                "Family history (depression, bipolar, suicide)",
                "Substance use history",
                "Medical history (thyroid, chronic illness)",
                "Current medications (steroids, beta-blockers, interferon)",
                "Psychosocial stressors",
                "Functional impairment (work, relationships, self-care)"
            ],
            "first_line_investigations": [
                {"test": "PHQ-9", "rationale": "Standardized depression screening", "cost": "FREE"},
                {"test": "TFT", "rationale": "Rule out hypothyroidism", "cost": "LOW"},
                {"test": "CBC", "rationale": "Rule out anemia", "cost": "LOW"},
                {"test": "Vitamin B12", "rationale": "Deficiency mimics depression", "cost": "LOW"},
                {"test": "Blood glucose", "rationale": "Diabetes comorbidity", "cost": "LOW"}
            ],
            "source": "IPS_CPG_Depression_mhGAP"
        },
        
        "anxiety": {
            "age_groups": ["adolescent", "adult", "elderly"],
            "must_rule_out": [
                {
                    "diagnosis": "Generalized Anxiety Disorder",
                    "features": ["excessive_worry", "multiple_domains", "difficulty_controlling_worry", "restlessness", "muscle_tension", "sleep_disturbance"],
                    "tests": ["GAD-7", "HAM-A"],
                    "duration": ">6 months"
                },
                {
                    "diagnosis": "Panic Disorder",
                    "features": ["recurrent_panic_attacks", "fear_of_future_attacks", "avoidance_behavior", "palpitations", "sweating", "trembling", "chest_pain"],
                    "tests": ["Panic_Disorder_Severity_Scale"]
                },
                {
                    "diagnosis": "Medical causes of anxiety",
                    "features": ["hyperthyroidism", "pheochromocytoma", "cardiac_arrhythmia", "hypoglycemia", "COPD"],
                    "tests": ["TFT", "ECG", "blood_glucose", "CBC"]
                },
                {
                    "diagnosis": "Substance-induced anxiety",
                    "features": ["caffeine_excess", "stimulant_use", "alcohol_withdrawal", "benzodiazepine_withdrawal"],
                    "tests": ["Substance_history", "UDS"]
                }
            ],
            "red_flags": [
                "Suicidal ideation",
                "Severe panic with cardiovascular symptoms (rule out MI)",
                "New onset in elderly (rule out medical cause)",
                "Psychotic features",
                "Substance withdrawal"
            ],
            "history_essentials": [
                "Nature and duration of anxiety symptoms",
                "Panic attacks - frequency, triggers, symptoms",
                "Avoidance behaviors",
                "Substance use (caffeine, alcohol, drugs)",
                "Medical history (thyroid, cardiac)",
                "Current medications",
                "Impact on functioning",
                "Comorbid depression - ALWAYS SCREEN"
            ],
            "first_line_investigations": [
                {"test": "GAD-7", "rationale": "Standardized anxiety screening", "cost": "FREE"},
                {"test": "PHQ-9", "rationale": "Screen for comorbid depression", "cost": "FREE"},
                {"test": "TFT", "rationale": "Rule out hyperthyroidism", "cost": "LOW"},
                {"test": "ECG", "rationale": "If cardiac symptoms present", "cost": "LOW"}
            ],
            "source": "IPS_CPG_Anxiety_mhGAP"
        },
        
        "psychosis": {
            "age_groups": ["adolescent", "adult"],
            "must_rule_out": [
                {
                    "diagnosis": "Schizophrenia",
                    "features": ["delusions", "hallucinations", "disorganized_speech", "negative_symptoms", "functional_decline"],
                    "tests": ["PANSS", "BPRS"],
                    "duration": ">6 months with >1 month active symptoms"
                },
                {
                    "diagnosis": "Organic psychosis",
                    "features": ["acute_onset", "visual_hallucinations", "fluctuating_consciousness", "disorientation", "medical_illness"],
                    "tests": ["CBC", "RFT", "LFT", "TFT", "electrolytes", "blood_glucose", "CT_head"],
                    "note": "ALWAYS rule out delirium in acute psychosis"
                },
                {
                    "diagnosis": "Substance-induced psychosis",
                    "features": ["cannabis_use", "stimulant_use", "alcohol_withdrawal", "temporal_relationship_to_substance"],
                    "tests": ["UDS", "blood_alcohol"]
                },
                {
                    "diagnosis": "Mood disorder with psychotic features",
                    "features": ["prominent_mood_symptoms", "mood_congruent_delusions"],
                    "tests": ["Detailed_mood_history"]
                },
                {
                    "diagnosis": "Autoimmune encephalitis",
                    "features": ["young_female", "seizures", "movement_disorder", "rapid_progression"],
                    "tests": ["Anti_NMDA_receptor_antibodies", "CSF_analysis", "MRI_brain"]
                }
            ],
            "red_flags": [
                "Command hallucinations to harm self/others",
                "Persecutory delusions with identified target",
                "Agitation with risk of violence",
                "Catatonia",
                "Neuroleptic malignant syndrome (if on antipsychotics)",
                "Acute onset (consider organic cause)",
                "First episode psychosis (requires full workup)"
            ],
            "history_essentials": [
                "Onset and duration of symptoms",
                "Nature of hallucinations (auditory vs visual)",
                "Content of delusions",
                "Substance use history - CRITICAL",
                "Past psychiatric history",
                "Family history of psychosis",
                "Premorbid functioning",
                "Risk assessment (harm to self/others)",
                "Medical history",
                "Recent head injury or infection"
            ],
            "first_line_investigations": [
                {"test": "CBC", "rationale": "Baseline and rule out infection", "cost": "LOW"},
                {"test": "RFT, LFT", "rationale": "Baseline before antipsychotics", "cost": "LOW"},
                {"test": "TFT", "rationale": "Thyroid dysfunction can cause psychosis", "cost": "LOW"},
                {"test": "Blood glucose", "rationale": "Baseline and rule out hypoglycemia", "cost": "LOW"},
                {"test": "UDS", "rationale": "Rule out substance-induced", "cost": "MEDIUM"},
                {"test": "CT/MRI brain", "rationale": "First episode or atypical features", "cost": "MEDIUM-HIGH"}
            ],
            "source": "IPS_CPG_Schizophrenia_NIMHANS"
        },
        
        "suicide_risk": {
            "age_groups": ["adolescent", "adult", "elderly"],
            "must_assess": [
                {
                    "domain": "Suicidal ideation",
                    "questions": ["thoughts_of_death", "wish_to_die", "thoughts_of_suicide", "frequency", "controllability"],
                    "tools": ["Columbia_Suicide_Severity_Rating_Scale", "PHQ-9_item_9"]
                },
                {
                    "domain": "Suicide plan",
                    "questions": ["specific_plan", "method_identified", "access_to_means", "timing_planned", "preparations_made"]
                },
                {
                    "domain": "Intent",
                    "questions": ["intent_to_act", "reasons_for_living", "reasons_for_dying", "ambivalence"]
                },
                {
                    "domain": "Past attempts",
                    "questions": ["previous_attempts", "method_used", "lethality", "circumstances", "what_stopped_them"]
                }
            ],
            "high_risk_factors": [
                "Previous suicide attempt (strongest predictor)",
                "Access to lethal means (pesticides, medications, firearms)",
                "Current psychiatric disorder (depression, psychosis, substance use)",
                "Recent discharge from psychiatric facility",
                "Recent loss or humiliation",
                "Chronic pain or terminal illness",
                "Social isolation",
                "Male gender + elderly",
                "Family history of suicide",
                "Recent self-harm"
            ],
            "protective_factors": [
                "Strong social support",
                "Responsibility for children/dependents",
                "Religious beliefs against suicide",
                "Fear of death/pain",
                "Future orientation (plans, goals)",
                "Therapeutic alliance"
            ],
            "red_flags_immediate_action": [
                "Active suicidal ideation with plan and intent",
                "Access to means",
                "Command hallucinations to self-harm",
                "Recent serious attempt",
                "Giving away possessions",
                "Saying goodbye to loved ones",
                "Sudden calmness after severe depression"
            ],
            "immediate_actions": [
                "Do not leave patient alone",
                "Remove access to means",
                "Involve family/caregivers",
                "Consider psychiatric admission",
                "Safety planning",
                "Document risk assessment thoroughly"
            ],
            "source": "DGHS_Suicide_Prevention_IPS"
        },
        
        "substance_use": {
            "age_groups": ["adolescent", "adult"],
            "must_rule_out": [
                {
                    "diagnosis": "Alcohol dependence",
                    "features": ["tolerance", "withdrawal", "loss_of_control", "continued_use_despite_harm", "craving"],
                    "tests": ["AUDIT", "CAGE", "LFT", "GGT", "MCV"],
                    "withdrawal": "Tremors, sweating, anxiety, seizures, DT"
                },
                {
                    "diagnosis": "Alcohol withdrawal / DT",
                    "features": ["tremors", "sweating", "tachycardia", "hypertension", "confusion", "hallucinations", "seizures"],
                    "tests": ["CIWA-Ar", "electrolytes", "blood_glucose", "LFT"],
                    "note": "Medical emergency - can be fatal"
                },
                {
                    "diagnosis": "Opioid dependence",
                    "features": ["heroin_use", "prescription_opioid_misuse", "tolerance", "withdrawal"],
                    "tests": ["UDS", "detailed_history"],
                    "withdrawal": "Myalgia, lacrimation, rhinorrhea, diarrhea, piloerection"
                },
                {
                    "diagnosis": "Cannabis use disorder",
                    "features": ["daily_use", "tolerance", "craving", "continued_use_despite_problems"],
                    "tests": ["UDS", "history"]
                },
                {
                    "diagnosis": "Benzodiazepine dependence",
                    "features": ["prescribed_or_illicit_use", "tolerance", "withdrawal_seizures"],
                    "tests": ["UDS", "prescription_review"],
                    "note": "Withdrawal can be life-threatening"
                }
            ],
            "red_flags": [
                "Alcohol withdrawal seizures",
                "Delirium tremens (confusion, hallucinations, autonomic instability)",
                "Wernicke's encephalopathy (confusion, ataxia, ophthalmoplegia)",
                "Opioid overdose (pinpoint pupils, respiratory depression)",
                "Benzodiazepine withdrawal seizures",
                "Suicidal ideation",
                "Severe malnutrition"
            ],
            "history_essentials": [
                "Substance(s) used - type, amount, frequency, route",
                "Duration of use",
                "Last use (timing critical for withdrawal)",
                "Previous withdrawal episodes and severity",
                "Previous detoxification/treatment",
                "Comorbid psychiatric disorders",
                "Medical complications (liver disease, HIV, Hepatitis)",
                "Social consequences",
                "Motivation for change"
            ],
            "first_line_investigations": [
                {"test": "LFT", "rationale": "Alcohol-related liver damage", "cost": "LOW"},
                {"test": "CBC", "rationale": "Macrocytosis, anemia", "cost": "LOW"},
                {"test": "Electrolytes", "rationale": "Derangement in withdrawal", "cost": "LOW"},
                {"test": "Blood glucose", "rationale": "Hypoglycemia in alcoholics", "cost": "LOW"},
                {"test": "UDS", "rationale": "Confirm substances used", "cost": "MEDIUM"},
                {"test": "HIV, HBsAg, HCV", "rationale": "If IV drug use", "cost": "MEDIUM"}
            ],
            "source": "NDDTC_Guidelines_IPS"
        }
    }
}
```

### 1.4 Phase 1 Checklist

- [ ] Create guideline registry with all sources
- [ ] Download all Priority 1 PDFs
- [ ] Verify PDFs are readable (not scanned images)
- [ ] Create differential trees for: fever, jaundice, chest_pain, breathlessness, abdominal_pain (General Medicine)
- [ ] Create differential trees for: fever, diarrhea, seizures (Pediatrics)
- [ ] Create differential trees for: bleeding_pv, hypertension (Obstetrics)
- [ ] Create differential trees for: respiratory_distress, sepsis (Neonatology)
- [ ] Create differential trees for: depression, anxiety, psychosis, suicide_risk, substance_use (Psychiatry)
- [ ] Create investigation protocols for each presentation

---

## Phase 2: RAG Pipeline Setup

**Duration:** 1 week  
**Goal:** Set up database, embeddings, and retrieval functions

### 2.1 Database Schema

```sql
-- File: /database/schema.sql

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Table 1: Clinical Guidelines (Vector Search)
CREATE TABLE clinical_guidelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,
    source_organization TEXT,
    source_url TEXT,
    document_title TEXT NOT NULL,
    specialty TEXT NOT NULL,
    topics TEXT[] DEFAULT '{}',
    presentations TEXT[] DEFAULT '{}',
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_guidelines_specialty ON clinical_guidelines(specialty);
CREATE INDEX idx_guidelines_topics ON clinical_guidelines USING GIN(topics);
CREATE INDEX idx_guidelines_embedding ON clinical_guidelines 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Table 2: Differential Lookup (Direct Query)
CREATE TABLE differential_lookup (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    specialty TEXT NOT NULL,
    presentation TEXT NOT NULL,
    age_group TEXT DEFAULT 'all',
    must_rule_out JSONB DEFAULT '[]',
    high_probability JSONB DEFAULT '[]',
    red_flags TEXT[] DEFAULT '{}',
    history_essentials TEXT[] DEFAULT '{}',
    first_line_investigations JSONB DEFAULT '[]',
    second_line_investigations JSONB DEFAULT '[]',
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(specialty, presentation, age_group)
);

CREATE INDEX idx_differential_lookup ON differential_lookup(specialty, presentation);

-- Table 3: Investigation Protocols
CREATE TABLE investigation_protocols (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    specialty TEXT NOT NULL,
    indication TEXT NOT NULL,
    first_line JSONB DEFAULT '[]',
    second_line JSONB DEFAULT '[]',
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(specialty, indication)
);

-- Function: Vector Search
CREATE OR REPLACE FUNCTION match_guidelines(
    query_embedding vector(768),
    match_specialty text,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id uuid,
    source_name text,
    document_title text,
    chunk_text text,
    topics text[],
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        g.id,
        g.source_name,
        g.document_title,
        g.chunk_text,
        g.topics,
        1 - (g.embedding <=> query_embedding) as similarity
    FROM clinical_guidelines g
    WHERE g.specialty = match_specialty
    ORDER BY g.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

### 2.2 Ingestion Pipeline

```python
# File: /pipeline/ingestion.py

from pathlib import Path
from typing import List, Dict
import PyPDF2
import google.generativeai as genai
from supabase import create_client, Client

class GuidelineIngestionPipeline:
    def __init__(self, supabase_url: str, supabase_key: str, gemini_api_key: str):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        genai.configure(api_key=gemini_api_key)
        self.chunk_size = 800
        self.chunk_overlap = 100
    
    def ingest_all_guidelines(self, data_dir: str = "./data/guidelines"):
        data_path = Path(data_dir)
        
        for specialty_dir in data_path.iterdir():
            if not specialty_dir.is_dir():
                continue
            
            specialty = specialty_dir.name
            print(f"\n📁 Processing: {specialty}")
            
            for pdf_file in specialty_dir.glob("*.pdf"):
                print(f"  📄 {pdf_file.name}")
                self._process_pdf(pdf_file, specialty)
    
    def _process_pdf(self, pdf_path: Path, specialty: str):
        try:
            text = self._extract_pdf_text(pdf_path)
            if len(text) < 100:
                print(f"    ⚠️ Skipping (too short)")
                return
            
            chunks = self._chunk_text(text)
            topics = self._infer_topics(pdf_path.stem, text[:2000])
            
            for i, chunk_text in enumerate(chunks):
                embedding = self._get_embedding(chunk_text)
                
                self.supabase.table('clinical_guidelines').insert({
                    "source_name": "Clinical Guideline",
                    "document_title": pdf_path.stem,
                    "specialty": specialty,
                    "topics": topics,
                    "presentations": topics,
                    "chunk_text": chunk_text,
                    "chunk_index": i,
                    "embedding": embedding
                }).execute()
            
            print(f"    ✅ Ingested {len(chunks)} chunks")
            
        except Exception as e:
            print(f"    ❌ Error: {e}")
    
    def _extract_pdf_text(self, pdf_path: Path) -> str:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    
    def _chunk_text(self, text: str) -> List[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            if end < len(text):
                last_period = chunk.rfind('.')
                if last_period > self.chunk_size * 0.5:
                    chunk = chunk[:last_period + 1]
                    end = start + last_period + 1
            chunks.append(chunk.strip())
            start = end - self.chunk_overlap
        return [c for c in chunks if len(c) > 50]
    
    def _get_embedding(self, text: str) -> List[float]:
        result = genai.embed_content(model="models/text-embedding-004", content=text)
        return result['embedding']
    
    def _infer_topics(self, filename: str, text_sample: str) -> List[str]:
        keywords = ["fever", "sepsis", "pneumonia", "diabetes", "hypertension", 
                   "jaundice", "dengue", "malaria", "typhoid", "tuberculosis"]
        combined = (filename + " " + text_sample).lower()
        return [kw for kw in keywords if kw in combined] or ["general"]
    
    def ingest_differential_trees(self, trees: dict):
        for specialty, presentations in trees.items():
            for presentation, data in presentations.items():
                self.supabase.table('differential_lookup').upsert({
                    "specialty": specialty,
                    "presentation": presentation,
                    "age_group": "all",
                    "must_rule_out": data.get("must_rule_out", []),
                    "high_probability": data.get("high_probability", []),
                    "red_flags": data.get("red_flags", []),
                    "history_essentials": data.get("history_essentials", []),
                    "first_line_investigations": data.get("first_line_investigations", []),
                    "source": data.get("source", "")
                }).execute()
```

### 2.3 RAG Retrieval Class

```python
# File: /pipeline/rag.py

from typing import List, Dict
from dataclasses import dataclass
import google.generativeai as genai
from supabase import create_client, Client

@dataclass
class RetrievedContext:
    guidelines: List[Dict]
    differentials: List[Dict]
    investigations: List[Dict]
    formatted_context: str

class ClinicalRAG:
    def __init__(self, supabase_url: str, supabase_key: str, gemini_api_key: str):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        genai.configure(api_key=gemini_api_key)
        self._cache: Dict[str, RetrievedContext] = {}
    
    def retrieve(self, specialty: str, chief_complaints: List[str], 
                 age_group: str = "adult", top_k: int = 3) -> RetrievedContext:
        
        cache_key = f"{specialty}:{':'.join(sorted(chief_complaints))}:{age_group}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        normalized = [p.lower().split()[0] for p in chief_complaints]
        
        guidelines = self._search_guidelines(specialty, chief_complaints, top_k)
        differentials = self._lookup_differentials(specialty, normalized, age_group)
        investigations = self._lookup_investigations(specialty, normalized)
        
        formatted = self._format_context(guidelines, differentials, investigations)
        
        result = RetrievedContext(
            guidelines=guidelines,
            differentials=differentials,
            investigations=investigations,
            formatted_context=formatted
        )
        
        self._cache[cache_key] = result
        return result
    
    def _search_guidelines(self, specialty: str, presentations: List[str], top_k: int) -> List[Dict]:
        query_text = f"{specialty} " + " ".join(presentations)
        embedding = genai.embed_content(model="models/text-embedding-004", content=query_text)['embedding']
        
        response = self.supabase.rpc('match_guidelines', {
            'query_embedding': embedding,
            'match_specialty': specialty,
            'match_count': top_k
        }).execute()
        
        return response.data or []
    
    def _lookup_differentials(self, specialty: str, presentations: List[str], age_group: str) -> List[Dict]:
        response = self.supabase.table('differential_lookup').select('*').eq(
            'specialty', specialty
        ).in_('presentation', presentations).execute()
        return response.data or []
    
    def _lookup_investigations(self, specialty: str, presentations: List[str]) -> List[Dict]:
        indications = [f"{p}_workup" for p in presentations]
        response = self.supabase.table('investigation_protocols').select('*').eq(
            'specialty', specialty
        ).in_('indication', indications).execute()
        return response.data or []
    
    def _format_context(self, guidelines: List[Dict], differentials: List[Dict], 
                        investigations: List[Dict]) -> str:
        parts = []
        
        if differentials:
            parts.append("## DIFFERENTIAL DIAGNOSIS (India-specific)")
            for d in differentials:
                parts.append(f"\n### {d['presentation'].upper()}")
                if d.get('must_rule_out'):
                    parts.append("**Must Rule Out:**")
                    for item in d['must_rule_out']:
                        tests = ", ".join(item.get('tests', []))
                        parts.append(f"- {item['diagnosis']}: {tests}")
                if d.get('red_flags'):
                    parts.append(f"**Red Flags:** {', '.join(d['red_flags'])}")
        
        if guidelines:
            parts.append("\n## CLINICAL GUIDELINES")
            for g in guidelines[:3]:
                parts.append(f"\n**Source:** {g.get('document_title', 'Unknown')}")
                parts.append(g.get('chunk_text', '')[:400] + "...")
        
        return "\n".join(parts)
```

### 2.4 Phase 2 Checklist

- [ ] Create Supabase project
- [ ] Enable pgvector extension
- [ ] Run schema.sql
- [ ] Run ingestion pipeline on all PDFs
- [ ] Ingest differential trees
- [ ] Test vector search function
- [ ] Test differential lookup
- [ ] Measure retrieval latency (<200ms target)

---

## Phase 3: Integration Layer

**Duration:** 3-5 days  
**Goal:** Define structured insights class, map to existing extraction output

### 3.1 Structured Insights Class

```python
# File: /models/structured_insights.py

from dataclasses import dataclass, field
from typing import List, Dict

class Specialty:
    GENERAL_MEDICINE = "general_medicine"
    PEDIATRICS = "pediatrics"
    NEONATOLOGY = "neonatology"
    OBSTETRICS = "obstetrics"
    FERTILITY = "fertility"
    GASTROENTEROLOGY = "gastroenterology"
    ORTHOPAEDICS = "orthopaedics"
    PSYCHIATRY = "psychiatry"

@dataclass
class StructuredInsights:
    specialty: str
    patient_age: str = ""
    patient_gender: str = ""
    age_group: str = "adult"
    
    chief_complaints: List[str] = field(default_factory=list)
    
    history_of_present_illness: Dict = field(default_factory=lambda: {
        "onset": "", "duration": "", "progression": "", "severity": "",
        "negative_findings": [], "impact_on_daily_life": ""
    })
    
    past_medical_history: List[str] = field(default_factory=list)
    past_surgical_history: List[str] = field(default_factory=list)
    family_history: str = ""
    social_history: Dict = field(default_factory=dict)
    birth_history: str = ""
    
    allergies: List[str] = field(default_factory=list)
    current_medications: List[Dict] = field(default_factory=list)
    
    examination_findings: Dict = field(default_factory=lambda: {
        "vital_signs": {}, "cardiovascular_system": "", "respiratory_system": "",
        "central_nervous_system": "", "per_abdomen": ""
    })
    
    investigations_ordered: List[str] = field(default_factory=list)
    investigations_results: List[Dict] = field(default_factory=list)
    
    diagnoses_discussed: List[str] = field(default_factory=list)
    treatment_plan: List[str] = field(default_factory=list)
    advice_given: Dict = field(default_factory=dict)
    follow_up: Dict = field(default_factory=dict)
    
    patient_anxiety_level: str = ""
    financial_concerns: str = ""
    compliance_likelihood: str = ""
    
    def derive_age_group(self) -> str:
        if not self.patient_age:
            return "adult"
        try:
            age_str = self.patient_age.lower()
            if "day" in age_str:
                return "neonate"
            elif "month" in age_str:
                months = int(''.join(filter(str.isdigit, age_str)))
                return "infant" if months <= 12 else "toddler"
            else:
                years = int(''.join(filter(str.isdigit, age_str)))
                if years < 1: return "infant"
                elif years < 3: return "toddler"
                elif years < 12: return "child"
                elif years < 18: return "adolescent"
                elif years < 60: return "adult"
                else: return "elderly"
        except:
            return "adult"
    
    @classmethod
    def from_extraction_output(cls, extraction: Dict) -> "StructuredInsights":
        insights = cls(
            specialty=extraction.get("specialty", "general_medicine"),
            patient_age=extraction.get("patient_age", ""),
            patient_gender=extraction.get("patient_gender", ""),
            chief_complaints=extraction.get("chief_complaints", []),
            history_of_present_illness=extraction.get("history_of_present_illness", {}),
            past_medical_history=extraction.get("past_medical_history", []),
            family_history=extraction.get("family_history", ""),
            allergies=extraction.get("allergies", []),
            current_medications=extraction.get("current_medications", []),
            examination_findings=extraction.get("examination_findings", {}),
            investigations_ordered=extraction.get("investigations_ordered", []),
            diagnoses_discussed=extraction.get("diagnoses_discussed", []),
            treatment_plan=extraction.get("treatment_plan", []),
            patient_anxiety_level=extraction.get("patient_anxiety_level", ""),
            financial_concerns=extraction.get("financial_concerns", ""),
            compliance_likelihood=extraction.get("compliance_likelihood", "")
        )
        insights.age_group = insights.derive_age_group()
        return insights
```

### 3.2 Extraction Mapper

```python
# File: /models/extraction_mapper.py

from typing import Dict
from .structured_insights import StructuredInsights

class ExtractionMapper:
    @staticmethod
    def from_op_extraction(extraction: Dict) -> StructuredInsights:
        return StructuredInsights(
            specialty=extraction.get("specialty", "general_medicine"),
            patient_age=extraction.get("physical_examination", {}).get("age", ""),
            patient_gender=extraction.get("physical_examination", {}).get("gender", ""),
            chief_complaints=extraction.get("complaints", {}).get("chief_complaints", []),
            history_of_present_illness=extraction.get("history_of_present_illness", {}),
            past_medical_history=extraction.get("history", {}).get("past_medical_history", []),
            family_history=extraction.get("history", {}).get("family_history", ""),
            current_medications=extraction.get("history", {}).get("current_medications", []),
            examination_findings=extraction.get("physical_examination", {}),
            investigations_ordered=extraction.get("investigations", {}).get("laboratory_tests", []),
            diagnoses_discussed=[extraction.get("diagnosis", {}).get("primary_diagnosis", "")],
            treatment_plan=extraction.get("treatment_plan_advice", {}).get("medications", []),
            patient_anxiety_level=extraction.get("subtext_analysis", {}).get("patient_factors", {}).get("anxiety_level_before", ""),
            financial_concerns=extraction.get("subtext_analysis", {}).get("patient_factors", {}).get("financial_concerns", "")
        )
    
    @staticmethod
    def from_neonatal_extraction(extraction: Dict) -> StructuredInsights:
        medical_problems = extraction.get("medicalProblem", [])
        return StructuredInsights(
            specialty="neonatology",
            patient_age=f"{extraction.get('gestationWeeks', '')} weeks",
            patient_gender=extraction.get("sex", ""),
            age_group="neonate",
            chief_complaints=[mp.get("problem_name", "") for mp in medical_problems],
            birth_history=f"Weight: {extraction.get('birthWeight', 'N/A')}g, Mode: {extraction.get('modeOfDelivery', 'N/A')}",
            examination_findings={"apgar": extraction.get("apgar", {})}
        )
```

### 3.3 Phase 3 Checklist

- [ ] Create StructuredInsights dataclass
- [ ] Create ExtractionMapper class
- [ ] Test mapping from OP extraction
- [ ] Test mapping from neonatal extraction
- [ ] Test with 5 real extractions per specialty

---

## Phase 4: Triage Engine

**Duration:** 1 week  
**Goal:** Build the multi-step triage suggestion engine

### 4.1 Triage Engine

```python
# File: /engine/triage_engine.py

from typing import Dict, List, Optional
from dataclasses import dataclass
import json
import google.generativeai as genai

from models.structured_insights import StructuredInsights
from pipeline.rag import ClinicalRAG, RetrievedContext

@dataclass
class TriageSuggestions:
    critical_actions: List[Dict]
    important_considerations: List[Dict]
    nice_to_have: List[Dict]
    psychosocial_recommendations: List[Dict]
    overall_assessment: Dict
    rag_context: Optional[RetrievedContext] = None

class TriageSuggestionEngine:
    def __init__(self, gemini_api_key: str, supabase_url: str, supabase_key: str,
                 model_name: str = "gemini-2.0-flash"):
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel(model_name)
        self.generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
        self.rag = ClinicalRAG(supabase_url, supabase_key, gemini_api_key)
    
    def generate_suggestions(self, insights: StructuredInsights) -> TriageSuggestions:
        # Step 0: RAG retrieval
        rag_context = self.rag.retrieve(
            specialty=insights.specialty,
            chief_complaints=insights.chief_complaints,
            age_group=insights.age_group
        )
        
        # Step 1: Generate ideal triage
        ideal_triage = self._step1_ideal_triage(insights, rag_context)
        
        # Step 2: Gap analysis
        gaps = self._step2_gap_analysis(insights, ideal_triage)
        
        # Step 3: Prioritize
        final = self._step3_prioritize(insights, gaps)
        
        return TriageSuggestions(
            critical_actions=final.get("critical_actions", []),
            important_considerations=final.get("important_considerations", []),
            nice_to_have=final.get("nice_to_have", []),
            psychosocial_recommendations=final.get("psychosocial_recommendations", []),
            overall_assessment=final.get("overall_assessment", {}),
            rag_context=rag_context
        )
    
    def _step1_ideal_triage(self, insights: StructuredInsights, 
                           rag_context: RetrievedContext) -> Dict:
        prompt = f"""Generate IDEAL triage checklist.

## SPECIALTY: {insights.specialty}

## CLINICAL GUIDELINES
{rag_context.formatted_context}

## PATIENT
Age: {insights.patient_age}, Gender: {insights.patient_gender}
Chief Complaints: {json.dumps(insights.chief_complaints)}
HPI: {json.dumps(insights.history_of_present_illness)}

## OUTPUT (JSON)
{{
  "history_questions_required": [],
  "examination_required": [],
  "differential_diagnoses": [],
  "investigations_required": [],
  "red_flags_to_exclude": []
}}"""
        
        response = self.model.generate_content(prompt, generation_config=self.generation_config)
        return json.loads(response.text)
    
    def _step2_gap_analysis(self, insights: StructuredInsights, ideal_triage: Dict) -> Dict:
        prompt = f"""Compare DONE vs IDEAL. Output MISSING items only.

## IDEAL TRIAGE
{json.dumps(ideal_triage, indent=2)}

## WHAT WAS DONE
Complaints: {json.dumps(insights.chief_complaints)}
HPI: {json.dumps(insights.history_of_present_illness)}
Examination: {json.dumps(insights.examination_findings)}
Investigations: {json.dumps(insights.investigations_ordered)}
Diagnoses: {json.dumps(insights.diagnoses_discussed)}

## OUTPUT (JSON)
{{
  "missed_history_questions": [],
  "missed_examinations": [],
  "unconsidered_diagnoses": [],
  "missing_investigations": [],
  "unchecked_red_flags": []
}}"""
        
        response = self.model.generate_content(prompt, generation_config=self.generation_config)
        return json.loads(response.text)
    
    def _step3_prioritize(self, insights: StructuredInsights, gaps: Dict) -> Dict:
        prompt = f"""Prioritize gaps for doctor.

## GAPS
{json.dumps(gaps, indent=2)}

## CONTEXT
Financial concerns: {insights.financial_concerns}
Compliance: {insights.compliance_likelihood}

## OUTPUT (JSON)
{{
  "critical_actions": [max 5],
  "important_considerations": [max 10],
  "nice_to_have": [max 10],
  "psychosocial_recommendations": [],
  "overall_assessment": {{
    "triage_completeness": "COMPREHENSIVE|ADEQUATE|MINOR_GAPS|SIGNIFICANT_GAPS",
    "key_concern": "string",
    "summary_for_doctor": "2-3 sentences",
    "top_3_priorities": []
  }}
}}"""
        
        response = self.model.generate_content(prompt, generation_config=self.generation_config)
        return json.loads(response.text)
```

### 4.2 API Endpoint

```python
# File: /api/triage_api.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
import os

from models.extraction_mapper import ExtractionMapper
from engine.triage_engine import TriageSuggestionEngine

app = FastAPI(title="Clinical Triage Suggestions API")

engine = TriageSuggestionEngine(
    gemini_api_key=os.getenv("GEMINI_API_KEY"),
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)

class TriageRequest(BaseModel):
    extraction_output: Dict
    extraction_type: str = "op"

class TriageResponse(BaseModel):
    critical_actions: List[Dict]
    important_considerations: List[Dict]
    nice_to_have: List[Dict]
    overall_assessment: Dict

@app.post("/api/triage/suggestions", response_model=TriageResponse)
async def get_triage_suggestions(request: TriageRequest):
    try:
        if request.extraction_type == "op":
            insights = ExtractionMapper.from_op_extraction(request.extraction_output)
        elif request.extraction_type == "neonatal":
            insights = ExtractionMapper.from_neonatal_extraction(request.extraction_output)
        else:
            raise HTTPException(400, "Invalid extraction_type")
        
        suggestions = engine.generate_suggestions(insights)
        
        return TriageResponse(
            critical_actions=suggestions.critical_actions,
            important_considerations=suggestions.important_considerations,
            nice_to_have=suggestions.nice_to_have,
            overall_assessment=suggestions.overall_assessment
        )
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### 4.3 Phase 4 Checklist

- [ ] Create TriageSuggestionEngine class
- [ ] Implement Step 1: Ideal triage generation
- [ ] Implement Step 2: Gap analysis
- [ ] Implement Step 3: Prioritization
- [ ] Create FastAPI endpoint
- [ ] Test with 5 General Medicine cases
- [ ] Test with 5 Pediatrics cases
- [ ] Test with 3 Psychiatry cases (depression, anxiety, suicide risk)
- [ ] Measure latency (<15 seconds target)

---

## Phase 5: Testing & Deployment

**Duration:** 1 week  
**Goal:** Evaluate quality, optimize, deploy

### 5.1 Evaluation Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Relevance | >70% | Expert review of suggestions |
| Completeness | >80% | % of known gaps identified |
| False Positives | <20% | Irrelevant suggestions |
| Latency | <15s | End-to-end timing |
| Missed Red Flags | 0% | Critical safety check |

### 5.2 Phase 5 Checklist

- [ ] Create 10 ground truth test cases
- [ ] Run evaluation
- [ ] Achieve >70% relevance score
- [ ] Achieve 0% missed red flags
- [ ] Optimize prompts based on evaluation
- [ ] Deploy API to production
- [ ] Set up monitoring
- [ ] Create documentation

---

## Summary Timeline

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Phase 1** | Week 1-2 | Downloaded guidelines, differential trees |
| **Phase 2** | Week 2-3 | Database, ingestion, RAG retrieval |
| **Phase 3** | Week 3 | StructuredInsights class, mappers |
| **Phase 4** | Week 3-4 | Triage engine, API endpoint |
| **Phase 5** | Week 4-5 | Evaluation, deployment |

**Total: 4-5 weeks**

---

## Directory Structure

```
/project
├── /data
│   ├── /guidelines
│   │   ├── /general_medicine
│   │   ├── /pediatrics
│   │   ├── /neonatology
│   │   ├── /obstetrics
│   │   ├── /fertility
│   │   ├── /gastroenterology
│   │   ├── /orthopaedics
│   │   └── /psychiatry
│   ├── guideline_registry.py
│   └── differential_trees.py
├── /database
│   └── schema.sql
├── /pipeline
│   ├── __init__.py
│   ├── ingestion.py
│   └── rag.py
├── /models
│   ├── __init__.py
│   ├── structured_insights.py
│   └── extraction_mapper.py
├── /engine
│   ├── __init__.py
│   └── triage_engine.py
├── /api
│   └── triage_api.py
├── /scripts
│   └── download_guidelines.py
├── /evaluation
│   └── evaluator.py
└── requirements.txt
```

---

## Quick Start Commands

```bash
# 1. Install dependencies
pip install supabase google-generativeai PyPDF2 beautifulsoup4 fastapi uvicorn

# 2. Set environment variables
export GEMINI_API_KEY="your-key"
export SUPABASE_URL="your-url"
export SUPABASE_KEY="your-key"

# 3. Download guidelines
python scripts/download_guidelines.py

# 4. Run ingestion
python -c "from pipeline.ingestion import GuidelineIngestionPipeline; p = GuidelineIngestionPipeline(...); p.ingest_all_guidelines()"

# 5. Start API
uvicorn api.triage_api:app --reload
```
