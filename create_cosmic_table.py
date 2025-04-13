import json
import os
import concurrent.futures
import time
from functools import partial
from typing import List, Dict, Any
from pathlib import Path

from ai_common import load_model_config
from langchain_openai_client_v1 import call_ai
from decorators import ai_processor
from project_paths import ProjectPaths
from validate_cosmic_table import validate_cosmic_table, extract_table_from_text
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging # 导入日志模块

# 获取 logger 实例 (确保日志已在别处配置，例如 orchestrator.py)
logger = logging.getLogger(__name__)

def read_prompt_file(prompt_path: str) -> str:
    """读取AI提示词文件"""
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def read_business_req(business_req_path: str) -> str:
    """读取业务需求文本文件"""
    with open(business_req_path, 'r', encoding='utf-8') as f:
        return f.read()

def read_trigger_event_files(output_dir: str) -> List[Dict[str, Any]]:
    """读取所有触发事件JSON文件，跳过已处理的"""
    trigger_files = [
        f for f in os.listdir(output_dir) 
        if f.startswith('trigger_events') and f.endswith('.json')
    ]
    
    # 获取已生成的表格文件
    existing_tables = [
        f for f in os.listdir(output_dir)
        if f.startswith('table_cosmic_') and f.endswith('.md')
    ]
    processed_indices = {
        f.split('_')[-1].split('.')[0] for f in existing_tables
    }
    
    events = []
    for file in trigger_files:
        event_num = file.split('_')[-1].split('.')[0]
        if event_num not in processed_indices:
            with open(Path(output_dir) / file, 'r', encoding='utf-8') as f:
                event_data = json.load(f)
                event_data['file_name'] = file
                events.append(event_data)
    return events

def process_single_event(
    ai_prompt: str,
    business_req: str,
    event_data: Dict[str, Any],
    output_dir: str
) -> None:
    """处理单个触发事件并保存结果"""
    # 提取tableRows
    table_rows = event_data['functional_user_requirements'][0]['tableRows']
    
    # 组合业务需求文本和触发事件文本
    combined_content = f"完整业务需求\n{business_req}\n本次生成表格仅处理此JSON中定义的内容和行数\n{json.dumps(event_data, indent=2, ensure_ascii=False)}"
    
    # 调用AI生成表格
    validator = partial(validate_cosmic_table, expected_total_rows=table_rows)
    markdown_table = ai_processor()(
        call_ai
    )(
        ai_prompt=ai_prompt,
        requirement_content=combined_content,
        extractor=extract_table_from_text,
        validator=validator,
        max_chat_count = 8,
        config=load_model_config()
    )
    
    # 保存结果文件
    event_num = Path(event_data['file_name']).stem.split('_')[-1]  # 从文件名提取序号
    output_path = Path(output_dir) / f"table_cosmic_{event_num}.md"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_table)

def create_cosmic_table(req_name: str = None):
    """主处理流程
    Args:
        req_name: 需求名称，用于指定要处理的需求目录
    """
    config = ProjectPaths()
    prompt_path = config.ai_promote / "create_cosmic_table_from_trigger_events.md"
    
    if req_name is None:
        raise ValueError("必须提供req_name参数")
        
    # 处理req_name格式: "开发人员姓名/需求名称"
    if '/' in req_name:
        dev_name, req_base = req_name.split('/', 1)
        output_dir = config.output / dev_name / req_base
        business_req_path = output_dir / f"business_req_analysis_{req_base}.txt"
    else:
        output_dir = config.output / req_name
        business_req_path = output_dir / f"business_req_analysis_{req_name}.txt"
        req_base = req_name # Define req_base here

    # 检查最终合并文件是否已存在，如果存在则跳过
    merged_file_path = output_dir / f"{req_base}_cosmic_merged.md"
    if merged_file_path.exists():
        logger.info(f"[{req_name}] 最终合并文件 {merged_file_path} 已存在，跳过 COSMIC 表生成步骤。")
        return # 直接返回，跳过后续处理

    # 检查业务需求文件是否存在
    if not business_req_path.exists():
        raise FileNotFoundError(f"业务需求文件不存在: {business_req_path}")
    
    # 读取必要文件
    ai_prompt = read_prompt_file(str(prompt_path))
    business_req = read_business_req(str(business_req_path))
    trigger_events = read_trigger_event_files(str(output_dir))
    
    # 使用线程池并发处理
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = []
        for event in trigger_events:
            futures.append(
                executor.submit(
                    process_single_event,
                    ai_prompt,
                    business_req,
                    event,
                    output_dir
                )
            )
            # 添加请求间隔
            time.sleep(3)
        
        # 等待所有任务完成
        concurrent.futures.wait(futures)
