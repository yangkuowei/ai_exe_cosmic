from functools import partial
import re
import json
import shutil
from pathlib import Path
from typing import Optional, Any, List
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
            validator=validator,
            max_iterations = 3
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
    request_file: Path,
    batch_size: int = 3
) -> None:
    """生成COSMIC表格（支持分批处理）"""
    logger.info("开始生成COSMIC表格...")
    
    try:
        # 解析原始JSON数据
        cosmic_data = json.loads(json_data)
        # 创建临时目录
        temp_dir = output_dir / "temp"
        temp_dir.mkdir(exist_ok=True)
        
        # 分批处理触发事件（按需求逐个处理）
        batch_num = 1
        temp_files = []
        
        # 遍历每个需求
        for req in cosmic_data["functional_user_requirements"]:
            req_events = req["trigger_events"]
            requirement_name = req["requirement"]
            
            # 按需求内的触发事件分批
            for i in range(0, len(req_events), batch_size):
                batch_events = req_events[i:i+batch_size]
                
                # 构建单个需求的批次JSON
                batch_json = {
                    "functional_user_requirements": [{
                        "requirement": requirement_name,
                        "trigger_events": batch_events
                    }]
                }
            
            # 计算本批次功能过程数量
            total_processes = sum(
                len(event["functional_processes"])
                for req in batch_json["functional_user_requirements"]
                for event in req["trigger_events"]
            )
            
            # 生成动态行数范围
            min_rows = total_processes * 2
            max_rows = total_processes * 5
            row_range = f"{min_rows}~{max_rows}"
            
            # 更新基础内容中的行数要求
            content_lines = base_content.splitlines()
            for i in reversed(range(len(content_lines))):
                if "表格总行数要求：" in content_lines[i]:
                    # 使用正则表达式替换数字部分
                    content_lines[i] = re.sub(
                        r"(\d+)(行左右)", 
                        f"{row_range}行（根据功能过程数量动态计算）", 
                        content_lines[i]
                    )
                    break
                    
            updated_content = '\n'.join(content_lines)
            
            # 生成分批内容
            combined_content = f"{updated_content}\n触发事件与功能过程列表：\n{json.dumps(batch_json, ensure_ascii=False)}"
            
            # 调用AI生成表格
            markdown_table = call_ai(
                ai_prompt=prompt,
                requirement_content=combined_content,
                extractor=extract_table_from_text,
                validator=validate_cosmic_table
            )
            
            # 保存临时文件
            temp_filename = f"{request_file.stem}_batch{batch_num}.md"
            temp_path = temp_dir / temp_filename
            save_content_to_file(
                file_name=temp_filename,
                output_dir=str(temp_dir),
                content=markdown_table,
                content_type="markdown"
            )
            
            temp_files.append(temp_path)
            batch_num += 1
        
        # 合并临时文件
        full_table = merge_temp_files(temp_files)
        
        # 保存最终文件
        output_path = output_dir / request_file.stem
        save_content_to_file(
            file_name=request_file.name,
            output_dir=str(output_path),
            content=full_table,
            content_type="markdown"
        )
        
        # 生成Excel和Word
        processed_table = process_markdown_table(full_table)
        for file_type in ["xlsx", "docx"]:
            save_content_to_file(
                file_name=request_file.name,
                output_dir=str(output_path),
                content=processed_table,
                content_type=file_type
            )
        
        # 清理临时文件
        shutil.rmtree(temp_dir)
        logger.info(f"COSMIC表格已保存至: {output_path}")

    except Exception as e:
        logger.error(f"COSMIC表格生成失败: {str(e)}")
        raise

def merge_temp_files(temp_files: List[Path]) -> str:
    """合并临时Markdown表格文件"""
    full_content = []
    
    for i, file_path in enumerate(sorted(temp_files)):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().splitlines()
            
            if i == 0:
                # 保留第一个文件的完整头
                full_content.extend(content)
            else:
                # 跳过后续文件的头两行（标题和分隔符）
                full_content.extend(content[2:])
    
    return "\n".join(full_content)

if __name__ == "__main__":
    main()
