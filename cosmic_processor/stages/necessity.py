import os
from pathlib import Path

from ..core.context import ProcessingContext
from langchain_openai_client_v1 import call_ai
from read_file_content import save_content_to_file
from project_paths import FILE_NAME

def process_necessity(pipeline, context: ProcessingContext) -> bool:
    """建设必要性分析阶段"""
    try:
        # 从输入文件名提取需求目录名（去掉后缀）
        requirement_dir = Path(context.input_path).stem

        # 构建完整输出路径
        output_path = os.path.join(context.stage_data['output_dir'], requirement_dir)
        os.makedirs(output_path, exist_ok=True)

        # 检查输出文件是否已存在
        file_name = os.path.join(output_path,FILE_NAME['necessity'])
        if os.path.exists(file_name):
            pipeline.logger.info(f"建设必要性分析已完成，跳过处理: {file_name}")
            with open(file_name, 'r', encoding='utf-8') as f:
                context.stage_data['necessity'] = f.read()
            return True

        # 读取需求文档内容
        content = context.stage_data['requirement_extraction']

        # 调用AI分析
        txt = call_ai(
            ai_prompt=pipeline.necessity_prompt,
            requirement_content=content,
            extractor=pipeline._extract_text,
            validator=pipeline._validate_empty,
            config=pipeline.model_config
        )

        # 保存结果
        save_content_to_file(
            file_name=FILE_NAME['necessity'],
            output_dir=output_path,
            content=txt,
            content_type="text"
        )

        context.stage_data['necessity'] = txt
        return True

    except Exception as e:
        pipeline.logger.error(f"建设必要性生成失败: {str(e)}")
        return False
