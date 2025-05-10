import os
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..core.context import ProcessingContext
from langchain_openai_client_v1 import call_ai
from read_file_content import save_content_to_file
from project_paths import FILE_NAME


def process_generate_cosmic(pipeline, context: ProcessingContext) -> bool:
    """生成COSMIC表格阶段(并行处理)"""
    try:
        # 构建完整输出路径
        requirement_dir = Path(context.input_path).stem
        output_path = os.path.join(context.stage_data['output_dir'], requirement_dir)
        os.makedirs(output_path, exist_ok=True)

        # 检查完整输出文件是否已存在
        full_file_name = os.path.join(output_path, FILE_NAME['cosmic_table'])
        if os.path.exists(full_file_name):
            pipeline.logger.info(f"COSMIC表格文件已存在，跳过处理: {full_file_name}")
            return True

        # 拆分JSON为多个事件部分
        event_parts = _split_requirement_json(context.stage_data['requirement_json'])

        # 使用线程池并行处理
        with ThreadPoolExecutor(max_workers=pipeline.max_workers_analysis) as executor:
            futures = []
            for i, event_data in enumerate(event_parts, 1):
                if i > 1:
                    time.sleep(3)
                futures.append(executor.submit(
                    _process_single_event,
                    pipeline,
                    event_data,
                    output_path,
                    i
                ))

            # 等待所有任务完成
            results = [f.result() for f in futures]
            if not all(results):
                return False

        # 合并所有部分文件
        merged_content = _merge_markdown_files(output_path)
        save_content_to_file(
            file_name=FILE_NAME['cosmic_table'],
            output_dir=output_path,
            content=merged_content,
            content_type="markdown"
        )

        # 清理临时文件
        for part_file in os.listdir(output_path):
            if part_file.startswith('cosmic_table_part_'):
                os.remove(os.path.join(output_path, part_file))

        save_content_to_file(
            file_name=FILE_NAME['temp_excel'],
            output_dir=output_path,
            content=merged_content,
            content_type="xlsx"
        )

        return True

    except Exception as e:
        pipeline.logger.error(f"生成表格失败: {str(e)}")
        return False


def _split_requirement_json(json_str: str) -> list:
    """将需求JSON按functionalUserRequirements拆分为多个部分，保持triggeringEvents完整性"""
    data = json.loads(json_str)
    requirements = data['requirementAnalysis']['functionalUserRequirements']
    result = []

    for req in requirements:
        # 每个functionalUserRequirements作为一个整体部分
        result.append(_create_batch_json(data, req, req['triggeringEvents']))

    return result


def _create_batch_json(data: dict, req: dict, events: list) -> dict:
    """根据functionalUserRequirements创建JSON结构"""
    workload = sum(len(event['functionalProcesses']) for event in events) * 3
    return {
        'requirementAnalysis': {
            'customerRequirement': data['requirementAnalysis']['customerRequirement'],
            'customerRequirementWorkload': workload,
            'functionalUserRequirements': [{
                'description': req['description'],
                'triggeringEvents': events
            }]
        }
    }


def _merge_markdown_files(output_path: str) -> str:
    """合并所有part文件内容"""
    part_files = sorted(
        [f for f in os.listdir(output_path) if f.startswith('cosmic_table_part_')],
        key=lambda x: int(x.split('_')[-1].split('.')[0])
    )
    full_content = []
    for i, part_file in enumerate(part_files):
        with open(os.path.join(output_path, part_file), "r", encoding="utf-8") as f:
            content = f.read().splitlines()
            if i == 0:
                # 保留第一个文件的完整头
                full_content.extend(content)
            else:
                # 跳过后续文件的头两行（标题和分隔符）
                full_content.extend(content[2:])

    return "\n".join(full_content)


def _process_single_event(pipeline, event_data: dict, output_path: str, part_num: int) -> bool:
    """处理单个事件并生成markdown"""
    part_file = f"cosmic_table_part_{part_num}.md"
    full_path = os.path.join(output_path, part_file)

    if os.path.exists(full_path):
        pipeline.logger.info(f"部分文件已存在，跳过处理: {full_path}")
        return True

    try:
        markdown_table = call_ai(
            ai_prompt=pipeline.cosmic_prompt,
            requirement_content=json.dumps(event_data, ensure_ascii=False),
            extractor=pipeline._extract_table_from_text,
            validator=lambda x: pipeline._validate_cosmic_table(x, event_data['requirementAnalysis'][
                'customerRequirementWorkload']),
            config=pipeline.model_config
        )

        save_content_to_file(
            file_name=part_file,
            output_dir=output_path,
            content=markdown_table,
            content_type="markdown"
        )
        return True
    except Exception as e:
        pipeline.logger.error(f"处理部分事件失败: {str(e)}")
        return False
