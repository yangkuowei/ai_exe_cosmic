"""JSON拆分模块 - 按functionalPoints拆分需求分析结果"""
import json
from copy import deepcopy
from pathlib import Path
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def split_by_functional_points(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将单个JSON拆分为多个子JSON"""
    if "functionalPoints" not in data or not data["functionalPoints"]:
        return [data]
        
    results = []
    for point in data["functionalPoints"]:
        new_data = deepcopy(data)
        new_data["functionalPoints"] = [point]
        results.append(new_data)
        
    return results

def split_json_file(input_path: Path, output_dir: Path) -> List[Path]:
    """拆分单个JSON文件"""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        split_data = split_by_functional_points(data)
        output_files = []
        
        for i, sub_data in enumerate(split_data, 1):
            output_path = output_dir / f"{input_path.stem}_part{i}.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(sub_data, f, ensure_ascii=False, indent=2)
            output_files.append(output_path)
            logger.info(f"生成子文件: {output_path}")
            
        return output_files
        
    except Exception as e:
        logger.error(f"拆分文件失败 {input_path}: {str(e)}")
        raise
