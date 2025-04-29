import os
from pathlib import Path
from typing import Dict, Any

class ProcessingContext:
    """处理上下文，管理单个需求文件的全流程状态"""

    def __init__(self, input_path: str, developer: str):
        self.original_input_path = input_path  # 原始输入文件路径(不做处理)
        self.input_path = input_path  # 输入文件路径(后续会处理)
        self.developer = developer  # 开发人员目录名
        self.stem = Path(input_path).stem  # 文件名(无后缀)
        self.stage_data = {}  # 各阶段产出数据
        self.current_stage = 0  # 当前阶段索引
        self.success = True  # 处理状态
