import json
import re
import os
import time # 用于添加一点延迟，模拟AI调用耗时
from typing import Tuple, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, Future, as_completed

from ai_common import load_model_config
from langchain_openai_client_v1 import call_ai
from validate_cosmic_table import extract_json_from_text, extract_table_from_text

# --- 配置 ---
INPUT_FILE_PATH = os.path.join('../chat_history', 'train/processed_data.jsonl')
OUTPUT_FILE_PATH = 'remove_impurities.jsonl'
PROMPT_FILE_PATH = os.path.join('../ai_promote', 'remove_impurities.md')
AI_PROMPT_FILE_ENCODING = 'utf-8'
JSONL_FILE_ENCODING = 'utf-8'
MAX_WORKERS = 12 # 设置线程池的最大线程数，根据你的API限制和机器性能调整

# --- 回调函数 (保持不变) ---
def extractor(content: str) -> str:
    """简单的提取器回调函数"""
    return content

def _validate(content: str) -> Tuple[bool, str]:
    """简单的验证器回调函数"""
    # print(f"[Thread-{threading.get_ident()}] Validating content...")
    # 在实际应用中实现更复杂的验证逻辑
    return True, ''


# --- 处理单个需要 AI 的行的函数 (将在线程中运行) ---
def process_ai_task(line_num: int, ai_prompt: str, input_content: str) -> str:
    """
    封装调用 AI 的逻辑，以便在线程池中执行。
    返回处理后的 input (input_out)。
    """
    try:
        input_out = call_ai(
            ai_prompt=ai_prompt,
            requirement_content=input_content,
            extractor=extractor,
            validator=_validate,
            config=load_model_config()
        )
        return input_out
    except Exception as e:
        print(f"Error in AI task for line {line_num}: {e}")
        # 返回 None 或抛出异常，以便主线程知道此任务失败
        return None # 或者 raise e

# --- 主处理逻辑 (修改后) ---
def process_jsonl_file_concurrently():
    """
    读取输入的 JSONL 文件，并发处理需要 AI 的行，
    并将所有结果按顺序写入到输出的 JSONL 文件。
    """
    print(f"Starting concurrent processing of '{INPUT_FILE_PATH}'...")
    start_time = time.time()

    # 1. 读取 AI 系统提示词
    ai_system_prompt = ""
    try:
        with open(PROMPT_FILE_PATH, 'r', encoding=AI_PROMPT_FILE_ENCODING) as f:
            ai_system_prompt = f.read()
        print(f"Successfully read AI prompt from '{PROMPT_FILE_PATH}'.")
    except FileNotFoundError:
        print(f"Error: Prompt file '{PROMPT_FILE_PATH}' not found. Cannot proceed with AI calls.")
        return
    except Exception as e:
        print(f"Error reading prompt file '{PROMPT_FILE_PATH}': {e}")
        return

    # 加载模型配置一次
    model_config = load_model_config()

    lines_to_process = []
    lines_read_count = 0
    invalid_json_count = 0
    missing_keys_count = 0

    # --- 第一阶段：读取和初步分类 ---
    print("Phase 1: Reading input file and identifying tasks...")
    try:
        with open(INPUT_FILE_PATH, 'r', encoding=JSONL_FILE_ENCODING) as infile:
            for line_num, line in enumerate(infile, 1):
                lines_read_count += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    print(f"Warning: Skipping invalid JSON on line {line_num}: {line[:100]}...")
                    invalid_json_count += 1
                    continue

                if not all(k in data for k in ['instruction', 'input', 'output']):
                    print(f"Warning: Skipping line {line_num} due to missing keys ('instruction', 'input', 'output').")
                    missing_keys_count += 1
                    continue

                # 存储原始行号和数据，用于后续处理和排序
                lines_to_process.append({"line_num": line_num, "data": data})

    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE_PATH}' not found.")
        return
    except Exception as e:
        print(f"An unexpected error occurred during file reading: {e}")
        return

    print(f"Phase 1 finished. Read {lines_read_count} lines. Identified {len(lines_to_process)} valid lines for processing.")

    # --- 第二阶段：并发处理 AI 任务 ---
    print(f"Phase 2: Submitting AI tasks to ThreadPoolExecutor (max_workers={MAX_WORKERS})...")
    futures: Dict[Future, Dict[str, Any]] = {} # 存储 Future 对象和对应的原始信息
    results: Dict[int, Dict[str, Any]] = {} # 存储处理结果，以行号为键
    processed_ai_count = 0
    skipped_no_prompt_count = 0
    processed_non_ai_count = 0 # 如果有其他类型的处理，可以在这里计数

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for item in lines_to_process:
            line_num = item["line_num"]
            data = item["data"]
            instruction = data.get('instruction', '')
            input_content = data.get('input', '')
            output_content = data.get('output', '')

            # --- 条件 1: COSMIC 专家 (需要 AI) ---
            if "你是一位精通COSMIC功能点度量方法的专家分析师" in instruction:
                if not ai_system_prompt:
                    # 这个检查其实在开始时已经做了，但为了保险再加一次
                    print(f"Warning: Skipping line {line_num} because AI prompt is missing.")
                    skipped_no_prompt_count += 1
                    # 标记此行处理失败或跳过
                    results[line_num] = {"error": "Missing AI prompt"}
                    continue

                # 提交 AI 任务到线程池
                future = executor.submit(
                    process_ai_task,
                    line_num,
                    ai_system_prompt,
                    input_content
                )
                # 存储 future 和对应的原始数据，以便后续处理 output
                futures[future] = {"line_num": line_num, "original_output": output_content}
                processed_ai_count +=1

            # --- 其他条件（如果需要处理，在这里添加） ---
            # 例如，处理 "你是一名专业的软件需求分析师" 的情况（根据你的原始需求描述）
            # elif "你是一名专业的软件需求分析师" in instruction:
            #      # 这种类型不需要 AI 调用，直接处理
            #      cleaned_output = extract_table_from_text(output_content) # 清理 output
            #      results[line_num] = {
            #          "instruction": "你是一名专业的软件需求分析师。你的核心任务是根据用户提供的功能分析结果（JSON格式），生成详细、准确且格式规范的COSMIC度量表格（Markdown格式）",
            #          "input": input_content, # 保留原 input
            #          "output": cleaned_output,
            #          "processed": True # 标记为已处理
            #      }
            #      processed_non_ai_count += 1


            # --- 不符合任何处理条件的行 ---
            else:
                # 标记此行不处理或跳过，但保留行号以便最终统计
                results[line_num] = {"skipped": True}
                # skipped_lines_count += 1 # 这个计数后面统一做

        print(f"Submitted {processed_ai_count} AI tasks. Waiting for completion...")

        # --- 等待并收集 AI 任务结果 ---
        ai_task_errors = 0
        for future in as_completed(futures):
            original_info = futures[future]
            line_num = original_info["line_num"]
            original_output = original_info["original_output"]
            try:
                # 获取 AI 任务的结果 (处理后的 input_out)
                input_out = future.result()

                if input_out is not None:
                    # AI 调用成功，清理原始 output
                    # 注意：这里使用的是原始数据中的 output_content
                    cleaned_output = extract_json_from_text(original_output) # 或者用 clean_output

                    # 构建最终的 JSON 数据
                    results[line_num] = {
                        "instruction": "请根据以下软件需求描述，严格按照COSMIC分析规则生成JSON结果。",
                        "input": input_out,
                        "output": cleaned_output,
                        "processed": True # 标记为已处理
                    }
                else:
                    # AI 任务内部出错 (process_ai_task 返回了 None)
                    results[line_num] = {"error": "AI task failed internally"}
                    ai_task_errors += 1

            except Exception as exc:
                print(f'Line {line_num} generated an exception: {exc}')
                results[line_num] = {"error": str(exc)} # 记录错误信息
                ai_task_errors += 1

    print("Phase 2 finished. All AI tasks completed.")

    # --- 第三阶段：写入结果文件 ---
    print(f"Phase 3: Writing results to '{OUTPUT_FILE_PATH}'...")
    lines_written_count = 0
    final_skipped_count = 0
    final_error_count = invalid_json_count + missing_keys_count + skipped_no_prompt_count + ai_task_errors

    # 按原始行号排序，确保输出顺序与输入文件一致
    sorted_line_nums = sorted(results.keys())

    try:
        with open(OUTPUT_FILE_PATH, 'w', encoding=JSONL_FILE_ENCODING) as outfile: # 使用 'w' 覆盖模式
            for line_num in sorted_line_nums:
                result_data = results[line_num]

                if result_data.get("processed"):
                    # 提取需要写入的数据 (移除自定义的 'processed' 键)
                    data_to_write = {k: v for k, v in result_data.items() if k != 'processed'}
                    try:
                        json_string = json.dumps(data_to_write, ensure_ascii=False)
                        outfile.write(json_string + '\n')
                        lines_written_count += 1
                    except Exception as e:
                        print(f"Error writing processed data for line {line_num} to output file: {e}")
                        final_error_count += 1
                elif result_data.get("skipped"):
                    final_skipped_count += 1
                elif result_data.get("error"):
                     # 记录了错误，但不写入该行到输出文件
                     final_error_count += 1 # 错误已在前面计数，这里只是明确分类

    except Exception as e:
        print(f"An unexpected error occurred during file writing: {e}")
        return # 写入失败，提前退出

    end_time = time.time()
    print("Phase 3 finished.")

    print("\n--- Processing Summary ---")
    print(f"Total time taken: {end_time - start_time:.2f} seconds")
    print(f"Total lines read from input: {lines_read_count}")
    print(f"Lines with invalid JSON skipped: {invalid_json_count}")
    print(f"Lines with missing keys skipped: {missing_keys_count}")
    print(f"Lines needing AI prompt but prompt missing: {skipped_no_prompt_count}")
    print(f"AI tasks submitted: {processed_ai_count}")
    print(f"Non-AI lines processed: {processed_non_ai_count}") # 新增计数
    print(f"AI tasks completed with errors: {ai_task_errors}")
    print(f"Total lines successfully processed and written: {lines_written_count}")
    print(f"Total lines skipped (no matching instruction): {final_skipped_count}")
    print(f"Total lines with errors (parsing/AI call/writing): {final_error_count}")
    print(f"Output saved to '{OUTPUT_FILE_PATH}'")


# --- 运行脚本 ---
if __name__ == "__main__":
    # 检查输入文件是否存在
    if not os.path.exists(INPUT_FILE_PATH):
        print(f"Error: Input file not found at '{INPUT_FILE_PATH}'")
        print("Please ensure the file exists and the path is correct.")
    # 检查提示文件是否存在
    elif not os.path.exists(PROMPT_FILE_PATH):
         print(f"Error: Prompt file not found at '{PROMPT_FILE_PATH}'")
         print("Please ensure the file exists and the path is correct.")
    else:
        # 可选：在开始处理前删除旧的输出文件
        if os.path.exists(OUTPUT_FILE_PATH):
            print(f"Removing existing output file '{OUTPUT_FILE_PATH}'.")
            os.remove(OUTPUT_FILE_PATH)

        process_jsonl_file_concurrently()
