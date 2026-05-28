"""
Raster Drug Database Lookup Tables

This file contains the drug name to drugId mappings from Raster's mas_drugivfluid table.
Used to convert extracted drug names (brand or generic) to their Raster database IDs.

Used by: NEO_OP, NEO_DAILY, NEO_PROFORMA, NEO_DISCHARGE, NEO_ADMISSION templates
"""

from typing import Dict, Optional, List, Tuple
from difflib import SequenceMatcher
import re
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# DRUG DATABASE FROM RASTER mas_drugivfluid TABLE
# Format: {id: (brand_name, generic_name, value/strength)}
# ============================================================================

DRUG_DATABASE: Dict[int, Tuple[str, str, str]] = {
    1: ("Dopamine", "Dopamine", ""),
    2: ("Dobutamine", "Dobutamine", ""),
    3: ("Noradrenaline", "Noradrenaline", ""),
    4: ("Milrinone", "Milrinone", ""),
    5: ("Sildenafil", "Sildenafil", ""),
    7: ("10% Dextrose", "10% Dextrose", ""),
    8: ("Isolyte P", "Isolyte P", ""),
    9: ("Isolyte M", "Isolyte M", ""),
    10: ("1/2 DNS", "DNS", ""),
    11: ("DNS", "DNS", ""),
    12: ("0.45% saline", "0.45% saline", ""),
    13: ("0.9% saline", "0.9% saline", ""),
    14: ("Aminoven Infant 10%", "Aminoacid", "10%"),
    15: ("LIPIDS", "LIPIDS", ""),
    16: ("Morphine", "Morphine", ""),
    17: ("Tazar", "Piperacillin Tazobactam", ""),
    18: ("Merotrol 250", "Meropenem", ""),
    19: ("Amikamac 100", "Amikacin", ""),
    20: ("Neovec", "Vercuronium", ""),
    21: ("Cathflush", "Heparin Saline", ""),
    22: ("5% Dextrose", "5% Dextrose", ""),
    23: ("Cathflush", "Heparin saline (1unit/1ml)", ""),
    24: ("Mezolam", "Midazolam", ""),
    25: ("Adrenaline", "Adrenaline", ""),
    26: ("Prostaglandin", "Prostaglandin", ""),
    27: ("Midazolam", "Midazolam", ""),
    28: ("Insulin", "Insulin", ""),
    29: ("3% Saline", "Hypertonic Saline", ""),
    30: ("PRBC", "Packed Red Blood Cells", ""),
    31: ("Imicrit 500mg", "Imipenem", ""),
    32: ("Sudostar (colistin)", "Colistin", ""),
    33: ("Ambilon 50", "Liposomal Amphotercin", ""),
    34: ("Fluconazole", "Fluconazole", ""),
    37: ("Caffirate", "Caffeine", ""),
    38: ("Ampicillin", "Ampicillin", ""),
    39: ("Ampicillin", "Ampicillin 500mg", ""),
    40: ("Taximax", "Cefotaxime + Sulbactam", ""),
    41: ("Genticin", "Gentamycin", ""),
    42: ("Sodium Bicarbonate", "Sodium Bicarbonate 7.5%", ""),
    43: ("Lasix", "Frusemide", ""),
    44: ("Decadron", "Dexamethasone", ""),
    46: ("Dexona", "Dexamethasone", ""),
    47: ("Calcium gluconate", "Calcium gluconate", ""),
    48: ("Vancogen", "Vancomycin", ""),
    49: ("Cynocobalamin B12", "Inj.Cyanocobalamine(B12)", ""),
    51: ("Roscillin", "Ampicillin", ""),
    52: ("Normal Saline", "0.9% Sodium Chloride", ""),
    54: ("Apnicaf", "Caffeine Citrate", ""),
    70: ("Eptoin", "Phenytoin", "30 mg/5 ml"),
    98: ("Domstal drops", "Domperidone", "1mg/1ml"),
    112: ("Syrup Gardenal", "Phenobarbitone", "20 mg/5 ml"),
    132: ("Kenadion", "Phytomenadione", "0.5 ml/1 mg"),
    134: ("Dexona", "Dexamethasone sodium phosphate", "4 mg/ 2ml"),
    135: ("Rantidine", "Rantac Injection", ""),
    138: ("Vancogen continuous infusion", "Vancomycin continuous infusion", ""),
    139: ("Vancogen", "Vancomycin", ""),
    144: ("Dexona", "Dexamethasone", "4mg/ml"),
    145: ("Kenadion", "Pytomenadione", "1mg/0.5 ml"),
    146: ("Epilive", "Levetiracetam", ""),
    147: ("Magneon", "50% Magnesium sulphate", ""),
    148: ("Vir 500", "Aciclovir", ""),
    151: ("Fentanyl", "Fentanyl", ""),
    152: ("Sucol", "Suxamethonium", ""),
    153: ("Atropine", "Atropine", ""),
    156: ("Tamin Inj", "Paracetamol", "100 mg/100 ml"),
    157: ("M.V.I.", "Multi-Vitamin Injection", "10 ml vial"),
    158: ("Neomol - 80", "Paracetamol", "80 mg per suppository"),
    159: ("Fungilip 50", "Liposomal Amphotercin", "50 mg/12 ml"),
    161: ("Inj Potphos", "Potassium Phosphate", "1 ml/ 4.4 mmol of K+ and 3 mmol of P"),
    163: ("Rantidine", "Rantacinj", ""),
    164: ("Tablet Tropan", "Oxybutynin Hydrochloride", ""),
    166: ("Targocid 200", "Teicoplanin", ""),
    168: ("Apnicaf", "Apnicaf", ""),
    169: ("Ns", "Normal saline", ""),
    170: ("Roscillin", "Ampicillin", ""),
    171: ("Cyno", "Inj.Cyanocobalamine(B12)", ""),
    172: ("Dexamethasone", "Dexona", ""),
    173: ("Decdran", "Dexamethasone", ""),
    174: ("Vancomycin", "Vancomycin", ""),
    175: ("Tigefic", "Tigecycline", "50 mg vial"),
    176: ("Targocid Inj", "Teicoplanin", "200 mg"),
    177: ("Zostum 500", "Cefoperazone Sulbactam", "500 mg"),
    178: ("Gerbisa", "Bisacodyl", "5 mg"),
    179: ("FFP", "Fresh Frozen Plasma", "Plasma"),
    182: ("Platelet concentrate", "Platelets", "Fresh Platelets"),
    183: ("Syrup Omnacortil", "Prednisolone", "5mg/5ml"),
    184: ("Cafirate", "Caffeine Citrate", "20 mg/1 ml"),
    185: ("Magnova", "Cefipime Tazobactam", "1 gram/125 mg"),
    190: ("Plasmaglob", "Human immunoglobulin 5%", "0.5gm/10ml"),
    191: ("Plasmaglob", "Human immunoglobulin 5%", "0.5gm/10ml"),
    192: ("Plasmaglob", "Human immunoglobulin 5%", "0.5gm/10ml"),
    193: ("Aquazet", "Hydrochlorthiazide", "12.5mg"),
    194: ("Proglicem/Balila", "Diazoxide", "25mg"),
    232: ("Sucol", "Suxamethonium", ""),
    233: ("Sodium Bicarbonate", "Sodium Bicarbonate 7.5%", ""),
    234: ("Fentanyl", "Fentanyl", ""),
    235: ("Atropine", "Atropine", ""),
    236: ("Carnisure", "Carnitine", "500mg/5ml"),
    237: ("T.Frisium", "clobazam", "5mg"),
    238: ("Syrup Azee 200", "azithromycin", "200/5ml"),
    239: ("Akair lc", "Monteleukast +Levocetrizine", "4mg+2.5mg"),
    240: ("Syr.Augpen DS", "Amoxycillin +Potassium Clavunate", "400+57"),
    241: ("Syr.Of", "Ofloxacin", "50mg/5ml"),
    242: ("Syr.Of", "Ofloxacin", "100mg/5ml"),
    243: ("Syr.Dolo", "Paracetamol", "150/5ml"),
    244: ("Syr.Dolopar", "Paracetamol", "250/5ml"),
    245: ("Ondem drops", "Ondansetron", "2mg in 5ml"),
    246: ("T.Theo-asthalin", "Salbutamol +Theoasthalin", "2mg+100mg"),
    247: ("Syr.Piriton CS", "Cpm+Dexomethorphan hydrobromide", "4mg+10mg in 5 ml"),
    248: ("Syr.Ventryl LS", "Ambroxal+Levosalbutamol+Guaifenesin", "LS 0.5mg in 5 ml"),
    249: ("Drops Uprise D3", "Vit D3", "800 U in 1 ml"),
    250: ("Momate cream", "Mometasone 0.1%", "0.1%"),
    251: ("Rashfree", "Benzalkonium chloride & Zinc oxide cream", "0.1% + 8.5%"),
    252: ("Tab Montak LC kid", "Montelukast sodium and Levocetrizine Hydrochloride", "4mg+ 2.5 mg"),
    253: ("Tab Augmetin", "Amoxycillin + Clavulanic acid", "500mg+125 mg"),
    254: ("Tab lasix", "Furosemide", "40mg"),
    255: ("Syr Mucain Gel", "Oxetacaine+ Aluminium Hydroxid+ Milk of Magnesia", "10 mg+ 0.29 gm + 98 mg / 5ml"),
    256: ("Augpen HS", "Amoxycyllin + Clavulanic acid", "200 mg+ 28.5 mg"),
    257: ("Syr.Maxtra", "chlorpheniramine maleate +phenylephrine", "2mg+5mg"),
    258: ("Flutibact Ointment", "Fluticasone Propionate + Muprirocin", "0.005% + 2%"),
    259: ("Clam kid forte", "Amoxycyllin & Potassium Clavulanate", "400mg+ 57 mg"),
    260: ("Montar", "Monteleukast", "5mg"),
    261: ("MONTAIR", "Monteleukast", "5mg"),
    262: ("Tablet folic acid", "Folvite", "5mg"),
    263: ("A to Z drops", "Multivitamin", "Drops"),
    264: ("Tab Zyrtec", "Citrizine", "10mg"),
    265: ("TIMOLOL DROPS", "Timolol Maleate", "0.5%"),
    866: ("Ultra D3 drops", "Cholecalciferol", "400 units/ml"),
    867: ("Calcimax Plain suspension", "Calcium Carbonate", "250 mg/5 ml"),
    868: ("Hifital Drops", "Multi-vitamin Drops", "Multi vitamin combo"),
    869: ("Lizomac 100 mg syrup", "Linezolid", "100 mg in 5 ml"),
    870: ("D3 Forte drops", "Cholecalciferol", "800 IU/ml"),
    871: ("Feronia Xt drops", "Elemental iron", "10 mg/ml"),
    872: ("T. Folvite", "Folic acid", "5 mg tab"),
    873: ("Augmentin DDS", "Co-amoxiclav", "400 mg/5 ml"),
    874: ("Colic aid drops", "Simethicone", "N/A"),
    875: ("T-Minic Drops", "Chlorpheniramine & Phenylephrine", "2mg/5 mg in 1 ml"),
    876: ("Calpol drops", "Paracetamol", "100 mg in 1 ml"),
    877: ("Nasoclear nasal drops", "Sodium chloride", "0.65%"),
    878: ("Vi-Synerol drops", "Multi-vitamins", "Multi-vitamin combo"),
    879: ("Eptoin", "Phenytoin", ""),
    880: ("Rantac Syrup", "Ranitidine", "75 mg/5 ml"),
    881: ("Calcimax P suspension", "Calcium/Phosphorus", "300/150 in 10 ml"),
    882: ("Zincovit drops", "Multi-vitamins", "Multi-vitamin combo"),
    883: ("Vitanova 800 drops", "Cholecalciferol", "800 IU/ml"),
    884: ("T. Hisone", "Hydrocortisone", "1 tablet/10 mg"),
    885: ("T Floricort", "Fludrocortisone", "1 tablet/100 mcg"),
    886: ("Septran syrup", "Trimethoprim", "40 mg TMP/5 ml"),
    887: ("Econorm Sachet", "Probiotic", "1 sachet/5 ml milk"),
    888: ("Nasivion Mini drops", "Oxymetazoline", "0.01%"),
    889: ("Furoped drops", "Furosemide", "10 mg/ml"),
    890: ("T. Aldactone", "Spironolactone", "25 mg/ 1 tablet"),
    891: ("Coriminic drops", "Chlorpheniramine & Phenylephrine", "1 mg/15 mg"),
    892: ("Lasix", "Furosemide", "40 mg tablet"),
    893: ("Calpol suspension", "Paracetamol", "120 mg/5 ml"),
    894: ("Ibugesic suspension", "Ibuprofen", "100 mg/5 ml"),
    895: ("Alerid Syrup", "Cetirizine", "5 mg in 5 ml"),
    896: ("Emeset Syrup", "Ondansetron", "2 mg in 5 ml"),
    897: ("Bandy Suspension", "Albendazole", "200 mg in 5 ml"),
    898: ("Levexx Syrup", "Levetiracetam", "100 mg/1 ml"),
    899: ("Augmentin Duo", "Co-Amoxiclav", "200 mg/5ml"),
    900: ("Zanocin 50 syrup", "Ofloxacillin", "50 mg/5 ml"),
    901: ("T Lasix", "Furosemide", "40 mg tab"),
    902: ("T.Envas", "Enalapril", "2.5 mg tab"),
    903: ("Syp Acyclovir", "Acyclovir", "400mg/5ml"),
    904: ("Ciplox eye drops", "Ciprofloxacin eye drop", ""),
    905: ("Hicool eye ointment", "N/A", ""),
    906: ("Domstal Suspension", "Domperidone", "1mg/1ml"),
    907: ("Apnicaf drops", "Caffine", "20mg/1ml"),
    908: ("Tab Sildenafil", "Sildenafil", "25mg"),
    909: ("Cefixime", "N/A", ""),
    910: ("Taxim - O", "Cefixime", "50 mg in 5 ml"),
    911: ("Ventryl", "Terbutaline", "10 ml in 2.5 mg"),
    912: ("T-Bact Ointment", "Mupirocin", ""),
    913: ("T. Diamox", "Acetazolamide", "250 mg tablet"),
    914: ("Sporidex Syrup", "Cephalexin", "125 mg in 5 ml"),
    915: ("Dixin Paed", "Digoxin", "50 micrograms/1 ml"),
    916: ("Levolin Syp", "Levosalbutamol", "1 mg/5 ml"),
    917: ("Syp Azilide 200", "Azithromycin", "200 mg/5 ml"),
    918: ("Asthalin Respules", "Salbutamol", "2.5 mg/2.5 ml"),
    919: ("Ipravent", "Ipratropium Bromide", "500 mcg/2 ml"),
    920: ("Budecort Inhaler", "Budenoside", "100 mcg/puff"),
    921: ("Calpol 250 susp", "Paracetamol", "250 mg in 5 ml"),
    922: ("Duphalac Syrup", "N/A", ""),
    923: ("Gardenal", "Phenobarbitone", ""),
    924: ("Pedichloryl suspension", "Triclophos", "500 mg/5 ml"),
    925: ("Picasa oral suspension", "Posaconazole", "40 mg/ml"),
    926: ("Betnovate GM", "Betamethasone, Gent, mupirocin", ""),
    927: ("Tab Voriconazole", "Voriconazole", "50mg"),
    928: ("Tab Fluconazole", "Fluconazole", "50 mg"),
    929: ("Vigamox eye drops", "Moxifloxacillin", "0.50%"),
    930: ("Tab Thyroxine", "Levothyroxine", "25 mcg"),
    931: ("Syp Pulmosil", "Sildenafil", "10mg/ml"),
    932: ("Atarax syrup", "Hydroxyzine", "10 mg/5 ml"),
    933: ("Atarax drops", "Hydroxyzine", "6 mg/ml"),
    934: ("Xyzal syrup", "Levocetririzine", "2.5 mg/5 ml"),
    935: ("Xyzal Tablet", "Levoceterizine", "5 mg"),
    936: ("Xyzal tablet", "Levoceterizine", "10 mg"),
    937: ("Atarax anti-itch lotion", "Calamine 3%, Pramoxine HCL 1%", ""),
    938: ("Zyrtec drops", "Cetirizine", "10 mg/ml"),
    939: ("Zyrtec Syrup", "Cetirizine Hydrochloride", "1mg/ml"),
    940: ("Ascazin Syrup", "Elemental zinc", "10 mg/5ml"),
    941: ("ORSL plus", "Oral rehydration solution", ""),
    942: ("Ossopan D", "Calcium Phosphorus", "CA 125 mg/5 ml"),
    943: ("T Hisone 5", "Hydrocortisone", "5mg in 1 tablet"),
    944: ("Sporidex Drops", "Cephalexin", "100 mg/ml"),
    945: ("Electral sachet", "WHO ORS salt", "1sachet/200 ml water"),
    946: ("Caladryl Lotion", "Diphenhydramine/Calamine", ""),
    947: ("Montair LC Kid", "Monteleukast/Levocetirizine", "4 mg/2.5 mg/5 ml"),
    948: ("Omnacortil suspension", "Prednisolone", "5 mg/ 5 ml"),
    949: ("Budate Respule", "Budenoside", "0.5mg/2ml"),
    950: ("Jusdee 400 drops", "Cholecalciferol", "400 IU/ml"),
    951: ("Zanocin suspension 100", "Ofloxacin", "100 mg/5 ml"),
    952: ("Auxitrol", "Calcitrol", "0.25 mcg/capsule"),
    953: ("T. Inderal", "Propranolol", "10 mg"),
    954: ("Levipil Syrup", "Levetiracetam", "100 mg/ml"),
    955: ("Tonoferon", "", ""),
    956: ("D-Sol drops", "Cholecalciferol", "400 IU/ml"),
    957: ("Diaz syrup", "Elemental zinc", "20 mg/5 ml"),
    958: ("Proglicem Tablet", "Diazoxide", "25 mg tablet"),
    959: ("T. Hydrochlorothiazide", "T. Hydrochlorothiazide", "12.5 mg tablet"),
    960: ("Weltone Drops", "Multi-vitamins", ""),
    961: ("D3 Must Forte drops", "Cholecalciferol", "800 IU/ml"),
    962: ("Evion 400", "Vitamin E", "400 mg"),
    963: ("Meconerv-Z syp", "Multi vitamins", ""),
    964: ("Evion 200", "Tocopheryl Acetate", "200 mg capsule"),
    965: ("Laxopeg Kid", "Macrogol poly ethylene glycol 3350", ""),
    966: ("Asthalin Inhaler", "Salbutamol", "100 mcg per puff"),
    967: ("Ipravent Inhaler", "Ipratropium Bromide", "20 mcg/puff"),
    968: ("Cafirate", "Caffeine citrate", ""),
    969: ("Toba Eye drops", "Tobramycin", ""),
    970: ("Oflox Eye Drops", "Ofloxacillin", ""),
    971: ("Proglycem C", "Diazoxide", "25 mg cap"),
    972: ("Astymin C", "Amino acids & Vitamin C drops", "Drops"),
    973: ("NULL", "Piperacillin + Tazobactum", ""),
    974: ("NULL", "Amikacin", ""),
    975: ("NULL", "Piptazobactam", ""),
    976: ("NULL", "Fluconazole", ""),
    977: ("NULL", "Meropenem", ""),
    978: ("NULL", "Imipenem", ""),
    979: ("NULL", "Collistin", ""),
    980: ("NULL", "Cefotaxime", ""),
    981: ("NULL", "Amikacin", ""),
    982: ("NULL", "Vancomycin", ""),
    983: ("NULL", "Fluconozole", ""),
    984: ("NULL", "Amphotercin", ""),
    985: ("NULL", "piptazobactam", ""),
    986: ("NULL", "Amphotercin", ""),
    987: ("NULL", "vancomycin", ""),
    988: ("NULL", "Imipenem", ""),
    989: ("NULL", "Collistin", ""),
    990: ("NULL", "Vancomycin", ""),
    991: ("NULL", "Piptazobactan", ""),
    992: ("NULL", "Imipenam", ""),
    993: ("NULL", "Piptzobactam", ""),
    994: ("NULL", "Amkacin", ""),
    995: ("NULL", "Oflox ear drops", ""),
    996: ("NULL", "Amohotercin", ""),
    997: ("NULL", "Fluconzole", ""),
    998: ("NULL", "Aciclovir", ""),
    999: ("NULL", "Linezolid", ""),
    1000: ("NULL", "Cefipime + Sulbactum", ""),
    1001: ("NULL", "Ceftriaxone", ""),
    1002: ("NULL", "Tigecycline", ""),
    1003: ("NULL", "Ceftazidime", ""),
    1004: ("NULL", "Amoxycillin + Clavulanate", ""),
    1005: ("NULL", "Ciprofloxacin", ""),
    1006: ("NULL", "Ampicillin + Cloxacillin", ""),
    1007: ("NULL", "Metronidazole", ""),
    1008: ("NULL", "Azithromycin", ""),
    1009: ("NULL", "Netilmycin", ""),
    1010: ("NULL", "Gentamicin", ""),
    1011: ("Ibugesic suspension", "Ibuprofen", "100 mg/5 ml"),
    1012: ("Hicool eye ointment", "", ""),
    1013: ("Ipravent", "Ipratropium Bromide", "500 mcg/2 ml"),
    1014: ("Duphalac Syrup", "", ""),
    1015: ("Gardenal", "Phenobarbitone", "20 mg/5 ml"),
    1016: ("Tab Fluconazole", "Fluconazole", "50 mg"),
    1017: ("Vigamox eye drops", "Moxifloxacillin", "0.5%"),
    1018: ("Cafirate", "Caffeine Citrate", "20 mg/ml"),
    1019: ("Acuzone", "Cefoperazone Sulbactam", "1000/500"),
    1020: ("Calcimax P", "Calcium", "300 in 10ml"),
    1021: ("SYP ASTHALIN", "Salbutamol Sulphate", "2mg/5ml"),
    1022: ("Huff puff kit", "Asthalin", "1puff"),
    1023: ("Huff puff kit", "Budecort", "1puff"),
    1024: ("Zytee gel", "Benzalkonium", "Local application."),
    1025: ("Tab hydrea", "Hydroxy urea", "500mg"),
    1026: ("Syp Feronia XT", "Ferrous Ascorbate", "30mg/5 ml"),
    1028: ("ORS L", "Rehydration liquid", "WHO"),
    1029: ("calpol", "paracetamol", "650"),
    1030: ("Meropenem", "Meropenem", "500mg"),
    1031: ("Amikacin", "Amikacin", "500"),
    1032: ("T.Junior Lanzol", "Lanzoprazole", "15mg/ tab"),
    1033: ("syp.Sucrafil", "Sucralfate", "500mg"),
    1034: ("Syp.Microcef", "Cefixime", "100mg/5ml"),
    1035: ("Syp.Microcef", "Cefpodoxime", "100mg/5ml"),
    1036: ("Grenil", "Paracetamol/domeperidone", "500mg/10mg"),
    1037: ("Syr.Ventryl LS", "Levosalbutamol", "0.5 mg/5 ml"),
    1038: ("Phosome50", "Liposomal Amphotericin B", "50mg"),
    1039: ("Calosoft lotion", "Calamine", "local application"),
    1040: ("Telekast", "Montelukast", "5 mg"),
    1041: ("Telekast", "Montelukast", "5mg"),
    1042: ("Natclovir", "Ganciclovir", "500"),
    1043: ("omnacortil forte", "prednisolone", "15mg/5ml"),
    1044: ("Wyslone", "Prednisolone", "20"),
    1045: ("Wyslone", "prednisolone", "10"),
    1046: ("Syrup Potklor", "Potassium chloride", "15 ml/ 20 milli eqv"),
    1047: ("Syp potklor", "Potassium chloride oral solution", "15 ml / 20 meqv"),
    1048: ("WYSLONE 40", "PREDNISOLONE", "40"),
    1049: ("PANTOPRAZOLE 40", "Pantoprazole", "40"),
    1050: ("CEFIXIME", "Cefixime 100/5ml", "100/5ml"),
    1051: ("HHmite", "PERMETHRIN", "Topical"),
    1052: ("Meropenem", "Meropenem", "116mg BD"),
    1053: ("ASCABIOL", "LINDANE + CETRIMIDE", "L/A"),
    1054: ("BD 1cc syringe", "SYRINGE", "1cc"),
    1055: ("XONE", "Ceftriaxone", "IV"),
    1056: ("Syp. UDCA 1ml OD", "UDCA", "125mg/5ml"),
    1057: ("Cetaphil", "Moisturizing lotion", "Topical"),
    1058: ("Emeset", "Ondanseteron", "4mg"),
    1059: ("OFLOT 200", "OFLOXACIN", "200"),
    1060: ("ZENTE", "Albendzole", "400mg"),
    1061: ("ELECTRAL SACHET (1 SATCHET 1 LITER)", "WHO ORS", "1 SACHET IN 1 LITER WATER"),
    1062: ("ASTHALIN", "Salbutamol", "100mcg"),
    1063: ("DEXA", "Dexamethasone", "0.5cc"),
    1064: ("Dolo 650", "Paracetamol", "650mg/1tab"),
    1065: ("Baclofen Solution", "Baclofen", "5 mg/5ml"),
    1066: ("WYSOLONE 5", "Prednisolone", "5mg/tab"),
    1067: ("Deferasirox", "deferasirox", "250MG/5ML"),
    1068: ("Ofloxacin Ear drops", "Ofloxacin", "Eye drops"),
    1069: ("TONOFERON", "Iron+FA+ Vitamin B12", "250mg/5ml of elemental Iron"),
    1070: ("VIT A Gold", "VIT A", "5ml/50000IU"),
    1071: ("E CARE Drops", "VIT E drops", "1ml/50mg"),
    1072: ("Calcitriol", "Calcitriol", "0.25mcg"),
    1073: ("T. Montair Kid", "Monteleukast", "4 mg"),
    1076: ("Tablet Leucorin", "Calcium Leucovorin", "15 mg/Tablet"),
    1077: ("Metaspray", "MOMETASONE", "50mcg/puff"),
    1078: ("Azithral", "Azithromycin", "500mg/tab"),
    1079: ("Chymoral forte", "Trypsin Chymotrypsin", "100000AU"),
    1080: ("Calpol 500", "Paracetamol", "500/tab"),
    1081: ("BETADINE GARGLE", "Povidone", "5ml"),
    1082: ("ELECTRAL", "W.H.O ORS", "for 1 liter"),
    1083: ("Zanocin 200", "Ofloxacin", "200mg/tab"),
    1084: ("ZOVIRAX", "Acyclovir", "400mg/5ml"),
    1085: ("Pantop 20", "Pantoprazole", "20/tab"),
    1086: ("Protectis", "Probiotic - L Reuteri", "100 M"),
    1087: ("Ultra D3 800 drops", "Cholecalciferol", "800 IU/ml"),
    1088: ("A-Gold Syrup", "Vitamin A", "50,000 IU/5 ml"),
    1089: ("UDCAMENT", "Ursodeoxycholic acid", "125 mg/5ml"),
    1090: ("E-Care Drops", "Vitamin E drops", "50 mg/1ml"),
    1091: ("Valgan Tablets 450", "Valganciclovir", "450 mg/tablet"),
    1092: ("Balila Capsule", "Diazoxide", "25 mg/Tablet"),
    1093: ("Tab. Levipil 500", "Leviteracetam", "500/tab"),
    1094: ("IV set", "Iv set", "1"),
    1095: ("NS", "Normal Saline", "100ml/bottle"),
    1096: ("Inj.Levipil", "Leviteracetam", "1gram/vial"),
    1097: ("Venflon", "IV canulla", "1"),
    1098: ("Imicrit", "Imipenem", "."),
    1099: ("Gentamicin eye drops", "Gentamicin eye drops", "Drops"),
    1100: ("B-long", "Pyridoxine", "100mf"),
    1101: ("CREMAFFIN", "CREMAFFIN", "ML"),
    1102: ("hepatoglobine mikros", "Appetite", "ml"),
    1103: ("CYCLOPAM", "Dicyclomine (10mg) + Simethicone (40mg)", "10+40"),
    1104: ("Simyl MCT Oil", "Medium Chain Tryglycerides", "100 ml/94.5g fat"),
    1105: ("Riboflavin Tablet", "Riboflavin", "10 mg/ each tablet"),
    1106: ("Co Q", "Ubidecarenone (Coenzyme Q10)", "30 mg/ each capsule"),
    1107: ("Tonoferon drops", "Elemental Iron 25 mg", "25 mg/ml"),
    1108: ("Inj.Emeset", "Ondensetran", "8mg/2ml"),
    1109: ("Hypertonic saline", "3% normal saline", "3ml"),
    1110: ("Akair LC syp", "Monteleulakst", "5ml/5mg"),
    1111: ("Adrenaline neb", "Adrenaline", "3ml"),
    1112: ("Topcef tablet", "cefixime", "50mg/tab"),
    1113: ("Syp.Citralka", "Disodium sodium Citrate", "5ml"),
    1114: ("aspirin", "aspirin", "75/tab"),
    1115: ("Isoniazid", "Isoniazid", "300"),
    1116: ("Lidocaine Gel", "Lignocaine", "4%"),
    1117: ("Hydrocort", "Hydrocortisone", "1"),
    1118: ("Vitamin A gold", "vitamin A", "5ml/50000"),
    1119: ("Evion drops", "Vitamin E", "100IU"),
    1120: ("LAXOLITE", "Polyethylene glycol", "10gm/25 ml"),
    1121: ("DULCOLAX", "Bisacodyl", "pediatric 5mg"),
    1122: ("Fluconazole", "Fluconazole", "Injection"),
    1123: ("Sodium Chloride", "3% Sodium Chloride", "3%"),
    1124: ("T bact", "Mupirocin", "Oint"),
    1125: ("T-Bact ointment", "Mupirocin", "Ointment"),
    1126: ("Atarex", "Hydroxyzine", "25 mg"),
    1127: ("Tab Mox 250mg", "Amoxycillin", "250 MG"),
    1128: ("Tab ZYRTEC", "Cetrizine", "10mg"),
    1129: ("Tab Clavum", "Amoxycyllin and clavulunic acid", "500mg+ 125mg"),
    1130: ("Tazact", "Piperacillin and Tazobactum", "1.1"),
    1131: ("E-Care drops", "Vitamin E", "50mg/ml"),
    1132: ("Moxclav DS", "Amoxycillin/clavulanic acid.", "400mg/5ml"),
    1133: ("Noctoryl Syrup", "Melatonin", "3 mg/5 ml"),
    1134: ("Noctoryl Tablet", "Melatonin", "10 mg/1 tablet"),
    1135: ("BIFILAC", "BIFILAC", "1 SATCHET"),
    1136: ("Ibugesic plus", "Ibuprofen (100mg) + Paracetamol (162.5mg)", "Ibuprofen (100mg) + Paracetamol (162.5mg)"),
    1137: ("Wyslone", "Prednisolone", "20mg/tab"),
    1138: ("ZENTEL 400/10ML", "ALBENDAZOLE 400", "400/10ML"),
    1139: ("Augmentin", "Amoxicillin + Clauvnate", "625mg"),
    1140: ("Cremaffin Blue", "Cremaffin", "5"),
    1141: ("Syp Levipil", "Leviteracetam", "1ml/100mg"),
    1142: ("SYP MICROCEF 100", "CEFPODOXIME", "100MG/5ML"),
    1143: ("Mox syrup", "Amoxicilin", "250mg/5ml"),
    1144: ("Candid mouth paint", "Clotrimazole", "Clotrimazole and Glycerin 1%"),
    1145: ("Dextrose Bolus", "10% Dextrose", ""),
    1146: ("zincovit", "multivitamin", "tablet"),
    1147: ("longifene DS", "Buclizine", "syrup"),
    1148: ("Tamiflu", "Oseltamivir", "12mg/1ml"),
    1149: ("Ivepred 40", "Methylprednisolone sodium succinate", "40mg"),
    1150: ("Azee", "Azithromycin", "100mg/5ml"),
    1151: ("Spy. Azee", "Azithromycin", "100mg/5ml"),
    1152: ("TAMIFLU", "OSELTAMIVIR", "1ml/12mg"),
    1153: ("Hisone", "Hydrocortisone", "100mg"),
    1154: ("Decadron", "Dexamethasone", "8mg"),
    1155: ("Neovac", "Vecuronium", "1 ampoule/ 4 mg"),
    1156: ("Sildenafil", "Sildenafil", "10mg/12.5ml"),
    1157: ("Mezolam", "Midazolam", "1ml/ 5mg"),
    1161: ("BIOTIN", "BIOTIN", "10mg"),
    1162: ("B-LONG", "PYRIDOXINE", "100mg"),
    1163: ("B-LONG", "PYRIDOXINE", "100mg"),
    1164: ("Rumorf", "Morphine", "1ml/10mg"),
    1165: ("Daktarin cream", "Miconazole", "Topical"),
    1166: ("3% saline neb", "3% saline neb", "3ml"),
    1167: ("syruo Nootropil", "Piracetam", "5ml/500mg"),
    1168: ("Syrup Nootropil", "Piracetam", "5ml/500mg"),
    1169: ("Add phos", "Sodium phosphate", "500mg"),
    1170: ("Augpen", "Amoxycillin-clavulinic acid", "300"),
    1171: ("augpen", "amoxycillin clavulinic acid", "300mg"),
    1172: ("syrup azee", "azithromycin", "5ml/100mg"),
    1173: ("Neb Budecort", "Budesonide", "0.5mg/2ml"),
    1174: ("Inj. Solumedrol", "Methyl prednisolone", "125mg"),
    1175: ("Z & D DS 20", "Elemental Zinc", "1ml/20 mg"),
    1176: ("INJ.Neomol", "Paracetamol", "1ml/10mg"),
    1177: ("Inj.Neomol", "Paracetamol", "1ml/10mg"),
    1178: ("Inj.Neomol", "Paracetamol", "1ml/10mg"),
    1179: ("Caspledge", "Caspofungin Acetate", "50mg"),
    1180: ("Caspledge", "Caspofungin Acetate", "50mg"),
    1181: ("Limcee", "Vitamin C", "500mg"),
    1182: ("Z and D drops", "Zinc dry powder", "20mg"),
    1183: ("Sodium Benzoate", "Sodium Benzoate", ""),
    1184: ("L-Arginine", "Arginine", ""),
    1185: ("B-50", "B-Complex", "1 Cap/50 mg"),
    1186: ("DNS", "Dextrose Normal saline", "500ML"),
    1187: ("DNS", "DNS", "500"),
    1188: ("Depura", "Vitamin D3", "60000 IU / 5ml"),
    1189: ("Linezolid", "Linezolid", "100ml/200mg"),
    1190: ("Arachitol Kid", "Cholecalciferol", "400 IU/ml"),
    1191: ("T Kenadion", "Phytomenadione", "10 mg tablet"),
    1192: ("Thiamine", "Thiamine", "200mg"),
    1193: ("Thiamine", "Thiamine", "200mg"),
    1194: ("Timolet Drops", "Timolol Maleate", "0.5%"),
    1195: ("z and d drops", "z and d", "1ml/20mg"),
    1196: ("Zovirax ointment", "Aciclovir", "Ointment"),
    1197: ("Duolin Inhaler", "Ipratropium Bromide/Levosalbutamol", "20 mcg/50 mcg"),
    1198: ("Lopamide Tablet 2 mg", "Loperamide", "2 mg"),
    1199: ("Inj. Hisone", "Hydrocortisone", "100mg"),
    1200: ("Azee", "Azithromycin", "500mg"),
    1201: ("Half normal saline", "Half normal saline", "0.45% NACL"),
    1202: ("Ciprofloxacin", "Ciprofloxacin", "2mg/1ml"),
    1203: ("Ciprofloxacin", "Ciprofloxacin", "2mg/1ml"),
    1204: ("CIPRO", "Ciprofloxacin", "2mg"),
    1205: ("Atomist cream", "Moisturiser", "125"),
    1206: ("Mucinac 600", "N- acetyl cystine 600 mg", "1 tab/ 600 mg"),
    1207: ("Lizomac", "Linezolid", "100"),
    1208: ("Potklor", "Potassium chloride", "15ml / 20 meq"),
    1209: ("Magnex", "Cefoperazone sulbactum", "1gram"),
    1210: ("fosphenytoin", "fosphenytoin sodium", "500mg/10ml"),
    1211: ("Amox", "Amoxicillin", "1ml / 100mg"),
    1212: ("LEVIPIL", "LEVITIRACETAM", "100"),
    1213: ("Caspledge", "Caspofungin", "50"),
    1214: ("Bioprim Syrup", "Sulfamethoxazole and Trimethrprim", "200/40 in 5 ml"),
    1215: ("Syp Nodosis", "Sodium Bicarbonate", "1000 mg/15 ml"),
    1216: ("Ampicillin", "Ampicillin", "500"),
    1217: ("Syrup Meff", "Mefanamic acid", "100 mg/5 ml"),
    1218: ("Sun top D3 drops", "Vitamin D3", "400IU/ML"),
    1219: ("Desonide", "Desonide", "0.05%"),
    1220: ("benadon", "phyridoxine", "100mg"),
    1221: ("benadon", "phyridoxine", "100mg"),
    1222: ("benadon", "phyridoxine", "100mg"),
    1223: ("Cephalexin", "Cephalexin", "125 / 5 ml"),
    1224: ("MUCOMIX injection", "N-Acetyl cysteine", "20%"),
    1225: ("Hisone", "Hydrocortisone", "100mg"),
    1226: ("Immunoglobulin", "Immunoglobulin", "10%"),
    1227: ("Clexane", "Low molecular weight heparin", "40mg"),
    1228: ("At rapid", "Regular insulin", "40 units / ml"),
    1229: ("Actrapid", "Regular insulin", "40 units / ml"),
    1230: ("Fortacef", "Ceftazidime", "1 gram"),
    1231: ("Fortacef/ Ceftazidime", "Ceftazidime", "1 gram"),
    1232: ("Debamed", "Body lotion", "50 ml"),
    1233: ("Sebamed", "Body lotion", "50 ml"),
    1234: ("Fucidine", "Fusidic acid", "5g"),
    1235: ("Isocaldin Retort", "Isoniazid", "150/5ml"),
    1236: ("Albucel 5%", "Human Albumin 5% solution", "5gm/100ml"),
    1237: ("Vancomycin", "Vancomycin", "100"),
    1238: ("Apnicaf", "Caffine", "10 mg"),
    1239: ("Fungilip", "Liposomal amphotericin b", "100"),
    1240: ("50% dextrose", "50% dextrose", "50gm in 100ml"),
    1241: ("50% dextrose", "50% dextrose", "50gm in 100ml"),
    1242: ("solumedrol", "methyl prednisolone", "40 mg"),
    1243: ("25%D", "25% Dextrose", "25%"),
    1244: ("Voriconzole", "Voriconazole", "200mg/tab"),
    1245: ("Udiliv", "Ursodeoxycholic acid", "150"),
    1246: ("Rocaltrol", "Calcitriol", "25ng"),
    1247: ("Eltroxin", "Thyroxine", "37.5 mcg"),
    1248: ("Nextane", "Sodium hyaluronate", "0.1"),
    1249: ("CARNISURE INJECTION", "Levocarnitine", "1gm/5ml"),
    1250: ("25% dextrose", "25% dextrose", "25gm in 100ml"),
    1251: ("25% dextrose", "25% dextrose", "25gm in 100ml"),
    1252: ("25% dextrose", "25% dextrose", "25gm in 100ml"),
    1253: ("Enlapril", "Enalapril", "2.5 mg"),
    1254: ("THIAMINE", "THIAMINE", "100MG"),
    1255: ("TETRAFOL PLUS", "PYRIDOXAL PHOSPHATE", "25MG"),
    1256: ("Flohale", "Fluticasone Propionate", "0.5mg"),
    1257: ("Sporidex drops", "Cephalexin", "100mg/ml"),
    1258: ("Cryoprecipitate", "Cryoprecipitate", "Blood products"),
    1259: ("Cryoprecipitate", "Cryoprecipitate", "Blood products"),
    1260: ("Trifer Drops", "Hydroxide Polymaltose", "50 mg/1ml"),
    1261: ("Teicoplanin", "Teicoplanin", "20"),
    1262: ("Topiramate", "Topiramate", "25"),
    1263: ("Nevirapine", "Nevirapine", "5ml/50mg"),
    1264: ("Hperneb", "Hyperneb/ 3% Nacl", "1 respule"),
    1265: ("Augpen", "Amoxycillin clavulinic acid", "300mg"),
    1266: ("Duolin respules", "Duolin", "3ml/ 550mcg+ 1.25mg"),
    1267: ("Duolin respules", "Duolin respules", "3ml/ 500mcg+1.25mg"),
    1268: ("CoQ", "CoQ enzyme", "1"),
    1269: ("k-cit", "Potassium chloride", "1ml/2meq"),
    1270: ("Blong", "Phyridoxine", "100mcg"),
    1271: ("Tab. Sidenafil", "Tab. Sidenafil", "20mg"),
    1272: ("AZITHROMYCIN", "AZITHROMYCIN", "500MG"),
    1273: ("Azithromycin", "Azithromycin", "500mg"),
    1274: ("Micafung Plus", "Micafungin", "50mg"),
    1275: ("Moxigram", "Moxifloxacin", "5g"),
    1276: ("Folacin", "Oflaxacin", "0.3%"),
    1277: ("Folacin", "Ofloxacin", "0.3%"),
    1278: ("Aquablue", "Methylene blue", "1ml/ 10 mg"),
    1279: ("Aquablue", "Methylene blue", "1ml/ 10 mg"),
    1280: ("glucon", "glucagon", "1 mg"),
    1281: ("glucagen", "glucagon", "1 mg"),
    1282: ("Glucagon", "Glucagon", ""),
    1283: ("Refresh eye drops", "Methyl cellulose", "1 drops"),
    1284: ("Amphonex", "Liposomal Amphotericin", "50mg"),
    1285: ("Vasopressin", "Vasopressin", "1ml/20units"),
    1286: ("Eptoin", "Phenytoin", "1gm"),
    1287: ("Accuzon", "Ceftriaxone", "250"),
    1288: ("Metronidazole", "Metronidazole", "500"),
    1289: ("Half DNS", "1/2 DNS", "500ml"),
    1290: ("Half DNS", "1/2 DNS", "500ml"),
    1291: ("Ethambutol", "combutol", "400"),
    1292: ("T.Pyzina", "pyrazinamide", "500"),
    1293: ("T.R-CINEX KID", "Rifampicin 100 mg+ Isoniazid100", "100"),
    1294: ("Zentel", "Albendazole", "400mg/10ml"),
    1295: ("T Thyronorm", "Thyroxine", "12.5 mcg"),
    1296: ("Syp Nutrihale", "Ubidecarenone & Levocarnitine", "Ubidecarenone 30 mg and Levocarnitine 500 mg/10 ml"),
    1297: ("B long", "pyridoxine", "100 mg"),
    1298: ("Tab Ribofem 200", "Riboflavin", "200 mg/Tablet"),
    1299: ("Visyneral Zinc Syrup", "Multivitamins", "Syrup"),
    1300: ("Laxopeg Kid", "Poly Ethylene Glycol", "Macrogol 3350/13 g"),
    1301: ("Laxopeg Kid", "Poly Ethylene Glycol", "Macrogol 3350/13 g"),
}


# ============================================================================
# BUILD LOOKUP INDICES FOR FAST SEARCHING
# ============================================================================

def _normalize_drug_name(name: str) -> str:
    """Normalize drug name for matching."""
    if not name:
        return ""
    # Lowercase, remove extra spaces, remove common suffixes
    normalized = name.lower().strip()
    # Remove common prefixes like "inj.", "syp.", "tab.", etc.
    prefixes = ["inj.", "inj ", "syp.", "syp ", "syr.", "syr ", "tab.", "tab ", "t.", "t "]
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
    return normalized


def _build_drug_index() -> Dict[str, int]:
    """Build a normalized lookup index from drug names to IDs."""
    index = {}
    for drug_id, (brand_name, generic_name, value) in DRUG_DATABASE.items():
        # Index by brand name
        if brand_name and brand_name != "NULL":
            normalized = _normalize_drug_name(brand_name)
            if normalized and normalized not in index:
                index[normalized] = drug_id

        # Index by generic name
        if generic_name and generic_name != "N/A":
            normalized = _normalize_drug_name(generic_name)
            if normalized and normalized not in index:
                index[normalized] = drug_id

    return index


# Build the index at module load time
DRUG_NAME_INDEX = _build_drug_index()


# ============================================================================
# PUBLIC LOOKUP FUNCTIONS
# ============================================================================

def lookup_drug_id(drug_name: str) -> Optional[int]:
    """
    Look up the Raster drugId for a given drug name.

    Args:
        drug_name: Drug name (brand or generic) extracted from audio

    Returns:
        The Raster drugId if found, None otherwise
    """
    if not drug_name:
        return None

    normalized = _normalize_drug_name(drug_name)

    # Direct match only — no loose substring matching
    if normalized in DRUG_NAME_INDEX:
        return DRUG_NAME_INDEX[normalized]

    return None


def lookup_drug_id_with_fallback(drug_name: str, fallback_id: int = 1) -> int:
    """
    Look up the Raster drugId with a fallback value.

    Args:
        drug_name: Drug name (brand or generic) extracted from audio
        fallback_id: ID to return if no match found (default: 1 for Dopamine)

    Returns:
        The Raster drugId if found, otherwise the fallback_id
    """
    result = lookup_drug_id(drug_name)
    return result if result is not None else fallback_id


def get_drug_info(drug_id: int) -> Optional[Tuple[str, str, str]]:
    """
    Get drug information by ID.

    Args:
        drug_id: The Raster drugId

    Returns:
        Tuple of (brand_name, generic_name, value) or None if not found
    """
    return DRUG_DATABASE.get(drug_id)


def search_drugs(query: str, limit: int = 10) -> List[Tuple[int, str, str]]:
    """
    Search for drugs matching a query.

    Args:
        query: Search query (partial name match)
        limit: Maximum number of results

    Returns:
        List of (drug_id, brand_name, generic_name) tuples
    """
    if not query:
        return []

    query_lower = query.lower()
    results = []

    for drug_id, (brand_name, generic_name, value) in DRUG_DATABASE.items():
        brand_lower = brand_name.lower() if brand_name else ""
        generic_lower = generic_name.lower() if generic_name else ""

        if query_lower in brand_lower or query_lower in generic_lower:
            results.append((drug_id, brand_name, generic_name))
            if len(results) >= limit:
                break

    return results


# ============================================================================
# COMMON DRUG ALIASES FOR FUZZY MATCHING
# ============================================================================

DRUG_ALIASES: Dict[str, str] = {
    # Common abbreviations
    "pcm": "paracetamol",
    "para": "paracetamol",
    "ceftri": "ceftriaxone",
    "amox": "amoxicillin",
    "amoxy": "amoxicillin",
    "aug": "augmentin",
    "metro": "metronidazole",
    "genta": "gentamicin",
    "vanco": "vancomycin",
    "mero": "meropenem",
    "piptaz": "piperacillin tazobactam",
    "pip-taz": "piperacillin tazobactam",
    "amika": "amikacin",
    "levo": "levetiracetam",
    "phenobarb": "phenobarbitone",
    "pheno": "phenobarbitone",
    "midaz": "midazolam",
    "dex": "dexamethasone",
    "pred": "prednisolone",
    "hydro": "hydrocortisone",
    "furo": "furosemide",
    "lasix": "furosemide",
    "salbut": "salbutamol",
    "budecort": "budesonide",
    "bude": "budesonide",
    "ns": "normal saline",
    "dns": "dextrose normal saline",
    "rl": "ringer lactate",
    "d5": "5% dextrose",
    "d10": "10% dextrose",
    "d25": "25% dextrose",
    "prbc": "packed red blood cells",
    "ffp": "fresh frozen plasma",
    "ivig": "immunoglobulin",
    "vit k": "vitamin k",
    "vit d": "vitamin d",
    "vit e": "vitamin e",
    "vit a": "vitamin a",
}


def resolve_drug_alias(drug_name: str) -> str:
    """
    Resolve common drug aliases to their standard names.

    Args:
        drug_name: Drug name or alias

    Returns:
        Resolved drug name
    """
    if not drug_name:
        return drug_name

    normalized = drug_name.lower().strip()
    return DRUG_ALIASES.get(normalized, drug_name)


# ============================================================================
# FUZZY MATCHING FUNCTIONS
# ============================================================================

def calculate_similarity(s1: str, s2: str) -> float:
    """
    Calculate similarity ratio between two strings using SequenceMatcher.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Similarity ratio (0.0 to 1.0)
    """
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def find_closest_drug_match(drug_name: str, threshold: float = 0.75) -> Optional[Tuple[int, str, float]]:
    """
    Find the closest matching drug if similarity exceeds threshold.

    Args:
        drug_name: Drug name to search for
        threshold: Minimum similarity score (default: 0.90 = 90%)

    Returns:
        Tuple of (drug_id, matched_name, similarity_score) if match found, None otherwise
    """
    if not drug_name:
        return None

    normalized = _normalize_drug_name(drug_name)
    best_match = None
    best_score = 0.0

    # Search through all indexed drug names
    for indexed_name, drug_id in DRUG_NAME_INDEX.items():
        score = calculate_similarity(normalized, indexed_name)
        if score > best_score:
            best_score = score
            best_match = (drug_id, indexed_name, score)

    # Also search through generic names in the database
    for drug_id, (brand_name, generic_name, _) in DRUG_DATABASE.items():
        for name in [brand_name, generic_name]:
            if name:
                score = calculate_similarity(normalized, name.lower())
                if score > best_score:
                    best_score = score
                    best_match = (drug_id, name, score)

    if best_match and best_score >= threshold:
        return best_match

    # Log best match even if below threshold for debugging
    if best_match:
        logger.debug(f"[DRUG_LOOKUP] Best fuzzy match for '{drug_name}': '{best_match[1]}' ({best_match[2]:.1%}) - below {threshold:.0%} threshold")
        logger.info(f"[DRUG_LOOKUP] No fuzzy match for '{drug_name}' (best: '{best_match[1]}' at {best_match[2]:.1%}, threshold: {threshold:.0%})")

    return None


def lookup_drug_id_fuzzy(drug_name: str) -> Optional[int]:
    """
    Look up drug ID with fuzzy matching including alias resolution.

    Args:
        drug_name: Drug name, alias, or abbreviation

    Returns:
        The Raster drugId if found, None otherwise
    """
    if not drug_name:
        return None

    # First try direct lookup
    result = lookup_drug_id(drug_name)
    if result is not None:
        return result

    # Try alias resolution
    resolved = resolve_drug_alias(drug_name)
    if resolved != drug_name:
        result = lookup_drug_id(resolved)
        if result is not None:
            return result

    # Try fuzzy matching with 85% threshold as final fallback
    fuzzy_match = find_closest_drug_match(drug_name, threshold=0.85)
    if fuzzy_match:
        drug_id, matched_name, score = fuzzy_match
        logger.info(f"[DRUG_LOOKUP] Fuzzy match: '{drug_name}' -> '{matched_name}' (score: {score:.1%})")
        return drug_id

    return None
