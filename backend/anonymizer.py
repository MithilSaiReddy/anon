import logging
import re
import os
from typing import Dict, Tuple, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

SKIP_WORDS = {"Aadhaar", "Aadhar", "GSTIN"}

# Common English / domain words that should never be treated as entities when
# they appear as a single token (e.g. "Gross", "Code", "Act", "Employer",
# "Provided"). Multitoken phrases are handled separately by LEGAL_TITLE_MARKERS.
COMMON_WORDS = {
    # Weekdays / months
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "jan", "feb", "mar", "apr",
    # Honorifics
    "mr", "mrs", "ms", "dr", "prof", "sir", "madam", "st", "sr", "jr",
    # Articles / pronouns / function words
    "the", "this", "that", "these", "those", "there", "their", "they", "then", "than",
    "from", "for", "with", "will", "would", "could", "should", "about", "after", "before",
    "and", "but", "are", "was", "were", "has", "had", "have", "get", "got", "see", "saw",
    "now", "new", "old", "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "only", "own", "same", "not", "no", "yes", "upon", "within",
    "also", "may", "shall", "can", "must", "whose", "which", "where", "when", "whether",
    # Generic document / form words
    "total", "grand", "sub", "net", "amount", "value", "price", "cost", "date", "name",
    "email", "phone", "address", "city", "state", "country", "status", "id", "number",
    "qty", "quantity", "rate", "discount", "tax", "payment", "notes", "description",
    "product", "service", "item", "order", "invoice", "account", "company", "contact",
    "region", "zone", "type", "category", "department", "team", "manager", "report",
    "summary", "detail", "info", "information", "remarks", "comment", "balance",
    "financial", "data", "analysis", "overview", "review", "update", "progress",
    # Correspondence
    "dear", "hello", "hi", "please", "thanks", "thank", "regards", "best", "good",
    # Labour / legal / tax domain terms
    "act", "code", "rules", "regulation", "regulations", "section", "chapter",
    "clause", "schedule", "rule", "provided", "subject", "gross", "wages",
    "salary", "employer", "employee", "worker", "contribution", "income", "bonus",
    "deduction", "deductions", "executive", "director", "manager", "welfare", "cess",
    "period", "payment", "remuneration", "compensation", "gratuity", "pension",
    "insurance", "provident", "fund", "employment", "establishment", "workman",
    "workmen", "industrial", "labour", "labor", "dispute", "conciliation", "arbitration",
    "adjudication", "inspection", "inspector", "register", "records", "procedure",
    "penalty", "penalties", "offence", "offense", "fine", "amendment", "ordinance",
    "bill", "notification", "scheme", "policy", "provision", "provisions", "appeal",
    "complaint", "suit", "contract", "agreement", "settlement", "negotiation",
    "average", "basic", "dearness", "house", "rent", "conveyance", "allowance",
    "overtime", "hours", "shift", "week", "month", "year", "annual", "monthly",
    "daily", "weekly", "leave", "holiday", "attendance", "absenteeism", "retrenchment",
    "closure", "layoff", "transfer", "promotion", "demotion", "warning", "notice",
    "suspension", "dismissal", "termination", "resignation", "retirement",
    # Countries / continents / broad geography (kept as common words; specific
    # street names, cities, etc. are still detected via other stages)
    "india", "us", "uk", "usa", "china", "japan", "germany", "france", "canada",
    "australia", "brazil", "russia", "italy", "spain", "mexico", "korea", "asia",
    "europe", "africa", "america", "north", "south", "east", "west", "central",
    "international", "global", "national", "state", "union", "central", "federal",
    # Generic corporate tokens (used single-handedly they are not entities)
    "ltd", "inc", "corp", "llc", "pvt", "private", "limited", "corporation",
    "solutions", "services", "technologies", "systems", "tech", "group", "holdings",
    "enterprises", "industries", "consulting", "partners", "associates", "company",
    "trade", "commerce", "bank", "centre", "center",
}

# Whole-word markers that indicate a legislative / statutory document title
# rather than an organization.
LEGAL_TITLE_MARKERS = {
    "act", "code", "rules", "regulation", "regulations", "ordinance", "bill",
    "chapter", "section", "schedule", "notification", "amendment", "bye-law",
    "byelaw",
}

# Tokens that only appear attached to genuine company names (strong suffix).
STRONG_COMPANY_SUFFIX = {
    "Ltd", "Inc", "Corp", "LLC", "Pvt", "Limited", "Corporation", "LLP",
    "Co", "Group", "Holdings",
}

# Tokens that virtually only ever occur inside real incorporated entities
# (e.g. "Acme Corp Ltd", "Tech Solutions Inc").
INCORPORATION_TOKENS = {"Ltd", "LLC", "Pvt", "Inc", "LLP", "Co"}

# Softer corporate tokens — still strong signals, but only accepted when the
# candidate contains at least one genuinely non-common word.
SOFT_COMPANY_SUFFIX = {"Corp", "Corporation", "Limited", "Company", "Group", "Holdings"}

MEDIUM_COMPANY_KEYWORDS = {
    "Solutions", "Services", "Technologies", "Systems", "Tech", "Enterprises",
    "Industries", "Consulting", "Partners", "Associates", "International",
    "Global", "Labs", "Digital", "Software", "Infotech",
}

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

    @staticmethod
    def _is_single_common_word(text: str) -> bool:
        """True when *text* is a single ordinary English/domain word.

        Used to reject single-token PERSON/ORG false positives like
        "Gross", "Code", "Act", "Employer", "Provided".
        """
        if not text or len(text) < 3:
            return True
        if any(c.isspace() for c in text):
            return False
        return text.lower() in COMMON_WORDS

    @classmethod
    def _is_legal_doc_title(cls, text: str) -> bool:
        """True when *text* looks like a legislative document title
        ("The Code on Social Security, 2020", "Payment of Wages Act") rather
        than an organization. Real companies ending in a strong suffix
        (e.g. "Acme Corporation") are not vetoed.
        """
        if not text:
            return False
        words = text.split()
        if not words:
            return False
        last = words[-1].rstrip(",.").lower()
        if last in {s.lower() for s in STRONG_COMPANY_SUFFIX}:
            return False
        lowered = " " + text.lower() + " "
        return any(
            re.search(rf"\b{re.escape(marker)}\b", lowered)
            for marker in LEGAL_TITLE_MARKERS
        )

    @classmethod
    def _looks_like_statutory_fragment(cls, org_text: str, document_text: str) -> bool:
        """True when a multi-word ORG candidate is just a fragment of a
        statutory document title, e.g. "Social Security" inside
        "The Code on Social Security, 2020". Real companies (which carry an
        incorporation / corporate suffix) are exempt, and there must be a low
        word-distance between the candidate and a legal-title marker so a real
        organization merely mentioned in the same sentence as an Act (e.g.
        "State Bank of India ... Banking Regulation Act") is preserved.
        """
        words = org_text.split()
        if len(words) < 2:
            return False
        clean_lower = {w.strip(",.").lower() for w in words if w.strip(".,")}
        corporate = (
            {s.lower() for s in INCORPORATION_TOKENS}
            | {s.lower() for s in SOFT_COMPANY_SUFFIX}
            | {s.lower() for s in MEDIUM_COMPANY_KEYWORDS}
        )
        if clean_lower & corporate:
            return False
        org_lower = org_text.lower()
        for line in document_text.split("\n"):
            low = line.lower()
            pos = low.find(org_lower)
            if pos == -1:
                continue
            line_words = line.split()
            org_first_idx = len(line[:pos].split())
            marker_indices = [
                idx for idx, w in enumerate(line_words)
                if w.strip(".,;:()").lower() in LEGAL_TITLE_MARKERS
            ]
            if any(abs(mi - org_first_idx) <= 6 for mi in marker_indices):
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
                    if self._is_single_common_word(entity_text):
                        continue
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1
                elif internal_label == "ORG":
                    if self._is_single_common_word(entity_text):
                        continue
                    if self._is_legal_doc_title(entity_text):
                        continue
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
                    if self._is_single_common_word(entity_text):
                        continue
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1
                elif internal_label == "ORG":
                    if self._is_single_common_word(entity_text):
                        continue
                    if self._is_legal_doc_title(entity_text):
                        continue
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

        # Step 4: company keyword fallback — only accept candidates that either
        # contain an unambiguous incorporation token, or combine a softer
        # corporate keyword with at least one non-generic word. This prevents
        # "Code", "Act", "Group Insurance Scheme" etc. being captured as ORGs.
        for line in text.split('\n'):
            line = line.strip()
            if len(line) < 5:
                continue
            company_pattern = re.compile(r'([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})')
            for match in company_pattern.finditer(line):
                candidate = match.group(1)
                if candidate in seen_entities:
                    continue
                words = candidate.split()
                if len(words) < 2:
                    continue
                if self._is_legal_doc_title(candidate):
                    continue

                clean_words = [w.strip(",.") for w in words if w.strip(",.")]
                clean_lower = {w.lower() for w in clean_words}
                incorp_lower = {s.lower() for s in INCORPORATION_TOKENS}
                soft_lower = {s.lower() for s in SOFT_COMPANY_SUFFIX}
                medium_lower = {s.lower() for s in MEDIUM_COMPANY_KEYWORDS}
                has_incorp = bool(clean_lower & incorp_lower)
                has_soft_suffix = bool(clean_lower & soft_lower)
                has_medium_keyword = bool(clean_lower & medium_lower)
                has_non_common = any(
                    w.lower() not in COMMON_WORDS for w in clean_words if w
                )

                if not (has_incorp or ((has_soft_suffix or has_medium_keyword) and has_non_common)):
                    continue

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
            if self._is_legal_doc_title(snippet):
                continue
            # Require at least one genuinely non-generic token so legal
            # boilerplate ("office of the establishment and such records…")
            # isn't captured as a location.
            snippet_words = [
                w.strip(".,-") for w in snippet.split() if w.strip(".,-")
            ]
            has_non_common = any(
                w.lower() not in COMMON_WORDS for w in snippet_words
            )
            if not has_non_common:
                continue
            placeholder = f"LOC_{entity_counters['LOC']}"
            entity_counters['LOC'] += 1
            entity_map[placeholder] = snippet
            seen_entities.add(snippet)

        # Step 6: drop ORG entities that are merely fragments of a statutory
        # document title appearing in the text (e.g. "Social Security" inside
        # "The Code on Social Security, 2020"). Companies are exempt.
        for placeholder in [k for k in entity_map if k.startswith("ORG_")]:
            org_text = entity_map[placeholder]
            if self._looks_like_statutory_fragment(org_text, text):
                logger.debug("Dropping statutory fragment ORG %r", org_text)
                del entity_map[placeholder]
                seen_entities.discard(org_text)

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
                    if self._is_single_common_word(entity_text):
                        continue
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1
                elif internal_label == "ORG":
                    if self._is_single_common_word(entity_text):
                        continue
                    if self._is_legal_doc_title(entity_text):
                        continue
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
                    if self._is_single_common_word(entity_text):
                        continue
                    parts = entity_text.split()
                    if len(parts) == 1 and len(entity_text) < 4:
                        continue
                    placeholder = f"PERSON_{entity_counters['PERSON']}"
                    entity_counters['PERSON'] += 1
                elif internal_label == "ORG":
                    if self._is_single_common_word(entity_text):
                        continue
                    if self._is_legal_doc_title(entity_text):
                        continue
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
            company_pattern = re.compile(r'([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})')
            for match in company_pattern.finditer(val):
                candidate = match.group(1)
                if candidate in seen_entities:
                    continue
                words = candidate.split()
                if len(words) < 2:
                    continue
                if self._is_legal_doc_title(candidate):
                    continue

                clean_words = [w.strip(",.") for w in words]
                has_incorp = any(w in INCORPORATION_TOKENS for w in clean_words)
                has_soft_suffix = any(w in SOFT_COMPANY_SUFFIX for w in clean_words)
                has_medium_keyword = any(w in MEDIUM_COMPANY_KEYWORDS for w in clean_words)
                has_non_common = any(
                    w.lower() not in COMMON_WORDS for w in clean_words if w
                )

                if not (has_incorp or ((has_soft_suffix or has_medium_keyword) and has_non_common)):
                    continue

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

    def anonymize(self, text: str, multiplier: float, entity_types: Dict[str, bool], skip_entities: Optional[set] = None) -> Tuple[Dict[str, str], str, Dict[str, Any]]:
        skip_entities = skip_entities or set()
        entity_map = self.extract_entities(text, entity_types)
        if skip_entities:
            entity_map = {
                k: v for k, v in entity_map.items() if v not in skip_entities
            }

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
