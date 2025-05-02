import os
import json
import math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import tempfile

from ..core.context import ProcessingContext
from langchain_openai_client_v1 import call_ai
from read_file_content import save_content_to_file
from project_paths import FILE_NAME


def _process_single_feature(pipeline, feature_data, requirement_data, output_path, index):
    """Process a single feature point and save to temporary file"""
    temp_file = os.path.join(output_path, f"requirement_analysis_part_{index}.json")
    
    # Check if temp file already exists
    if os.path.exists(temp_file):
        pipeline.logger.info(f"部分文件已存在，跳过处理: {temp_file}")
        return temp_file

    # Calculate cosmic lines for this feature
    cosmic_lines = math.ceil(
        (requirement_data['cosmic_total_lines'] * feature_data['workload_percentage']) / 100
    )
    
    # Format the content
    content = f"""需求名称:
{requirement_data['requirement_name']}

需求背景:
{requirement_data['requirement_background']}

需求解决方案:
功能1：{feature_data['feature_point']}
方案：{feature_data['description']}

cosmic总行数: 
{cosmic_lines}"""

    # Call AI and save result
    json_data = call_ai(
        ai_prompt=pipeline.requirement_prompt,
        requirement_content=content,
        extractor=pipeline._extract_json_from_text,
        validator=pipeline._validate_requirement_analysis_json,
        config=pipeline.model_config
    )
    
    # Ensure output directory exists
    os.makedirs(output_path, exist_ok=True)
    
    # Save to temporary file with correct path
    temp_filename = f"requirement_analysis_part_{index}.json"
    save_content_to_file(
        file_name=temp_filename,
        output_dir=output_path,
        content=json_data,
        content_type="json"
    )
    return os.path.join(output_path, temp_filename)


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
        requirement_data = json.loads(context.stage_data['requirement_extraction'])

        # Process each feature concurrently
        with ThreadPoolExecutor(max_workers=pipeline.max_workers_analysis) as executor:
            futures = []
            for idx, feature in enumerate(requirement_data['solution_details']):
                futures.append(
                    executor.submit(
                        _process_single_feature,
                        pipeline,
                        feature,
                        requirement_data,
                        output_path,
                        idx
                    )
                )

            # Wait for all futures to complete
            temp_files = [f.result() for f in futures]

        # Merge all temporary files into new structure
        final_output = {
            "requirementAnalysis": {
                "customerRequirement": requirement_data['requirement_name'],
                "customerRequirementWorkload": requirement_data['cosmic_total_lines'],
                "functionalUserRequirements": []
            }
        }

        # Collect functionalUserRequirements from all parts
        for temp_file in sorted(temp_files):
            with open(temp_file, 'r', encoding='utf-8') as f:
                part_data = json.load(f)
                if isinstance(part_data, dict) and 'requirementAnalysis' in part_data:
                    final_output['requirementAnalysis']['functionalUserRequirements'].extend(
                        part_data['requirementAnalysis']['functionalUserRequirements']
                    )
            os.remove(temp_file)  # Remove temp file

        # Save merged result
        json_data = json.dumps(final_output, ensure_ascii=False, indent=2)
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
