from typing import Tuple, Optional


def validate_empty(text: str) -> Tuple[bool, str]:
    """空验证器"""
    return True, ''

def validate_requirement_analysis_json(json_str: str) -> Tuple[bool, str]:
    """验证需求分析JSON"""
    from validate.validate_requirement_analysis_json import validate_requirement_analysis_json as validate
    return validate(json_str)

def validate_cosmic_table(markdown_table_str: str, table_rows: Optional[int] = None) -> Tuple[bool, str]:
    """验证COSMIC表格"""
    from validate.validate_cosmic_table import validate_cosmic_table as validate
    return validate(markdown_table_str, table_rows)
