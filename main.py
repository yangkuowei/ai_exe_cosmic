from datetime import datetime
from functools import partial
import re
import json
import shutil
from pathlib import Path
import logging
import argparse
from dataclasses import dataclass
import queue
import time

from ai_common import load_model_config
from langchain_openai_client_v1 import call_ai

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


@dataclass
class ProjectPaths:
    """项目路径配置"""
    base_dir: Path = Path(__file__).parent.resolve()
    ai_promote: Path = base_dir / "ai_promote"
    requirements: Path = base_dir / "requirements"
    output: Path = base_dir / "out_put_files"
    trigger_events_template: Path = ai_promote / "create_trigger_events.md"
    cosmic_table_template: Path = ai_promote / "create_cosmic_table_from_trigger_events.md"

    def __post_init__(self):
        """初始化时自动验证路径"""
        required_dirs = [self.ai_promote, self.requirements, self.output]
        missing = [str(d) for d in required_dirs if not d.exists()]
        if missing:
            raise FileNotFoundError(f"Missing required directories: {', '.join(missing)}")


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

        config = ProjectPaths()

        # 读取所有需求文件
        txt_files = list(config.requirements.glob("*.txt"))
        if not txt_files:
            raise FileNotFoundError(f"需求目录中未找到.txt文件: {config.requirements}")

        # 使用多进程处理所有需求文件
        from multiprocessing import Process
        processes = []
        
        for request_file in txt_files:
            logger.info(f"开始处理需求文件: {request_file}")
            requirement_content = read_file_content(str(request_file))
            
            # 创建新进程处理每个文件
            p = Process(target=process_single_requirement, 
                        args=(args, config, request_file, requirement_content))
            p.start()
            processes.append(p)
            time.sleep(30)
            
        # 等待所有进程完成
        for p in processes:
            p.join()
        
        return  # 主进程提前返回
    except Exception as e:
        logger.error(f"主进程执行失败: {str(e)}")
        raise

def process_single_requirement(args, config, request_file, requirement_content):
    """处理单个需求文件的进程函数"""
    try:
        # 提取表格行数要求
        total_rows = extract_content_from_requst(requirement_content)
        if total_rows is None:
            raise ValueError(f"需求文件中缺少表格总行数要求: {request_file.name}")

        # 提取需求名称
        request_name = extract_content_from_requst(requirement_content, extract_type='request_name')
        if request_name is None:
            raise ValueError(f"需求文件中缺少需求名称: {request_file.name}")

        logger.info(f"正在处理需求文件: {request_file.name}")

        json_str = ""
        output_path = config.output / request_file.stem

        # 改进阶段执行逻辑
        run_stage1 = args.stage1 or not args.stage2
        run_stage2 = args.stage2 or not args.stage1

        # 检查阶段1输出文件是否已存在
        base_name = request_file.name.split(".")[0]
        json_file = output_path / f"{base_name}.json"
        xlsx_file = output_path / f"{base_name}.xlsx"

        if run_stage1 and json_file.exists():
            logger.info(f"触发事件JSON文件已存在，跳过阶段1: {json_file}")
            json_str = read_file_content(str(json_file))
        elif run_stage1:
            # 阶段1：生成触发事件JSON
            json_str = generate_trigger_events(
                prompt=load_prompt_template(config.trigger_events_template),
                requirement=requirement_content,
                total_rows=total_rows,
                output_dir=config.output,
                request_file=request_file
            )
        elif run_stage2:
            # 尝试读取已存在的JSON文件
            if not json_file.exists():
                raise FileNotFoundError(f"未找到阶段1输出文件，请先执行阶段1: {json_file}")
            json_str = read_file_content(str(json_file))

        if run_stage2 and xlsx_file.exists():
            logger.info(f"Excel表格文件已存在，跳过阶段2: {xlsx_file}")
        elif run_stage2:
            # 阶段2：生成COSMIC表格
            generate_cosmic_table(
                prompt=load_prompt_template(config.cosmic_table_template),
                base_content=requirement_content,
                json_data=json_str,
                output_dir=config.output,
                request_file=request_file,
                request_name=request_name
            )

    except (FileNotFoundError, ValueError) as e:
        logger.error(f"初始化失败: {str(e)}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"未处理的异常: {str(e)}")
        raise RuntimeError("程序执行异常") from e


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

    json_data = call_ai(
        ai_prompt=prompt,
        requirement_content=requirement,
        extractor=extract_json_from_text,
        validator=validator,
        max_chat_count=5,
        config=load_model_config()
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
) -> None:
    """生成COSMIC表格（支持分批处理及独立执行）
    
    参数:
        prompt: AI提示模板
        base_content: 原始需求内容
        json_data: 触发事件JSON数据（字符串格式）
        output_dir: 输出目录
        request_file: 原始需求文件路径
        batch_size: 每批处理事件数（默认5）
        
    执行逻辑:
        1. 检查输入JSON数据有效性
        2. 创建临时目录
        3. 分批处理并生成中间文件
        4. 合并结果并生成最终文件
        5. 保存校验报告
    """
    logger.info("开始生成COSMIC表格...")

    try:
        # 解析原始JSON数据
        cosmic_data = json.loads(json_data)
        # 创建临时目录 (使用需求文件名作为目录名)
        temp_dir = output_dir / f"temp_{request_file.stem}"
        temp_dir.mkdir(exist_ok=True)

        # 结果队列
        result_queue = queue.Queue()
        from concurrent.futures import ThreadPoolExecutor, as_completed

        event_idx = 0
        # 使用线程池管理并发
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            
            # 遍历每个需求
            for req in cosmic_data["functional_user_requirements"]:
                requirement_name = req["requirement"]
                req_events = req["trigger_events"]

                # 处理每个触发事件
                for idx, event in enumerate(req_events):
                    # 提交任务到线程池
                    future = executor.submit(
                        process_single_event,
                        event,
                        requirement_name,
                        request_file,
                        temp_dir,
                        base_content,
                        prompt,
                        request_name,
                        result_queue,
                        event_idx
                    )
                    futures.append(future)
                    event_idx += 1
                    time.sleep(10)  # 添加10秒延迟

            # 等待所有任务完成
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"线程执行出错: {str(e)}")

        # 移除原有的5秒延迟

        # 收集结果
        temp_files = []
        while not result_queue.empty():
            temp_files.append(result_queue.get())

        if event_idx != len(temp_files):
            raise ValueError("部分COSMIC表格生成失败！")
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


def process_single_event(
        event,
        requirement_name,
        request_file,
        temp_dir,
        base_content,
        prompt,
        request_name,
        result_queue,
        event_idx: int = 0
):
    """处理单个触发事件的线程函数"""
    try:
        temp_filename = f"{request_file.stem}_event{event_idx}.md"
        temp_path = temp_dir / temp_filename

        # 检查文件是否已存在
        if temp_path.exists():
            print(f"文件 {temp_filename} 已存在，跳过处理")
            result_queue.put(temp_path)
            return

        # 构建单个触发事件的JSON
        event_json = {
            "functional_user_requirements": [{
                "requirement": requirement_name,
                "trigger_events": [event]
            }]
        }

        # 计算本事件的功能过程数量
        total_processes = sum(
            len(e["functional_processes"])
            for req in event_json["functional_user_requirements"]
            for e in req["trigger_events"]
        )

        # 生成动态行数范围
        min_rows = total_processes * 3
        row_range = min_rows

        # 更新基础内容中的行数要求
        content_lines = base_content.splitlines()
        for i in reversed(range(len(content_lines))):
            if "表格总行数要求：" in content_lines[i]:
                content_lines[i] = re.sub(
                    r"(\d+)(行左右)",
                    f"{row_range}行（根据功能过程数量动态计算）",
                    content_lines[i]
                )
                break

        updated_content = '\n'.join(content_lines)

        # 生成分批内容
        combined_content = f"{updated_content}\n结合需求背景、详细方案设计按照以下触发事件与功能过程列表生成符合规范的cosmic表格：\n{json.dumps(event_json, ensure_ascii=False, indent=2)}"

        # 调用AI生成表格
        validator = partial(validate_cosmic_table, request_name=request_name)
        markdown_table = call_ai(
            ai_prompt=prompt,
            requirement_content=combined_content,
            extractor=extract_table_from_text,
            validator=validator,
            config=load_model_config()
        )

        # 保存临时文件
        save_content_to_file(
            file_name=temp_filename,
            output_dir=str(temp_dir),
            content=markdown_table,
            content_type="markdown"
        )

        result_queue.put(temp_path)

    except Exception as e:
        logger.error(f"处理事件失败: {str(e)}")


if __name__ == "__main__":
    try:
        main()
    finally:
        exit(1)
