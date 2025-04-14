import os
import json
from pathlib import Path
from typing import Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from read_file_content import read_word_document
from validate_cosmic_table import extract_json_from_text
from main import call_ai, load_model_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def empty_validator(json_str: str) -> tuple[bool, str]:
    """空的校验函数"""
    return True, ""

def process_requirement_document(
    doc_path: Path,
    output_dir: Path,
    prompt: str
) -> Optional[str]:

    import pythoncom

    """处理单个需求文档并保存JSON结果"""
    # 检查是否已处理过
    output_path = output_dir / f"{doc_path.stem}.json"
    if output_path.exists():
        logger.info(f"跳过已处理文档: {doc_path}")
        return None
        
    pythoncom.CoInitialize()  # 初始化COM组件
    try:
        # 读取文档内容
        logger.info(f"正在处理文档: {doc_path}")
        content = read_word_document(str(doc_path))
        
        # 调用AI处理
        json_data = call_ai(
            ai_prompt=prompt,
            requirement_content=content,
            extractor=extract_json_from_text,
            validator=empty_validator,
            max_chat_count=5,
            config=load_model_config()
        )
        
        # 保存结果
        output_path = output_dir / f"{doc_path.stem}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_data)
        logger.info(f"已保存结果到: {output_path}")
        
        return json_data
    except Exception as e:
        logger.error(f"处理文档 {doc_path} 失败: {str(e)}")
        return None
    finally:
        pythoncom.CoUninitialize()  # 释放COM组件

def main():
    """主处理函数"""
    try:
        # 1. 读取AI提示词
        prompt_path = Path("ai_promote/requirement_extraction.md")
        prompt = open(prompt_path, "r", encoding="utf-8").read()
        
        # 2. 准备输入输出目录
        input_dir = Path(r"D:\shuchu\需求规格说明书")
        output_dir = Path("requirement_extraction_results")
        output_dir.mkdir(exist_ok=True)
        
        # 3. 使用线程池处理所有doc/docx文件
        doc_paths = []
        for ext in ["*.doc", "*.docx"]:
            doc_paths.extend(input_dir.glob(ext))
            
        # 设置线程池大小为5（可根据需要调整）
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = []
            for doc_path in doc_paths:
                future = executor.submit(
                    process_requirement_document,
                    doc_path,
                    output_dir,
                    prompt
                )
                futures.append((future, doc_path))
            
            for future, doc_path in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"处理文档 {doc_path} 时出错: {str(e)}")
                
    except Exception as e:
        logger.error(f"主流程执行失败: {str(e)}")
        raise

if __name__ == "__main__":
    main()
