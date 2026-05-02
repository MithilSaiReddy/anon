import re
import os
from typing import Dict, Tuple, List, Any
from datetime import datetime

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

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


class Anonymizer:
    def __init__(self):
        self.nlp = None

    def load_spacy(self):
        if self.nlp is None:
            print("Loading spaCy NER model (en_core_web_lg)...")
            import spacy
            self.nlp = spacy.load("en_core_web_lg")
            print("spaCy NER model ready!")

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

    def extract_entities(self, text: str) -> Dict[str, str]:
        self.load_spacy()

        entity_map = {}
        entity_counters = {"PERSON": 1, "ORG": 1, "LOC": 1}
        seen_entities = set()

        processed = text.replace('\n', '. ')
        doc = self.nlp(processed)

        for ent in doc.ents:
            entity_text = ent.text.strip()

            if self._is_skip_entity(entity_text):
                continue
            if entity_text in seen_entities:
                continue

            if ent.label_ == "PERSON":
                parts = entity_text.split()
                if len(parts) == 1 and len(entity_text) < 4:
                    continue
                placeholder = f"PERSON_{entity_counters['PERSON']}"
                entity_counters['PERSON'] += 1

            elif ent.label_ == "ORG":
                if len(entity_text) < 4:
                    continue
                placeholder = f"ORG_{entity_counters['ORG']}"
                entity_counters['ORG'] += 1

            elif ent.label_ == "GPE":
                placeholder = f"LOC_{entity_counters['LOC']}"
                entity_counters['LOC'] += 1

            else:
                continue

            entity_map[placeholder] = entity_text
            seen_entities.add(entity_text)

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

        filtered_map = {}
        for placeholder, text in entity_map.items():
            is_substring = False
            for other_text in seen_entities:
                if other_text != text and text in other_text:
                    is_substring = True
                    break
            if not is_substring:
                filtered_map[placeholder] = text

        return filtered_map

    def extract_entities_from_values(self, cell_values: List[str]) -> Dict[str, str]:
        self.load_spacy()

        entity_map = {}
        entity_counters = {"PERSON": 1, "ORG": 1, "LOC": 1}
        seen_entities = set()

        for cell_value in cell_values:
            if not cell_value or not isinstance(cell_value, str):
                continue
            cell_value = cell_value.strip()
            if len(cell_value) < 3:
                continue

            doc = self.nlp(cell_value)

            for ent in doc.ents:
                entity_text = ent.text.strip()

                if self._is_skip_entity(entity_text):
                    continue
                if entity_text in seen_entities:
                    continue

                if ent.label_ == "PERSON":
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1

                elif ent.label_ == "ORG":
                    if len(entity_text) < 4:
                        continue
                    placeholder = f"ORG_{entity_counters['ORG']}"
                    entity_counters['ORG'] += 1

                elif ent.label_ == "GPE":
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
        entity_map = self.extract_entities(text)

        result_text = text
        sorted_entities = sorted(entity_map.items(), key=lambda x: len(x[1]), reverse=True)
        for placeholder, original in sorted_entities:
            if original in result_text:
                result_text = result_text.replace(original, placeholder)

        stats = {
            "persons": sum(1 for k in entity_map.keys() if k.startswith("PERSON_")),
            "orgs": sum(1 for k in entity_map.keys() if k.startswith("ORG_")),
            "locs": sum(1 for k in entity_map.keys() if k.startswith("LOC_")),
        }

        print(f"NER detected: {stats['persons']} persons, {stats['orgs']} orgs, {stats['locs']} locations")
        for p, v in sorted(entity_map.items()):
            print(f"  {p} -> {v}")

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
