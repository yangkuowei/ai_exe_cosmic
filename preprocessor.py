"""JSON预处理模块 - 为需求分析结果添加tableRows字段"""
import json
from typing import Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def add_table_rows(data: Dict[str, Any]) -> Dict[str, Any]:
    """为每个functionalPoint添加tableRows字段"""
    if "functionalPoints" not in data:
        return data
        
    for point in data["functionalPoints"]:
        if "workloadPercentage" in point:
            point["tableRows"] = int(point["workloadPercentage"] * data["workload"] /100)
            
    return data

def process_json_file(input_path: Path, output_path: Path) -> None:
    """处理单个JSON文件"""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        processed_data = add_table_rows(data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"成功处理文件: {input_path} -> {output_path}")
    except Exception as e:
        logger.error(f"处理文件失败 {input_path}: {str(e)}")
        raise
