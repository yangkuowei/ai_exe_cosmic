"""触发事件创建模块 - 读取需求分析JSON并调用AI生成触发事件"""
import time
from pathlib import Path
import logging
import json
from typing import Tuple, Any

from ai_common import load_model_config
from langchain_openai_client_v1 import call_ai
from read_file_content import read_file_content, save_content_to_file
from validate_cosmic_table import extract_json_from_text, validate_trigger_event_json
from project_paths import ProjectPaths
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_single_file(json_file: Path, prompt: str, output_base: Path) -> Path:
    """处理单个JSON文件"""
    try:
        logger.info(f"开始处理JSON文件: {json_file.name}")
        
        # 检查输出文件是否已存在
        parts = json_file.stem.split('_part')
        req_name = parts[0].replace('processed_req_analysis_', '')
        output_path = output_base / req_name
        output_file = output_path / f"{ProjectPaths.TRIGGER_EVENT_PREFIX}{req_name}_{parts[1]}.json"
        
        if output_file.exists():
            logger.info(f"触发事件文件已存在，跳过处理: {output_file}")
            return output_path
            
        with open(json_file, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        # 将JSON对象转为字符串
        content_str = json.dumps(content, ensure_ascii=False)
        
        # 获取tableRows值作为total_rows
        total_rows = content['functionalPoints'][0].get('tableRows', 0)
        
        # 读取业务需求文本
        parts = json_file.stem.split('_part')
        req_name = parts[0].replace('processed_req_analysis_', '')
        business_file = json_file.parent / f"business_req_analysis_{req_name}.txt"
        business_content = read_file_content(str(business_file))
        
        # 合并业务需求文本和JSON内容
        combined_content = f"完整业务需求:\n{business_content}\n\n本次需要生成的功能点：\n{content_str}"
        
        json_data = call_ai(
            ai_prompt=prompt,
            requirement_content=combined_content,
            extractor=extract_json_from_text,
            validator=lambda data: validate_trigger_event_json(data, total_rows=total_rows),
            max_chat_count=5,
            config=load_model_config()
        )
        
        # 从路径中提取原始需求文件名
        parts = json_file.stem.split('_part')
        req_name = parts[0].replace('processed_req_analysis_', '')
        output_path = output_base / req_name
        
        save_content_to_file(
            file_name=f"{ProjectPaths.TRIGGER_EVENT_PREFIX}{req_name}_{parts[1]}.json",
            output_dir=str(output_path),
            content=json_data,
            content_type="json"
        )
        return output_path
        
    except Exception as e:
        logger.error(f"处理文件失败 {json_file}: {str(e)}")
        raise

def create_trigger_events():
    """主处理流程"""
    try:
        config = ProjectPaths()
        prompt_path = config.ai_promote / "create_trigger_events.md"
        prompt = read_file_content(str(prompt_path))
        
        # 查找所有拆分后的子JSON文件
        json_files = list(config.output.glob("**/processed_req_analysis_*_part*.json"))
        if not json_files:
            raise FileNotFoundError(f"未找到预处理后的JSON文件: {config.output}")
        
        # 使用线程池处理，添加限流控制
        max_concurrent = 6  # 最大并发数
        request_interval = 1  # 请求间隔(秒)
        
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {}
            for i, f in enumerate(json_files):
                # 添加请求间隔
                if i > 0 and i % max_concurrent == 0:
                    time.sleep(request_interval)
                
                future = executor.submit(process_single_file, f, prompt, config.output)
                futures[future] = f
            
            for future in as_completed(futures):
                try:
                    output_path = future.result()
                    logger.info(f"任务完成，结果保存至: {output_path}")
                except Exception as e:
                    logger.error(f"任务处理失败: {str(e)}")
            
    except Exception as e:
        logger.error(f"触发事件创建失败: {str(e)}")
        raise

if __name__ == "__main__":
    create_trigger_events()
