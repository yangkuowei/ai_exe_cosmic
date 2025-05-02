from typing import List

# 配置开发人员白名单
DEVELOPERS: List[str] = [
    "杨小扩",
    "张三",
    "李四"
]

# 模板文件路径
TEMPLATE_PATHS = {
    "requirement_extraction": "ai_promote/requirement_extraction.md",
    "requirement_analysis": "ai_promote/requirement_analysis.md", 
    "cosmic_table": "ai_promote/create_cosmic_table.md",
    "necessity": "ai_promote/create_necessity.md",
    "output_base_dir": "out_put_files",
    "out_template_base_dir": "out_template",
}

# 输出文件后缀
FILE_NAME = {
    "requirement_extraction": "requirement_extraction.json",
    "requirement_json": "requirement_analysis.json",
    "cosmic_table": "markdown_table.md",
    "necessity": "necessity.txt",
    "temp_excel": "temp_excel.xlsx",
    "template_xlsx": "template.xlsx",
}

# 支持的输入文件格式
INPUT_FILE_EXTENSIONS = ['.doc', '.docx']
