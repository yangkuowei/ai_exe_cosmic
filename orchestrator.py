"""需求处理流程编排器 - 并发处理多个需求，每个需求内部串行"""
import logging
from pathlib import Path
from typing import List
import concurrent.futures # 导入并发库
# import os # Removed as it's no longer needed here

from create_cosmic_table import create_cosmic_table
from project_paths import ProjectPaths
from requirement_analysis import analyze_requirements
from create_trigger_events import create_trigger_events
# 导入后置处理函数
from post_processor import run_post_processing
# Removed unused imports: merge_temp_files, save_content_to_file, read_file_content, process_excel_files, re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Removed parse_analysis_file function as it was moved to post_processor.py

def get_doc_files(config: ProjectPaths) -> List[Path]:
    """获取所有需求文档文件"""
    doc_files = []
    # 扫描所有开发人员子目录
    for dev_dir in config.requirements.iterdir():
        if dev_dir.is_dir():
            doc_files.extend(list(dev_dir.glob("*.doc")) + list(dev_dir.glob("*.docx")))
    
    if not doc_files:
        raise FileNotFoundError(f"需求目录中未找到.doc或.docx文件: {config.requirements}")
    logger.info(f"发现 {len(doc_files)} 个需求文档待处理。")
    return doc_files

def process_single_requirement(doc_file: Path, config: ProjectPaths):
    """处理单个需求文档"""
    try:
        dev_name = doc_file.parent.name
        req_base = doc_file.stem
        req_name = f"{dev_name}/{req_base}"

        logger.info(f"开始处理需求: {req_name}") # 调整日志位置

        # 1. 需求分析 (串行步骤1)
        logger.info(f"[{req_name}] 阶段 1: 开始需求分析")
        analyze_requirements(req_name)

        # 2. 创建触发事件 (串行步骤2)
        logger.info(f"[{req_name}] 阶段 2: 开始创建触发事件")
        create_trigger_events(req_name)

        # 3. 创建COSMIC表 (串行步骤3)
        logger.info(f"[{req_name}] 阶段 3: 开始创建COSMIC表")
        create_cosmic_table(req_name)

        # 4. 后置处理 (串行步骤4) - 调用 post_processor
        run_post_processing(
            req_name=req_name,
            config=config,
            dev_name=dev_name,
            req_base=req_base,
            doc_file=doc_file # Pass the original doc_file Path object
        )

        logger.info(f"需求处理完成: {req_name}")

    except Exception as e:
        # 在并发任务中记录错误，异常会被 Future 捕获
        logger.error(f"处理需求失败 {req_name}: {str(e)}")
        # 不再显式 raise，让 concurrent.futures 处理异常传递

def main():
    """主处理流程 - 使用并发处理"""
    successful_tasks = 0
    failed_tasks = 0
    try:
        config = ProjectPaths()

        # 确保输出目录存在
        config.output.mkdir(parents=True, exist_ok=True)

        # 获取所有需求文档
        doc_files = get_doc_files(config)

        if not doc_files:
            logger.warning("未找到任何需求文档，流程结束。")
            return

        # 使用 ThreadPoolExecutor 实现并发处理
        # max_workers 可以根据需要调整，None 表示由 Python 自动决定
        with concurrent.futures.ThreadPoolExecutor(max_workers=None) as executor:
            # 提交所有任务到线程池
            future_to_doc = {executor.submit(process_single_requirement, doc_file, config): doc_file for doc_file in doc_files}
            logger.info(f"已提交 {len(future_to_doc)} 个需求处理任务到线程池。")

            # 等待任务完成并处理结果/异常
            for future in concurrent.futures.as_completed(future_to_doc):
                doc_file = future_to_doc[future]
                req_name = f"{doc_file.parent.name}/{doc_file.stem}"
                try:
                    # future.result() 会阻塞直到任务完成
                    # 如果任务内部抛出异常，result() 会重新抛出该异常
                    future.result()
                    logger.info(f"任务成功完成: {req_name}")
                    successful_tasks += 1
                except Exception as exc:
                    logger.error(f"任务执行失败 {req_name}: {exc}")
                    failed_tasks += 1

        logger.info(f"所有需求处理任务完成。成功: {successful_tasks}, 失败: {failed_tasks}")

    except FileNotFoundError as e: # 单独处理文件未找到的初始化错误
         logger.error(f"初始化错误: {str(e)}")
    except Exception as e:
        logger.error(f"需求处理主流程发生严重错误: {str(e)}")
        # 在顶层可以选择是否重新抛出，这里选择不抛出，仅记录日志

if __name__ == "__main__":
    main()
