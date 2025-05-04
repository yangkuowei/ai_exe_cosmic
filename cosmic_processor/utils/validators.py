from typing import Tuple, Optional

import Levenshtein


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


def calculate_levenshtein_similarity(str1: str, str2: str) -> float:
    """
    计算两个字符串基于 Levenshtein 距离的相似度。

    相似度计算公式: 1 - (Levenshtein距离 / 两个字符串中较长者的长度)
    或者使用 Levenshtein.ratio() 的归一化公式：
    ratio = (len(str1) + len(str2) - distance) / (len(str1) + len(str2))
    这里我们直接使用库提供的 ratio() 方法，它返回一个 [0, 1] 范围内的相似度。

    Args:
        str1: 第一个字符串。
        str2: 第二个字符串。

    Returns:
        两个字符串的相似度，范围在 0.0 到 1.0 之间。
        1.0 表示完全相同，0.0 表示完全不同（根据 ratio 的定义，
        除非一个字符串为空另一个非空）。

    Raises:
        TypeError: 如果输入的不是字符串类型。
    """
    if not isinstance(str1, str) or not isinstance(str2, str):
        raise TypeError("输入参数必须是字符串类型")

    # 处理空字符串的边界情况
    # Levenshtein.ratio("", "") 返回 1.0
    # Levenshtein.ratio("abc", "") 返回 0.0
    # Levenshtein.ratio("", "abc") 返回 0.0
    # 这些行为符合预期，无需特殊处理

    # 使用 Levenshtein.ratio() 直接计算归一化相似度
    similarity_ratio = Levenshtein.ratio(str1, str2)

    return similarity_ratio