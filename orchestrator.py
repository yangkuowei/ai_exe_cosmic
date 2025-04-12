"""需求处理流程编排器 - 串联三个处理步骤"""
import logging
from pathlib import Path
from typing import List

from project_paths import ProjectPaths
from requirement_analysis import analyze_requirements
from create_trigger_events import create_trigger_events
from create_cosmic_table import main as create_cosmic_table

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_doc_files(config: ProjectPaths) -> List[Path]:
    """获取所有需求文档文件"""
    doc_files = []
    # 扫描所有开发人员子目录
    for dev_dir in config.requirements.iterdir():
        if dev_dir.is_dir():
            doc_files.extend(list(dev_dir.glob("*.doc")) + list(dev_dir.glob("*.docx")))
    
    if not doc_files:
        raise FileNotFoundError(f"需求目录中未找到.doc或.docx文件: {config.requirements}")
    return doc_files

def process_single_requirement(doc_file: Path, config: ProjectPaths):
    """处理单个需求文档"""
    try:
        dev_name = doc_file.parent.name
        req_base = doc_file.stem
        req_name = f"{dev_name}/{req_base}"
        
        # 1. 需求分析
        logger.info(f"开始需求分析: {req_name}")
        analyze_requirements(req_name)
        
        # 2. 创建触发事件
        logger.info(f"开始创建触发事件: {req_name}")
        create_trigger_events(req_name)
        
        # 3. 创建COSMIC表
        logger.info(f"开始创建COSMIC表: {req_name}")
        # 修改create_cosmic_table调用方式
        from create_cosmic_table import main as create_cosmic_table_main
        create_cosmic_table_main(req_name)
        
        logger.info(f"需求处理完成: {req_name}")
        
    except Exception as e:
        logger.error(f"处理需求失败 {req_name}: {str(e)}")
        raise

def main():
    """主处理流程"""
    try:
        config = ProjectPaths()
        
        # 确保输出目录存在
        config.output.mkdir(parents=True, exist_ok=True)
        
        # 获取所有需求文档
        doc_files = get_doc_files(config)
        
        # 处理每个需求文档
        for doc_file in doc_files:
            process_single_requirement(doc_file, config)
            
    except Exception as e:
        logger.error(f"需求处理流程失败: {str(e)}")
        raise

if __name__ == "__main__":
    main()
