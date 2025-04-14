import json
import os
import concurrent.futures
import time
import math # Added import
import shutil # Added import
from functools import partial
from typing import List, Dict, Any
from pathlib import Path

from ai_common import load_model_config
from langchain_openai_client_v1 import call_ai
from decorators import ai_processor
from project_paths import ProjectPaths
from validate_cosmic_table import validate_cosmic_table, extract_table_from_text
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging # 导入日志模块

# 获取 logger 实例 (确保日志已在别处配置，例如 orchestrator.py)
logger = logging.getLogger(__name__)

# 定义每个拆分文件的目标功能流程数量阈值 (新规则)
SPLIT_PROCESS_THRESHOLD = 20

def read_prompt_file(prompt_path: str) -> str:
    """读取AI提示词文件"""
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def read_business_req(business_req_path: str) -> str:
    """读取业务需求文本文件"""
    with open(business_req_path, 'r', encoding='utf-8') as f:
        return f.read()

def read_trigger_event_files(trigger_events_dir: str, parent_dir_for_table_check: str) -> List[Dict[str, Any]]:
    """
    Reads processed trigger event JSON files from the specified subdirectory,
    skipping those whose corresponding table file already exists in the parent directory.
    Args:
        trigger_events_dir: The directory containing the processed trigger_events_*.json files.
        parent_dir_for_table_check: The main output directory where table_cosmic_*.md files are stored.
    Returns:
        A list of dictionaries, each representing a trigger event to be processed.
    """
    trigger_events_path = Path(trigger_events_dir)
    parent_output_path = Path(parent_dir_for_table_check)

    if not trigger_events_path.is_dir():
        logger.warning(f"未找到触发事件目录: {trigger_events_path}")
        return []

    # 从特定子目录直接列出文件
    try:
        trigger_files = [
            f for f in os.listdir(trigger_events_path)
            if f.startswith('trigger_events') and f.endswith('.json') and os.path.isfile(trigger_events_path / f)
        ]
    except FileNotFoundError:
        logger.warning(f"列出触发事件目录中的文件时出错: {trigger_events_path}")
        return []

    # 从*父*目录获取已存在的表格文件
    try:
        existing_tables = {
            f for f in os.listdir(parent_output_path)
            if f.startswith('table_cosmic_') and f.endswith('.md') and os.path.isfile(parent_output_path / f)
        }
        logger.debug(f"在父目录 {parent_output_path} 中找到已存在的表格文件: {existing_tables}")
    except FileNotFoundError:
        logger.warning(f"未找到用于表格检查的父目录: {parent_output_path}")
        existing_tables = set() # Assume no tables exist if parent dir is missing


    # 在处理前按后缀数字排序文件
    try:
        trigger_files.sort(key=lambda x: int(Path(x).stem.split('_')[-1]))
    except ValueError as e:
        logger.error(f"排序触发文件时出错 - 文件名可能不以'_<number>.json'结尾: {e}. 文件列表: {trigger_files}")
        # Decide how to handle: return empty, process unsorted, or try alternative sorting?
        # For now, log the error and proceed with potentially unsorted/incomplete list.

    events = []
    processed_indices = set() # 跟踪已添加的索引

    for file_name in trigger_files:
        try:
            event_num_str = Path(file_name).stem.split('_')[-1]
            if not event_num_str.isdigit():
                logger.warning(f"无法从文件名中提取有效的数字索引: {file_name}. 跳过处理")
                continue
            event_num = int(event_num_str)

            # Check against existing tables in the parent output directory
            table_file_name = f"table_cosmic_{event_num}.md"

            if table_file_name not in existing_tables:
                if event_num not in processed_indices:
                    file_path = trigger_events_path / file_name # 使用正确的目录路径
                    logger.debug(f"正在读取事件文件: {file_path}")
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            event_data = json.load(f)
                            event_data['file_name'] = file_name # 存储来自trigger_events子目录的文件名
                            events.append(event_data)
                            processed_indices.add(event_num)
                    except json.JSONDecodeError:
                        logger.error(f"解码JSON文件时出错: {file_path}")
                    except Exception as e:
                        logger.error(f"读取文件时出错 {file_path}: {e}")
                # else: # No need for this warning if sorting works correctly
                #     logger.warning(f"Skipping file {file_name} as index {event_num} was already processed.")
            else:
                 logger.info(f"跳过事件文件 {file_name}，因为对应的表格 {table_file_name} 已存在于 {parent_output_path} 中")
        except Exception as e:
            # Catch potential errors in splitting filename or converting to int
            logger.error(f"处理文件条目 {file_name} 时发生意外错误: {e}", exc_info=True)

    logger.info(f"从目录 {trigger_events_path} 中找到 {len(events)} 个待处理的触发事件")
    return events

def preprocess_trigger_events(output_dir: Path, req_base: str):
    """
    Preprocesses original trigger event files based on cumulative functional process count.
    Groups trigger_events into batches aiming for SPLIT_PROCESS_THRESHOLD processes per file.
    Saves processed files to a 'trigger_events' subdirectory with global sequential numbering.
    """
    split_output_dir = output_dir / 'trigger_events'
    os.makedirs(split_output_dir, exist_ok=True)
    logger.info(f"已确保 'trigger_events' 子目录存在: {split_output_dir}")

    original_trigger_files = [
        f for f in os.listdir(output_dir)
        if f.startswith(f'trigger_events_{req_base}_') and f.endswith('.json') and os.path.isfile(output_dir / f)
    ]
    original_trigger_files.sort(key=lambda x: int(x.split('_')[-1].split('.')[0]))
    logger.info(f"已找到并排序 {len(original_trigger_files)} 个原始触发事件JSON文件")

    global_event_index = 1
    for original_file_name in original_trigger_files:
        original_file_path = output_dir / original_file_name
        logger.debug(f"正在处理原始文件: {original_file_path}")
        try:
            with open(original_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not data.get('functional_user_requirements'):
                logger.warning(f"文件 {original_file_name} 缺少 'functional_user_requirements'。跳过。")
                continue

            req_info = data['functional_user_requirements'][0]
            original_events = req_info.get('trigger_events', [])
            if not original_events:
                logger.warning(f"文件 {original_file_name} 在 'functional_user_requirements' 中缺少 'trigger_events'。跳过。")
                continue

            current_batch_events = []
            current_batch_process_count = 0

            # Helper function to save a batch
            def save_batch(batch_events, batch_process_count):
                nonlocal global_event_index
                if not batch_events:
                    return

                new_event_data = {
                    "functional_user_requirements": [
                        {
                            "requirement": req_info.get("requirement", ""),
                            "functionalUser": req_info.get("functionalUser", {}).copy(),
                            "trigger_events": batch_events,
                            "tableRows": math.ceil(batch_process_count * 2.75) # Calculate based on batch total
                        }
                    ]
                }
                new_filename = f"trigger_events_{req_base}_{global_event_index}.json"
                new_filepath = split_output_dir / new_filename
                with open(new_filepath, 'w', encoding='utf-8') as outfile:
                    json.dump(new_event_data, outfile, indent=2, ensure_ascii=False)
                logger.info(f"已保存批次到: {new_filepath}，包含 {len(batch_events)} 个事件，{batch_process_count} 个流程，tableRows={new_event_data['functional_user_requirements'][0]['tableRows']}")
                global_event_index += 1

            # Iterate through events in the current original file
            for event in original_events:
                event_process_count = len(event.get('functional_processes', []))

                # Rule 1: If a single event meets/exceeds threshold
                if event_process_count >= SPLIT_PROCESS_THRESHOLD:
                    # Save the current batch *before* this large event
                    save_batch(current_batch_events, current_batch_process_count)
                    current_batch_events = []
                    current_batch_process_count = 0
                    # Save the large event as its own batch
                    save_batch([event], event_process_count)
                # Rule 2: If adding the event meets/exceeds threshold AND the current batch is not empty
                elif current_batch_events and (current_batch_process_count + event_process_count >= SPLIT_PROCESS_THRESHOLD):
                    # Save the current batch *before* adding this event
                    save_batch(current_batch_events, current_batch_process_count)
                    # Start a new batch with the current event
                    current_batch_events = [event]
                    current_batch_process_count = event_process_count
                # Otherwise, add the event to the current batch (or start a new batch if it's the first event)
                else:
                    current_batch_events.append(event)
                    current_batch_process_count += event_process_count

            # Save any remaining events in the last batch for this file
            save_batch(current_batch_events, current_batch_process_count)

        except json.JSONDecodeError:
            logger.error(f"解码原始JSON文件时出错: {original_file_path}")
        except Exception as e:
            logger.error(f"处理文件 {original_file_name} 时发生意外错误: {e}", exc_info=True)

    logger.info(f"触发事件预处理完成。共生成 {global_event_index - 1} 个处理/拆分后的JSON文件")


def process_single_event(
    ai_prompt: str,
    business_req: str, # Keep business_req for context if needed by AI, though current combined_content overrides it
    event_data: Dict[str, Any],
    output_dir: Path # Changed to Path for consistency
) -> Path: # Return Path
    """处理单个触发事件（来自预处理后的文件）并保存结果"""
    try:
        # Ensure event_data is not empty and has the expected structure
        if not event_data or 'functional_user_requirements' not in event_data or not event_data['functional_user_requirements']:
             logger.error(f"事件数据结构无效: {event_data.get('file_name', 'unknown')}。跳过处理")
             return None # Indicate failure or skip

        # Extract tableRows from the potentially modified event data
        table_rows = event_data['functional_user_requirements'][0].get('tableRows', 0) # Use .get for safety
        if table_rows == 0:
             logger.warning(f"tableRows 为0或缺失: {event_data.get('file_name', 'unknown')}。继续处理，但AI可能需要调整")

        # Use only the event data JSON as input for the AI, as per the original commented-out line
        # The business_req might still be useful contextually, but the prompt focuses on the JSON.
        combined_content = json.dumps(event_data, indent=2, ensure_ascii=False)
        combined_content = f"完整业务需求:\n{business_req}\n\n本次生成表格仅处理此JSON中定义的内容和行数：\n{json.dumps(event_data, indent=2, ensure_ascii=False)}"


        # 调用AI生成表格
        # Ensure validator uses the potentially recalculated table_rows
        validator = partial(validate_cosmic_table, expected_total_rows=table_rows)
        markdown_table = ai_processor()(
            call_ai
        )(
            ai_prompt=ai_prompt,
            requirement_content=combined_content,
            extractor=extract_table_from_text,
            validator=validator,
            max_chat_count = 5,
            config=load_model_config()
        )

        if markdown_table is None:
             logger.error(f"AI生成表格失败: {event_data.get('file_name', 'unknown')}")
             return None # Indicate failure

        # 保存结果文件
        # Extract the number from the processed filename (e.g., trigger_events_reqname_5.json -> 5)
        event_num_str = Path(event_data['file_name']).stem.split('_')[-1]
        if not event_num_str.isdigit():
             logger.error(f"无法从文件名中提取有效的事件编号: {event_data['file_name']}")
             # Fallback or error handling needed - maybe use a default or skip?
             # For now, let's try to proceed but log prominently.
             event_num_str = "unknown" # Or raise an error

        # Save the table to the main output_dir, not the trigger_events subdir
        output_path = output_dir / f"table_cosmic_{event_num_str}.md"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_table)

        return output_path
    except KeyError as e:
        logger.error(f"事件数据中缺少关键字段 {e}: {event_data.get('file_name', 'unknown')}。事件数据: {event_data}")
        return None
    except Exception as e:
        logger.error(f"处理单个事件时出错: {event_data.get('file_name', 'unknown')}。错误: {e}", exc_info=True)
        return None

def create_cosmic_table(req_name: str = None):
    """主处理流程
    Args:
        req_name: 需求名称，用于指定要处理的需求目录
    """
    config = ProjectPaths()
    prompt_path = config.ai_promote / "create_cosmic_table_from_trigger_events.md"
    
    if req_name is None:
        raise ValueError("必须提供req_name参数")
        
    # 处理req_name格式: "开发人员姓名/需求名称"
    if '/' in req_name:
        dev_name, req_base = req_name.split('/', 1)
        output_dir = config.output / dev_name / req_base
        business_req_path = output_dir / f"business_req_analysis_{req_base}.txt"
    else:
        output_dir = config.output / req_name
        business_req_path = output_dir / f"business_req_analysis_{req_name}.txt"
        req_base = req_name # Define req_base here

    # 检查最终合并文件是否已存在，如果存在则跳过
    merged_file_path = output_dir / f"{req_base}_cosmic_merged.md"
    if merged_file_path.exists():
        logger.info(f"[{req_name}] 最终合并文件 {merged_file_path} 已存在，跳过 COSMIC 表生成步骤。")
        return # 直接返回，跳过后续处理

    # 检查业务需求文件是否存在
    if not business_req_path.exists():
        raise FileNotFoundError(f"业务需求文件不存在: {business_req_path}")
    
    # --- Preprocess Trigger Events ---
    logger.info(f"[{req_name}] 开始预处理触发事件JSON文件...")
    preprocess_trigger_events(output_dir, req_base)
    logger.info(f"[{req_name}] 触发事件JSON文件预处理完成")
    # --- End Preprocessing ---

    # 读取必要文件
    ai_prompt = read_prompt_file(str(prompt_path))
    business_req = read_business_req(str(business_req_path)) # Still read for potential context

    # Read the *processed* trigger events from the subdirectory
    processed_events_dir = output_dir / 'trigger_events'
    # Pass the subdirectory to read from, and the main output_dir to check for existing tables
    trigger_events = read_trigger_event_files(str(processed_events_dir), str(output_dir))

    if not trigger_events:
        logger.warning(f"[{req_name}] 在预处理并检查 {output_dir} 中的现有表格后，未在 {processed_events_dir} 中找到可处理的触发事件。跳过 COSMIC 表生成。")
        return # Exit if no events to process

    logger.info(f"[{req_name}] 找到 {len(trigger_events)} 个已预处理的触发事件需要生成COSMIC表格")

    # 使用线程池并发处理
    with ThreadPoolExecutor(max_workers=32) as executor: # Consider reducing max_workers if API rate limits are hit
        futures = []
        for event in trigger_events:
            futures.append(
                executor.submit(
                    process_single_event, # Function to execute
                    ai_prompt,            # Arguments for the function
                    business_req,
                    event,
                    output_dir            # Pass the main output dir for saving tables
                )
            )
            # 添加请求间隔 - Consider if still needed with potentially more, smaller calls
            time.sleep(3)

        for future in as_completed(futures):
            try:
                output_path = future.result() # Get the result (Path or None)
                if output_path:
                    logger.info(f"任务完成: COSMIC表格已成功保存至 {output_path}")
                else:
                    # Error already logged in process_single_event
                    logger.warning("任务失败: 未能生成COSMIC表格输出文件")
            except Exception as e:
                # This catches errors during future execution/retrieval, not necessarily within process_single_event
                logger.error(f"线程池任务处理失败: {str(e)}", exc_info=True)
