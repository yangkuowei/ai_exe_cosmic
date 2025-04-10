"""需求分析模块 - 读取需求文档并调用AI进行分析"""
from pathlib import Path
import logging
from typing import Tuple, Any

from ai_common import load_model_config
from langchain_openai_client_v1 import call_ai
from read_file_content import read_file_content, save_content_to_file, read_word_document
from validate_cosmic_table import extract_json_from_text

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from project_paths import ProjectPaths

def extract_markdown_from_text(text: str) -> str:
    """从文本中提取markdown格式内容"""
    # 查找markdown代码块
    start = text.find('```markdown')
    if start == -1:
        start = text.find('```')
        if start == -1:
            return text.strip()  # 如果没有代码块标记，返回整个文本
    
    start = text.find('\n', start) + 1  # 跳过代码块标记行
    end = text.find('```', start)
    if end == -1:
        return text[start:].strip()  # 如果没有结束标记，返回剩余文本
    
    return text[start:end].strip()

def empty_validator(data: Any) -> Tuple[bool, str]:
    """空校验器，总是返回验证通过"""
    return True, ""

def analyze_requirements():
    """主分析流程"""
    try:
        config = ProjectPaths()
        
        # 1. 读取AI系统提示词
        prompt_path = config.ai_promote / "requirement_analysis.md"
        prompt = read_file_content(str(prompt_path))
        
        # 2. 读取所有需求文件
        doc_files = list(config.requirements.glob("*.doc")) + list(config.requirements.glob("*.docx"))
        if not doc_files:
            raise FileNotFoundError(f"需求目录中未找到.doc或.docx文件: {config.requirements}")
        
        # 3. 处理每个需求文件
        for request_file in doc_files:
            logger.info(f"开始处理需求文件: {request_file.name}")
            
            # 读取需求内容
            content = read_word_document(str(request_file))
            
            # 调用AI进行分析
            json_data = call_ai(
                ai_prompt=prompt,
                requirement_content=content,
                extractor=extract_json_from_text,
                validator=empty_validator,
                max_chat_count=1,
                config=load_model_config()
            )
            
            # 预处理并保存结果
            output_path = config.output / request_file.stem
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 原始文件路径
            raw_file = output_path / f"{ProjectPaths.REQUIREMENT_PREFIX}{request_file.stem}.json"
            
            # 1. 保存原始结果
            save_content_to_file(
                file_name=raw_file.name,
                output_dir=str(output_path),
                content=json_data,
                content_type="json"
            )
            
            # 2. 转换为业务需求文本
            converter_prompt_path = config.ai_promote / "json_onverter_requirements.md"
            converter_prompt = read_file_content(str(converter_prompt_path))
            
            business_text = call_ai(
                ai_prompt=converter_prompt,
                requirement_content=json_data,
                extractor=extract_markdown_from_text,
                validator=empty_validator,
                max_chat_count=1,
                config=load_model_config()
            )
            
            save_content_to_file(
                file_name=f"business_{raw_file.name.replace('.json','.txt')}",
                output_dir=str(output_path),
                content=business_text,
                content_type="text"
            )
            
            # 3. 预处理(添加tableRows)
            from preprocessor import process_json_file
            processed_file = output_path / f"processed_{raw_file.name}"
            process_json_file(raw_file, processed_file)
            
            # 3. 拆分JSON
            from splitter import split_json_file
            split_files = split_json_file(processed_file, output_path)
            
            logger.info(f"需求分析结果已处理完成，生成{len(split_files)}个子文件")
            
    except Exception as e:
        logger.error(f"需求分析失败: {str(e)}")
        raise

if __name__ == "__main__":
    analyze_requirements()
