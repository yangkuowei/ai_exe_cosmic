from datetime import datetime
from functools import partial
import re
import json
import shutil
from pathlib import Path
import logging
import argparse

from cosmic_ai_cline import call_ai, load_model_config

from read_file_content import (
    read_file_content,
    save_content_to_file,
    extract_content_from_requst, merge_temp_files
)
from validate_cosmic_table import (
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
    """主业务流程（支持分阶段执行）
    
    命令行参数:
        --stage1   仅执行阶段1（生成触发事件JSON）
        --stage2   仅执行阶段2（生成COSMIC表格）
        默认同时执行两个阶段
    """
    try:
        # 解析命令行参数
        parser = argparse.ArgumentParser()
        parser.add_argument('--stage1', action='store_true', help='仅执行阶段1（生成触发事件JSON）')
        parser.add_argument('--stage2', action='store_true', help='仅执行阶段2（生成COSMIC表格）')
        args = parser.parse_args()

        config = ProjectConfig()
        config.validate_paths()

        # 读取需求文件（自动获取最新或通过参数指定）

        # 自动获取requirements目录下最新的.txt文件
        txt_files = list(config.requirements_dir.glob("*.txt"))
        if not txt_files:
            raise FileNotFoundError(f"需求目录中未找到.txt文件: {config.requirements_dir}")

        # 按修改时间排序获取最新文件
        txt_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        request_file = txt_files[0]

        if len(txt_files) > 1:
            logger.warning(f"检测到多个需求文件，已选择最新文件: {request_file.name}")

        logger.info(f"正在使用需求文件: {request_file}")
        requirement_content = read_file_content(str(request_file))

        # 提取表格行数要求
        total_rows = extract_content_from_requst(requirement_content)
        if total_rows is None:
            raise ValueError(f"需求文件中缺少表格总行数要求: {request_file.name}")

        # 提取需求名称
        request_name = extract_content_from_requst(requirement_content, extract_type='request_name')
        if request_name is None:
            raise ValueError(f"需求文件中缺少需求名称: {request_file.name}")

        logger.info(f"成功读取需求文件: {request_file.name}")

        json_str = ""
        output_path = config.output_dir / request_file.stem

        # 阶段执行逻辑
        run_stage1 = args.stage1 or (not args.stage1 and not args.stage2)
        run_stage2 = args.stage2 or (not args.stage1 and not args.stage2)

        # run_stage1 = False
        if run_stage1:
            # 阶段1：生成触发事件JSON
            json_str = generate_trigger_events(
                prompt=load_prompt_template(config.trigger_events_template),
                requirement=requirement_content,
                total_rows=total_rows,
                output_dir=config.output_dir,
                request_file=request_file
            )
        elif run_stage2:
            # 尝试读取已存在的JSON文件
            base_name = request_file.name.split(".")[0]
            json_file = output_path / f"{base_name}.json"
            if not json_file.exists():
                raise FileNotFoundError(f"未找到阶段1输出文件，请先执行阶段1: {json_file}")
            json_str = read_file_content(str(json_file))

        if run_stage2:
            # 阶段2：生成COSMIC表格
            generate_cosmic_table(
                prompt=load_prompt_template(config.cosmic_table_template),
                base_content=requirement_content,
                json_data=json_str,
                output_dir=config.output_dir,
                request_file=request_file,
                request_name=request_name
            )

    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}")
        raise


from decorators import ai_processor

@ai_processor(max_retries=3)
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
    
    def stream_callback(content: str):
        """流式响应回调示例"""
        print(content, end='', flush=True)

    json_data = call_ai(
        ai_prompt=prompt,
        requirement_content=requirement,
        extractor=extract_json_from_text,
        validator=validator,
        config=load_model_config(),
        stream_callback=stream_callback
    )

    output_path = output_dir / request_file.stem
    save_content_to_file(
        file_name=request_file.name,
        output_dir=str(output_path),
        content=json_data,
        content_type="json"
    )

    logger.info(f"触发事件已保存至: {output_path}")
    return json_data

@ai_processor(max_retries=3)
def generate_cosmic_table(
        prompt: str,
        base_content: str,
        json_data: str,
        output_dir: Path,
        request_file: Path,
        request_name: str,
        batch_size: int = 3,
) -> None:
    """生成COSMIC表格（支持分批处理及独立执行）
    
    参数:
        prompt: AI提示模板
        base_content: 原始需求内容
        json_data: 触发事件JSON数据（字符串格式）
        output_dir: 输出目录
        request_file: 原始需求文件路径
        batch_size: 每批处理事件数（默认3）
        
    执行逻辑:
        1. 检查输入JSON数据有效性
        2. 创建临时目录
        3. 分批处理并生成中间文件
        4. 合并结果并生成最终文件
        5. 保存校验报告
    """
    logger.info("开始生成COSMIC表格...")

    try:
        def stream_callback(content: str):
            """流式响应回调示例"""
            print(content, end='', flush=True)

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
                batch_events = req_events[i:i + batch_size]

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
                min_rows = total_processes * 3
                max_rows = total_processes * 4
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
                validator = partial(validate_cosmic_table, request_name=request_name)
                markdown_table = call_ai(
                    ai_prompt=prompt,
                    requirement_content=combined_content,
                    extractor=extract_table_from_text,
                    validator=validator,
                    config=load_model_config(),  # 添加必需的config参数
                    stream_callback=stream_callback
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

        # 校验并保存校验结果
        is_valid, messages = validate_cosmic_table(full_table, request_name)
        result_content = f"校验时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        result_content += f"校验结果：{'通过' if is_valid else '失败'}\n"
        result_content += "详细信息：\n" + "".join(messages)

        # 保存校验结果文件
        result_filename = f"{request_file.stem}_resultcheck.txt"
        save_content_to_file(
            file_name=result_filename,
            output_dir=str(output_path),
            content=result_content,
            content_type="text"
        )

        # 生成Excel和Word
        # processed_table = process_markdown_table(full_table)
        for file_type in ["xlsx", "docx"]:
            save_content_to_file(
                file_name=request_file.name,
                output_dir=str(output_path),
                content=full_table,
                content_type=file_type
            )

        # 清理临时文件
        shutil.rmtree(temp_dir)
        logger.info(f"COSMIC表格已保存至: {output_path}")

    except Exception as e:
        logger.error(f"COSMIC表格生成失败: {str(e)}")
        raise


if __name__ == "__main__":
    main()
    exit(1)
