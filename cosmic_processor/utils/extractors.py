import re
from typing import Tuple, Optional
from validate_cosmic_table import extract_json_from_text, extract_table_from_text

def extract_text(text: str) -> str:
    """从AI回复中提取```text ```标记之间的内容"""
    match = re.search(r'```text\n(.*?)\n```', text, re.DOTALL)
    return match.group(1) if match else text

def extract_json_from_text(text: str) -> str:
    """从文本提取JSON"""
    from validate_cosmic_table import extract_json_from_text as extract
    return extract(text)

def extract_table_from_text(text: str) -> str:
    """从文本提取表格"""
    from validate_cosmic_table import extract_table_from_text as extract
    return extract(text)
