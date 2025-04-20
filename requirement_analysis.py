import os
import threading
import concurrent.futures
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json

from ai_common import load_model_config
from project_paths import DEVELOPERS, TEMPLATE_PATHS, INPUT_FILE_EXTENSIONS, FILE_NAME
from my_openai_client import call_ai, ModelConfig
from read_file_content import read_word_document, save_content_to_file
from validate.validate_cosmic_table import validate_cosmic_table
from validate.validate_requirement_analysis_json import validate_requirement_analysis_json
from validate_cosmic_table import extract_json_from_text, extract_table_from_text


class ProcessingContext:
    """处理上下文，管理单个需求文件的全流程状态"""
    def __init__(self, input_path: str, developer: str):
        self.input_path = input_path  # 输入文件路径
        self.developer = developer    # 开发人员目录名
        self.stem = Path(input_path).stem  # 文件名(无后缀)
        self.stage_data = {}          # 各阶段产出数据
        self.current_stage = 0        # 当前阶段索引
        self.success = True           # 处理状态

class CosmicPipeline:
    """COSMIC处理流水线"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.model_config = load_model_config()
        
        # 从配置读取提示词模板
        self.requirement_prompt = self._read_prompt(TEMPLATE_PATHS["requirement_analysis"])
        self.cosmic_prompt = self._read_prompt(TEMPLATE_PATHS["cosmic_table"])

    def _read_prompt(self, path: str) -> str:
        """读取提示词文件"""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def _init_processing(self, context: ProcessingContext) -> bool:
        """初始化处理"""
        context.stage_data['output_dir'] = f"out_put_files/{context.developer}"
        os.makedirs(context.stage_data['output_dir'], exist_ok=True)
        return True

    def _pre_process(self, context: ProcessingContext) -> bool:
        """前置处理(预留)"""
        return True

    def _post_process(self, context: ProcessingContext) -> bool:
        """后置处理(预留)"""
        return True

    def _process_requirement_analysis(self, context: ProcessingContext) -> bool:
        """需求分析阶段"""
        try:
            # 从输入文件名提取需求目录名（去掉后缀）
            requirement_dir = Path(context.input_path).stem
            
            # 构建完整输出路径
            output_path = f"{context.stage_data['output_dir']}/{requirement_dir}"
            os.makedirs(output_path, exist_ok=True)
            
            # 检查输出文件是否已存在
            full_file_name = f"{output_path}/{FILE_NAME['requirement_json']}"
            if os.path.exists(full_file_name):
                print(f"需求分析文件已存在，跳过处理: {full_file_name}")
                with open(full_file_name, 'r', encoding='utf-8') as f:
                    context.stage_data['requirement_json'] = f.read()
                return True
            
            # 读取需求文档内容
            content = read_word_document(context.input_path)
            
            # 调用AI分析
            json_data = call_ai(
                ai_prompt=self.requirement_prompt,
                requirement_content=content,
                extractor=self._extract_json_from_text,
                validator=self._validate_requirement_analysis_json,
                config=self.model_config
            )
            
            # 保存结果
            save_content_to_file(
                file_name=FILE_NAME['requirement_json'],
                output_dir=output_path,
                content=json_data,
                content_type="json"
            )
            
            context.stage_data['requirement_json'] = json_data
            return True
            
        except Exception as e:
            print(f"需求分析失败: {str(e)}")
            return False

    def _process_generate_cosmic(self, context: ProcessingContext) -> bool:
        """生成COSMIC表格阶段"""
        try:
            # 构建完整输出路径
            requirement_dir = Path(context.input_path).stem
            output_path = f"{context.stage_data['output_dir']}/{requirement_dir}"
            os.makedirs(output_path, exist_ok=True)
            
            # 检查输出文件是否已存在
            full_file_name = f"{output_path}/{FILE_NAME['cosmic_table']}"
            if os.path.exists(full_file_name):
                print(f"COSMIC表格文件已存在，跳过处理: {full_file_name}")
                return True
            
            # 调用AI生成表格
            markdown_table = call_ai(
                ai_prompt=self.cosmic_prompt,
                requirement_content=context.stage_data['requirement_json'],
                extractor=self._extract_table_from_text,
                validator=self._validate_cosmic_table,
                config=self.model_config
            )
            
            # 保存结果
            save_content_to_file(
                file_name=FILE_NAME['cosmic_table'],
                output_dir=output_path,
                content=markdown_table,
                content_type="markdown"
            )

            return True
            
        except Exception as e:
            print(f"生成表格失败: {str(e)}")
            return False

    def _process_file(self, input_path: str, developer: str):
        """处理单个文件"""
        context = ProcessingContext(input_path, developer)
        
        steps = [
            self._init_processing,
            self._pre_process,
            self._process_requirement_analysis,
            self._process_generate_cosmic,
            self._post_process
        ]
        
        for step in steps:
            if not step(context):
                context.success = False
                break

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
        
        # 使用线程池处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._process_file, path, dev) for path, dev in req_files]
            concurrent.futures.wait(futures)

    # 以下为工具方法(需实现)
    def _extract_json_from_text(self, text: str) -> str:
        """从文本提取JSON"""
        # 实现JSON提取逻辑
        return extract_json_from_text(text)

    def _validate_requirement_analysis_json(self, json_str: str) -> Tuple[bool, str]:
        """验证需求分析JSON"""
        # 实现验证逻辑
        return validate_requirement_analysis_json(json_str)

    def _extract_table_from_text(self, text: str) -> str:
        """从文本提取表格"""
        # 实现表格提取逻辑
        return extract_table_from_text(text)

    def _validate_cosmic_table(self, markdown_table_str: str) -> Tuple[bool, str]:
        """验证COSMIC表格"""
        # 实现验证逻辑
        return validate_cosmic_table(markdown_table_str)

if __name__ == '__main__':
    pipeline = CosmicPipeline()
    pipeline.run()
