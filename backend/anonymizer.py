import logging
import re
import os
from typing import Dict, Tuple, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

SKIP_WORDS = {"Aadhaar", "Aadhar", "GSTIN"}

'''
SKIP_WORDS = {
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December", "Jan", "Feb", "Mar", "Apr",
    "Mr", "Mrs", "Ms", "Dr", "Prof", "Sir", "Madam",
    "The", "This", "That", "These", "Those", "There", "Their", "They", "Then", "Than",
    "From", "For", "With", "Will", "Would", "Could", "Should", "About", "After", "Before",
    "Total", "Grand", "Sub", "Net", "Amount", "Value", "Price", "Cost", "Date", "Name",
    "Email", "Phone", "Address", "City", "State", "Country", "Status", "ID", "Number",
    "Qty", "Quantity", "Rate", "Discount", "Tax", "Payment", "Notes", "Description",
    "Product", "Service", "Item", "Order", "Invoice", "Account", "Company", "Contact",
    "Region", "Zone", "Type", "Category", "Department", "Team", "Manager", "Report",
    "Summary", "Detail", "Info", "Information", "Remarks", "Comment", "Balance",
    "Financial", "Data", "Analysis", "Overview", "Review", "Update", "Progress",
    "Yes", "No", "Not", "And", "But", "Are", "Was", "Were", "Has", "Had", "Have",
    "Get", "Got", "See", "Saw", "Now", "New", "Old", "All", "Each", "Every", "Both",
    "Few", "More", "Most", "Other", "Some", "Such", "Only", "Own", "Same",
    "Dear", "Hello", "Hi", "Please", "Thanks", "Thank", "Regards", "Best", "Good",
    "India", "US", "UK", "USA", "China", "Japan", "Germany", "France", "Canada",
    "Australia", "Brazil", "Russia", "Italy", "Spain", "Mexico", "Korea", "Asia",
    "Europe", "Africa", "America", "North", "South", "East", "West",
    "Ltd", "Inc", "Corp", "LLC", "Pvt", "Private", "Limited", "Corporation",
    "Solutions", "Services", "Technologies", "Systems", "Technologies",
}
'''

class Anonymizer:
    def __init__(self):
        self.nlp = None
        self.nlp_spacy = None

    def load_gliner(self):
        if self.nlp is None:
            logger.info("Loading GLiNER NER model (gliner_medium-v2.1)...")
            from gliner import GLiNER
            kwargs = {"local_files_only": True} if os.environ.get("HF_HUB_OFFLINE") == "1" else {"cache_dir": MODEL_DIR}
            self.nlp = GLiNER.from_pretrained("urchade/gliner_medium-v2.1", **kwargs)
            logger.info("GLiNER NER model ready!")

    def load_spacy(self):
        if self.nlp_spacy is None:
            import spacy
            for model in ["en_core_web_lg", "en_core_web_sm"]:
                try:
                    self.nlp_spacy = spacy.load(model)
                    logger.info("spaCy NER model ready! (%s)", model)
                    return
                except OSError:
                    continue
            logger.warning("No spaCy model found (en_core_web_lg or en_core_web_sm). Install with: python -m spacy download en_core_web_sm")
            self.nlp_spacy = None

    def _is_skip_entity(self, text: str) -> bool:
        if len(text) < 3:
            return True
        if text in SKIP_WORDS:
            return True
        if text.lower() in {w.lower() for w in SKIP_WORDS}:
            return True
        if text.isdigit():
            return True
        if all(c.isdigit() or c in '.-,' for c in text):
            return True
        return False

    def extract_entities(self, text: str, entity_types: Dict[str, bool] = None) -> Dict[str, str]:
        self.load_gliner()
        self.load_spacy()

        entity_map = {}
        entity_counters = {"PERSON": 1, "ORG": 1, "LOC": 1, "ID": 1}
        seen_entities = set()

        # Step 1: structured ID detection — runs before NER so patterns like PAN,
        # GST, CIN, Aadhaar are claimed first (GLiNER misclassifies them otherwise).
        id_patterns = [
            ("PAN", r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'),
            ("GST", r'\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b'),
            ("CIN", r'\b[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}\b'),
            ("Aadhaar", r'\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b'),
            ("RegistrationNo", r'(?:Regn?|Registration|Reg\.?)\s*(?:No|Number|#)[\s:.-]*[A-Z0-9][A-Z0-9/\-]+'),
        ]
        for label, pattern in id_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entity_text = match.group().strip()
                if entity_text in seen_entities:
                    continue
                placeholder = f"ID_{entity_counters['ID']}"
                entity_counters['ID'] += 1
                entity_map[placeholder] = entity_text
                seen_entities.add(entity_text)

        # Step 2: GLiNER (primary NER)
        if self.nlp is not None:
            labels = ["Person", "Organization", "Location"]
            label_map = {"Person": "PERSON", "Organization": "ORG", "Location": "LOC"}
            gliner_entities = self.nlp.predict_entities(text, labels, threshold=0.3)

            for ent in gliner_entities:
                entity_text = ent["text"].strip()
                gliner_label = ent["label"]

                if self._is_skip_entity(entity_text):
                    continue
                if entity_text in seen_entities:
                    continue

                internal_label = label_map.get(gliner_label)
                if internal_label == "PERSON":
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1
                elif internal_label == "ORG":
                    if len(entity_text) < 4:
                        continue
                    placeholder = f"ORG_{entity_counters['ORG']}"
                    entity_counters['ORG'] += 1
                elif internal_label == "LOC":
                    placeholder = f"LOC_{entity_counters['LOC']}"
                    entity_counters['LOC'] += 1
                else:
                    continue

                entity_map[placeholder] = entity_text
                seen_entities.add(entity_text)

        # Step 3: spaCy (fallback NER)
        if self.nlp_spacy is not None:
            processed = text.replace('\n', '. ')
            doc = self.nlp_spacy(processed)
            spacy_label_map = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "LOC"}

            for ent in doc.ents:
                entity_text = ent.text.strip()
                spacy_label = ent.label_

                if self._is_skip_entity(entity_text):
                    continue
                if entity_text in seen_entities:
                    continue

                internal_label = spacy_label_map.get(spacy_label)
                if internal_label == "PERSON":
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1
                elif internal_label == "ORG":
                    if len(entity_text) < 4:
                        continue
                    placeholder = f"ORG_{entity_counters['ORG']}"
                    entity_counters['ORG'] += 1
                elif internal_label == "LOC":
                    placeholder = f"LOC_{entity_counters['LOC']}"
                    entity_counters['LOC'] += 1
                else:
                    continue

                entity_map[placeholder] = entity_text
                seen_entities.add(entity_text)

        # Step 4: company keyword fallback
        company_keywords = ['Private', 'Limited', 'Ltd', 'Inc', 'LLC', 'Corp', 'Corporation', 'Company', 'Solutions', 'Services', 'Technologies', 'Tech', 'Systems', 'Group', 'Holdings', 'Enterprises', 'Industries', 'Consulting', 'Partners', 'Associates', 'International', 'Global', 'India', 'Pvt', 'Vryno']

        for line in text.split('\n'):
            line = line.strip()
            if len(line) < 5:
                continue
            company_pattern = re.compile(r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})')
            for match in company_pattern.finditer(line):
                candidate = match.group(1)
                if candidate in seen_entities:
                    continue
                if any(kw in candidate for kw in company_keywords):
                    parts = candidate.split()
                    if len(parts) >= 2:
                        placeholder = f"ORG_{entity_counters['ORG']}"
                        entity_counters['ORG'] += 1
                        entity_map[placeholder] = candidate
                        seen_entities.add(candidate)

        # Step 5: address segments — extract a short window after address keywords
        # rather than capturing the entire line (which may contain other entities).
        address_markers = r'(?:address|addr|office|works\s+at|located\s+at|residence|branch|registered\s+office|correspondence)'
        for line in text.split('\n'):
            line_str = line.strip()
            if len(line_str) < 10:
                continue
            match = re.search(address_markers, line_str, re.IGNORECASE)
            if not match:
                continue
            words = line_str[match.start():].split()
            snippet = ' '.join(words[:10]).strip()
            if len(snippet) < 8:
                continue
            if snippet in seen_entities:
                continue
            placeholder = f"LOC_{entity_counters['LOC']}"
            entity_counters['LOC'] += 1
            entity_map[placeholder] = snippet
            seen_entities.add(snippet)

        if entity_types:
            prefix_map = {"PERSON": "PERSON", "ORG": "ORG", "LOC": "LOC", "ID": "ID"}
            entity_map = {
                k: v for k, v in entity_map.items()
                if entity_types.get(prefix_map.get(k.split("_")[0], ""), True)
            }

        return entity_map

    def extract_entities_from_values(self, cell_values: List[str]) -> Dict[str, str]:
        self.load_gliner()
        self.load_spacy()

        entity_map = {}
        entity_counters = {"PERSON": 1, "ORG": 1, "LOC": 1}
        seen_entities = set()

        # Step 1: GLiNER (primary)
        labels = ["Person", "Organization", "Location"]
        label_map = {"Person": "PERSON", "Organization": "ORG", "Location": "LOC"}

        for cell_value in cell_values:
            if not cell_value or not isinstance(cell_value, str):
                continue
            cell_value = cell_value.strip()
            if len(cell_value) < 3:
                continue

            entities = self.nlp.predict_entities(cell_value, labels, threshold=0.3)

            for ent in entities:
                entity_text = ent["text"].strip()
                gliner_label = ent["label"]

                if self._is_skip_entity(entity_text):
                    continue
                if entity_text in seen_entities:
                    continue

                internal_label = label_map.get(gliner_label)
                if internal_label == "PERSON":
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1
                elif internal_label == "ORG":
                    if len(entity_text) < 4:
                        continue
                    placeholder = f"ORG_{entity_counters['ORG']}"
                    entity_counters['ORG'] += 1
                elif internal_label == "LOC":
                    placeholder = f"LOC_{entity_counters['LOC']}"
                    entity_counters['LOC'] += 1
                else:
                    continue

                entity_map[placeholder] = entity_text
                seen_entities.add(entity_text)

        # Step 2: spaCy (fallback)
        spacy_label_map = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "LOC"}

        for cell_value in cell_values:
            if not cell_value or not isinstance(cell_value, str):
                continue
            cell_value = cell_value.strip()
            if len(cell_value) < 3:
                continue

            doc = self.nlp_spacy(cell_value)

            for ent in doc.ents:
                entity_text = ent.text.strip()
                spacy_label = ent.label_

                if self._is_skip_entity(entity_text):
                    continue
                if entity_text in seen_entities:
                    continue

                internal_label = spacy_label_map.get(spacy_label)
                if internal_label == "PERSON":
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1
                elif internal_label == "ORG":
                    if len(entity_text) < 4:
                        continue
                    placeholder = f"ORG_{entity_counters['ORG']}"
                    entity_counters['ORG'] += 1
                elif internal_label == "LOC":
                    placeholder = f"LOC_{entity_counters['LOC']}"
                    entity_counters['LOC'] += 1
                else:
                    continue

                entity_map[placeholder] = entity_text
                seen_entities.add(entity_text)

        company_keywords = ['Private', 'Limited', 'Ltd', 'Inc', 'LLC', 'Corp', 'Corporation', 'Company', 'Solutions', 'Services', 'Technologies', 'Tech', 'Systems', 'Group', 'Holdings', 'Enterprises', 'Industries', 'Consulting', 'Partners', 'Associates', 'International', 'Global', 'India', 'Pvt', 'Vryno']

        for val in cell_values:
            if not val or not isinstance(val, str):
                continue
            val = val.strip()
            if len(val) < 5:
                continue
            company_pattern = re.compile(r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})')
            for match in company_pattern.finditer(val):
                candidate = match.group(1)
                if candidate in seen_entities:
                    continue
                if any(kw in candidate for kw in company_keywords):
                    parts = candidate.split()
                    if len(parts) >= 2:
                        placeholder = f"ORG_{entity_counters['ORG']}"
                        entity_counters['ORG'] += 1
                        entity_map[placeholder] = candidate
                        seen_entities.add(candidate)

        filtered_map = {}
        for placeholder, txt in entity_map.items():
            is_substring = False
            for other_text in seen_entities:
                if other_text != txt and txt in other_text:
                    is_substring = True
                    break
            if not is_substring:
                filtered_map[placeholder] = txt

        return filtered_map

    def anonymize(self, text: str, multiplier: float, entity_types: Dict[str, bool]) -> Tuple[Dict[str, str], str, Dict[str, Any]]:
        entity_map = self.extract_entities(text, entity_types)

        result_text = text
        sorted_entities = sorted(entity_map.items(), key=lambda x: len(x[1]), reverse=True)
        for placeholder, original in sorted_entities:
            if original in result_text:
                result_text = result_text.replace(original, placeholder)

        stats = {
            "persons": sum(1 for k in entity_map.keys() if k.startswith("PERSON_")),
            "orgs": sum(1 for k in entity_map.keys() if k.startswith("ORG_")),
            "locs": sum(1 for k in entity_map.keys() if k.startswith("LOC_")),
            "ids": sum(1 for k in entity_map.keys() if k.startswith("ID_")),
        }

        logger.info("NER detected: %d persons, %d orgs, %d locations, %d IDs", stats['persons'], stats['orgs'], stats['locs'], stats['ids'])
        
        if entity_map and logger.isEnabledFor(logging.DEBUG):
            logger.debug("Entity mappings:")
            for p, v in entity_map.items():
                logger.debug("  %s -> %s", p, v)

        return entity_map, result_text, stats

    def create_bridge_key(self, original_filename: str, entity_map: Dict[str, str], multiplier: float) -> Dict[str, Any]:
        return {
            "app": "Anon Bridge",
            "version": "2.0",
            "multiplier": multiplier,
            "created_at": datetime.now().isoformat(),
            "original_filename": original_filename,
            "entities": entity_map,
        }


def create_anonymizer() -> Anonymizer:
    return Anonymizer()
