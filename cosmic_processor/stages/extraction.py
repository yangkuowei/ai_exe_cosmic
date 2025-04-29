import os
from typing import Dict, Any
from pathlib import Path

from ..core.context import ProcessingContext
from my_openai_client import call_ai
from read_file_content import read_word_document, save_content_to_file
from project_paths import FILE_NAME

def requirement_extraction(pipeline, context: ProcessingContext) -> bool:
    """需求提取阶段"""
    # 从输入文件名提取需求目录名（去掉后缀）
    requirement_dir = Path(context.input_path).stem

    # 构建完整输出路径
    output_path = os.path.join(context.stage_data['output_dir'], requirement_dir)
    os.makedirs(output_path, exist_ok=True)

    # 检查输出文件是否已存在
    full_file_name = os.path.join(output_path,FILE_NAME['requirement_extraction'])
    if os.path.exists(full_file_name):
        pipeline.logger.info(f"需求已提取，跳过处理: {full_file_name}")
        with open(full_file_name, 'r', encoding='utf-8') as f:
            context.stage_data['requirement_extraction'] = f.read()
        return True

    # 读取需求文档内容(使用原始路径)
    content = read_word_document(context.original_input_path)
    # 调用AI分析
    text = call_ai(
        ai_prompt=pipeline.requirement_extraction_prompt,
        requirement_content=content,
        extractor=pipeline._extract_text,
        validator=pipeline._validate_empty,
        config=pipeline.load_model_config_aliyun
    )
    # 保存结果
    save_content_to_file(
        file_name=FILE_NAME['requirement_extraction'],
        output_dir=output_path,
        content=text,
        content_type="text"
    )

    context.stage_data['requirement_extraction'] = text
    return True
