from functools import partial
import os
from pathlib import Path
from typing import Optional, Any
import logging

from ai_exe_cosmic.openAi_cline import call_ai
from ai_exe_cosmic.read_file_content import (
    process_markdown_table,
    read_file_content,
    save_content_to_file,
    extract_number
)
from ai_exe_cosmic.validate_cosmic_table import (
    validate_cosmic_table,
    extract_table_from_text,
    extract_json_from_text,
    validate_trigger_event_json
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProjectConfig:
    """项目路径配置类"""
    def __init__(self):
        self.base_dir = Path(__file__).parent.resolve()
        
        # 定义项目目录结构
        self.ai_promote_dir = self.base_dir / "ai_promote"
        self.requirements_dir = self.base_dir / "requirements"
        self.output_dir = self.base_dir / "out_put_files"
        
        # 定义模板文件
        self.trigger_events_template = self.ai_promote_dir / "create_trigger_events.md"
        self.cosmic_table_template = self.ai_promote_dir / "create_cosmic_table_from_trigger_events.md"

    def validate_paths(self) -> None:
        """验证必要目录是否存在"""
        required_dirs = [
            self.ai_promote_dir,
            self.requirements_dir,
            self.output_dir
        ]
        
        for directory in required_dirs:
            if not directory.exists():
                raise FileNotFoundError(f"Required directory not found: {directory}")

def load_prompt_template(template_path: Path) -> str:
    """加载AI提示模板"""
    try:
        return read_file_content(str(template_path))
    except Exception as e:
        logger.error(f"Failed to load prompt template: {template_path}")
        raise RuntimeError(f"Prompt template loading failed: {e}") from e

def main() -> None:
    """主业务流程"""
    try:
        config = ProjectConfig()
        config.validate_paths()
        
        # 加载提示模板
        trigger_prompt = load_prompt_template(config.trigger_events_template)
        cosmic_prompt = load_prompt_template(config.cosmic_table_template)
        
        # 读取需求文件
        request_file = config.requirements_dir / '202411291723184关于全光WiFi（FTTR）业务流程-转普通宽带智能网关出库的补充需求.txt'
        requirement_content = read_file_content(str(request_file))
        
        # 提取表格行数要求
        total_rows = extract_number(requirement_content)
        if total_rows is None:
            raise ValueError(f"需求文件中缺少表格总行数要求: {request_file.name}")
            
        logger.info(f"成功读取需求文件: {request_file.name}")

        # 生成触发事件JSON
        json_str = generate_trigger_events(
            prompt=trigger_prompt,
            requirement=requirement_content,
            total_rows=total_rows,
            output_dir=config.output_dir,
            request_file=request_file
        )

        # 生成COSMIC表格
        generate_cosmic_table(
            prompt=cosmic_prompt,
            base_content=requirement_content,
            json_data=json_str,
            output_dir=config.output_dir,
            request_file=request_file
        )

    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}")
        raise

def generate_trigger_events(
    prompt: str,
    requirement: str,
    total_rows: int,
    output_dir: Path,
    request_file: Path
) -> str:
    """生成触发事件JSON数据"""
    logger.info("开始生成触发事件...")
    
    validator = partial(validate_trigger_event_json, total_rows=total_rows)
    
    try:
        json_data = call_ai(
            ai_prompt=prompt,
            requirement_content=requirement,
            extractor=extract_json_from_text,
            validator=validator
        )
        
        output_path = output_dir / request_file.stem
        save_content_to_file(
            file_name=request_file.name,  # 使用完整的文件名
            output_dir=str(output_path),  # 转换为字符串
            content=json_data,
            content_type="json"
        )
        
        logger.info(f"触发事件已保存至: {output_path}")
        return json_data
        
    except Exception as e:
        logger.error(f"触发事件生成失败: {str(e)}")
        raise

def generate_cosmic_table(
    prompt: str,
    base_content: str,
    json_data: str,
    output_dir: Path,
    request_file: Path
) -> None:
    """生成COSMIC表格"""
    logger.info("开始生成COSMIC表格...")
    
    try:
        combined_content = f"{base_content}\n触发事件与功能过程列表：\n{json_data}"
        
        markdown_table = call_ai(
            ai_prompt=prompt,
            requirement_content=combined_content,
            extractor=extract_table_from_text,
            validator=validate_cosmic_table
        )
        
        output_path = output_dir / request_file.stem
        
        # 保存并处理Markdown表格
        save_content_to_file(
            file_name=request_file.name,
            output_dir=str(output_path),
            content=markdown_table,
            content_type="markdown"
        )
        
        processed_table = process_markdown_table(markdown_table)
        
        # 生成Excel文件
        save_content_to_file(
            file_name=request_file.name,
            output_dir=str(output_path),
            content=processed_table,
            content_type="xlsx"
        )
        
        # 生成Word文档
        save_content_to_file(
            file_name=request_file.name,
            output_dir=str(output_path),
            content=processed_table,
            content_type="docx"
        )
        
        logger.info(f"COSMIC表格已保存至: {output_path}")

    except Exception as e:
        logger.error(f"COSMIC表格生成失败: {str(e)}")
        raise

if __name__ == "__main__":
    main()
