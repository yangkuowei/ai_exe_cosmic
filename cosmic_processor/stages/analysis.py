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


def _process_feature_group(pipeline, group_features, requirement_data, output_path, group_index):
    """Process a group of feature points and save to temporary file"""
    temp_file = os.path.join(output_path, f"requirement_analysis_part_{group_index}.json")
    
    # Check if temp file already exists
    if os.path.exists(temp_file):
        pipeline.logger.info(f"部分文件已存在，跳过处理: {temp_file}")
        return temp_file

    # Calculate total cosmic lines for this group
    cosmic_lines = 0
    for feature in group_features:
        cosmic_lines += math.ceil(
            (requirement_data['cosmic_total_lines'] * feature['workload_percentage']) / 100
        )
    
    # Format the content with all features in group
    features_content = []
    for idx, feature in enumerate(group_features, 1):
        features_content.append(
            f"功能{idx}：{feature['feature_point']}\n"
            f"方案：{feature['description']}\n"
        )
    
    features_str = "\n".join(features_content)
    content = f"""需求名称:
{requirement_data['requirement_name']}

需求背景:
{requirement_data['requirement_background']}

需求解决方案:
{features_str}
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
    temp_filename = f"requirement_analysis_part_{group_index}.json"
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

        # Calculate workload for each feature and group them
        feature_groups = []
        current_group = []
        current_workload = 0
        
        for feature in requirement_data['solution_details']:
            workload = math.ceil(
                (requirement_data['cosmic_total_lines'] * feature['workload_percentage']) / 100
            )
            
            if current_workload + workload > 0 and current_group:
                feature_groups.append(current_group)
                current_group = [feature]
                current_workload = workload
            else:
                current_group.append(feature)
                current_workload += workload
        
        if current_group:
            feature_groups.append(current_group)

        # Process feature groups concurrently
        with ThreadPoolExecutor(max_workers=pipeline.max_workers_analysis) as executor:
            futures = []
            for group_idx, group in enumerate(feature_groups):
                futures.append(
                    executor.submit(
                        _process_feature_group,
                        pipeline,
                        group,
                        requirement_data,
                        output_path,
                        group_idx
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
