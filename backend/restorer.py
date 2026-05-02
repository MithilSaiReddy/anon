import re
from typing import Dict, Tuple, Any


class Restorer:
    def __init__(self):
        pass

    def restore_text(self, text: str, key_data: Dict[str, Any]) -> Tuple[str, Dict[str, int]]:
        entity_map = key_data.get("entities", {})
        number_map = key_data.get("number_mappings", {})
        multiplier = key_data.get("multiplier", 1.0)

        result_text = text
        restore_counts = {"entities": 0, "numbers": 0}

        for placeholder, original in entity_map.items():
            if placeholder in result_text:
                result_text = result_text.replace(placeholder, original)
                restore_counts["entities"] += 1

        if number_map:
            for orig_str, new_val in number_map.items():
                if str(new_val) in result_text:
                    result_text = result_text.replace(str(new_val), orig_str)
                    restore_counts["numbers"] += 1
        elif multiplier != 1.0:
            def divide_number(match):
                try:
                    num = float(match.group())
                    result = round(num / multiplier, 2)
                    if result == int(result):
                        return str(int(result))
                    return str(result)
                except ValueError:
                    return match.group()

            result_text = re.sub(r'\b\d+\.?\d+\b', divide_number, result_text)

        return result_text, restore_counts

    def restore_raw_text(self, text: str, key_data: Dict[str, Any]) -> Tuple[str, Dict[str, int]]:
        return self.restore_text(text, key_data)


def create_restorer() -> Restorer:
    return Restorer()
