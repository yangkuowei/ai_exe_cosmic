from typing import List

# 配置开发人员白名单
DEVELOPERS: List[str] = [
    "杨扩威", 
    "张三",
    "李四"
]

# 模板文件路径
TEMPLATE_PATHS = {
    "requirement_analysis": "ai_promote/requirement_analysis.md",
    "cosmic_table": "ai_promote/create_cosmic_table.md"
}

# 输出文件后缀
FILE_NAME = {
    "requirement_json": "requirement_analysis.json",
    "cosmic_table": "markdown_table.md"
}

# 支持的输入文件格式
INPUT_FILE_EXTENSIONS = ['.doc', '.docx']
