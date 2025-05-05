import os
import concurrent.futures
from concurrent.futures import as_completed
import logging
from typing import Optional, Tuple, Callable
from pathlib import Path

from ai_common import load_model_config
from decorators import ai_processor
from .context import ProcessingContext
from cosmic_processor.config import DEVELOPERS, TEMPLATE_PATHS, INPUT_FILE_EXTENSIONS, FILE_NAME
from cosmic_processor.utils.extractors import extract_json_from_text, extract_table_from_text
from cosmic_processor.utils.validators import validate_requirement_analysis_json, validate_cosmic_table
from cosmic_processor.stages import (
    requirement_extraction,
    process_requirement_analysis,
    process_generate_cosmic,
    process_necessity, process_excel
)

class CosmicPipeline:
    """COSMIC处理流水线"""

    def __init__(
        self, 
        max_workers: int = 24,
        json_extractor: Callable[[str], str] = extract_json_from_text,
        table_extractor: Callable[[str], str] = extract_table_from_text,
        json_validator: Callable[[str], Tuple[bool, str]] = validate_requirement_analysis_json,
        table_validator: Callable[[str, Optional[int]], Tuple[bool, str]] = validate_cosmic_table
    ):
        self.max_workers = max_workers
        self.max_workers_analysis = max_workers
        self.model_config = load_model_config()
        self.model_config_extraction = load_model_config("aliyun")
        self.json_extractor = json_extractor
        self.table_extractor = table_extractor 
        self.json_validator = json_validator
        self.table_validator = table_validator
        
        # 初始化日志
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # 阻止传播到root logger
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # 从配置读取提示词模板和路径
        self.requirement_extraction_prompt = self._read_prompt(TEMPLATE_PATHS["requirement_extraction"])
        self.requirement_prompt = self._read_prompt(TEMPLATE_PATHS["requirement_analysis"])
        self.cosmic_prompt = self._read_prompt(TEMPLATE_PATHS["cosmic_table"])
        self.necessity_prompt = self._read_prompt(TEMPLATE_PATHS["necessity"])
        self.output_base_dir = TEMPLATE_PATHS.get("output_base_dir", "out_put_files")
        self.out_template_base_dir = TEMPLATE_PATHS.get("out_template_base_dir", "out_template")

    def _read_prompt(self, path: str) -> str:
        """读取提示词文件"""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _process_file(self, input_path: str, developer: str):
        """处理单个文件"""
        context = ProcessingContext(input_path, developer)

        steps = [
            self._init_processing,
            self._pre_process,
            requirement_extraction,
            process_requirement_analysis,
            process_generate_cosmic,
            process_necessity,
            process_excel,
            self._post_process
        ]

        for step in steps:
            if not step(self, context):
                context.success = False
                break

    def _print_progress(self, current: int, total: int):
        """打印进度条"""
        progress = current / total
        bar_length = 40
        filled = int(bar_length * progress)
        bar = '=' * filled + ' ' * (bar_length - filled)
        self.logger.info(f'\r[{bar}] {current}/{total} ({progress:.0%})')

    @ai_processor(max_retries=1)
    def run(self):
        """启动处理流程"""
        # 获取所有需求文件(仅处理白名单开发人员)
        req_files = []
        for developer in os.listdir('requirements'):
            if developer not in DEVELOPERS:
                continue

            dev_dir = os.path.join('requirements', developer)
            if os.path.isdir(dev_dir):
                for file in os.listdir(dev_dir):
                    if any(file.endswith(ext) for ext in INPUT_FILE_EXTENSIONS):
                        req_files.append((os.path.join(dev_dir, file), developer))

        total_files = len(req_files)
        if total_files == 0:
            self.logger.info("没有找到需要处理的需求文件")
            return

        self.logger.info(f"开始处理 {total_files} 个需求文件...")
        completed = 0

        # 使用线程池处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._process_file, path, dev): (path, dev) for path, dev in req_files}
            
            # 初始化进度条
            self._print_progress(0, total_files)
            
            for future in as_completed(futures):
                future.result()
                completed += 1
                self._print_progress(completed, total_files)

    def _init_processing(self, pipeline, context: ProcessingContext) -> bool:
        """初始化处理"""
        context.stage_data['output_dir'] = os.path.join(pipeline.output_base_dir, context.developer)
        os.makedirs(context.stage_data['output_dir'], exist_ok=True)
        return True

    def _pre_process(self, pipeline, context: ProcessingContext) -> bool:
        # 处理stem部分
        context.stem = Path(context.input_path).stem.strip()
        # 更新input_path为处理后的路径(去掉扩展名前后的空格)
        path_obj = Path(context.original_input_path)
        context.input_path = str(path_obj.with_name(context.stem + path_obj.suffix))
        return True

    def _post_process(self, pipeline, context: ProcessingContext) -> bool:
        """后置处理(预留)"""
        return True

    def _extract_json_from_text(self, text: str) -> str:
        """从文本提取JSON"""
        return self.json_extractor(text)

    def _validate_requirement_analysis_json(self, json_str: str) -> Tuple[bool, str]:
        """验证需求分析JSON"""
        return self.json_validator(json_str)

    def _extract_table_from_text(self, text: str) -> str:
        """从文本提取表格"""
        return self.table_extractor(text)

    def _validate_cosmic_table(self, markdown_table_str: str, table_rows: Optional[int] = None) -> Tuple[bool, str]:
        """验证COSMIC表格"""
        return self.table_validator(markdown_table_str, table_rows)

    def _extract_text(self, text: str) -> str:
        """从AI回复中提取```text ```标记之间的内容"""
        import re
        match = re.search(r'```text\n(.*?)\n```', text, re.DOTALL)
        return match.group(1) if match else text

    def _validate_empty(self, text: str) -> Tuple[bool, str]:
        """空验证器"""
        return True, ''
