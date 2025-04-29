import os
import json
from pathlib import Path

from ..core.context import ProcessingContext
from langchain_openai_client_v1 import call_ai
from read_file_content import save_content_to_file
from project_paths import FILE_NAME

def process_requirement_analysis(pipeline, context: ProcessingContext) -> bool:
    """需求分析阶段"""
    try:
        # 从输入文件名提取需求目录名（去掉后缀）
        requirement_dir = Path(context.input_path).stem

        # 构建完整输出路径
        output_path = os.path.join(context.stage_data['output_dir'], requirement_dir)
        os.makedirs(output_path, exist_ok=True)

        # 检查输出文件是否已存在
        full_file_name = os.path.join(output_path, FILE_NAME['requirement_json'])
        if os.path.exists(full_file_name):
            pipeline.logger.info(f"需求分析文件已存在，跳过处理: {full_file_name}")
            with open(full_file_name, 'r', encoding='utf-8') as f:
                context.stage_data['requirement_json'] = f.read()
            return True

        # 读取需求文档内容
        content = context.stage_data['requirement_extraction']

        # 调用AI分析
        json_data = call_ai(
            ai_prompt=pipeline.requirement_prompt,
            requirement_content=content,
            extractor=pipeline._extract_json_from_text,
            validator=pipeline._validate_requirement_analysis_json,
            config=pipeline.model_config
        )

        # 保存结果
        save_content_to_file(
            file_name=FILE_NAME['requirement_json'],
            output_dir=output_path,
            content=json_data,
            content_type="json"
        )

        context.stage_data['requirement_json'] = json_data
        return True

    except Exception as e:
        pipeline.logger.error(f"需求分析失败: {str(e)}")
        return False
