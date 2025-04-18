import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

from ai_common import load_model_config
from langchain_openai_client_v1 import call_ai
from validate_cosmic_table import extract_json_from_text

# --- Configuration ---
SOURCE_DIRECTORY = Path("../requirement_extraction_results")  # 使用 Path 对象
MAX_WORKERS = 12  # 根据你的 CPU 和 AI 调用限制调整线程数
AI_PROMPT = """
# 角色
你是一个经验丰富的软件需求分析师和解决方案架构师，擅长理解和阐述需求，并设计相应的解决方案。同时，你也是一个数据增强专家，能够基于现有数据生成新的、多样化的、高质量的训练数据。

# 任务
根据我提供的原始需求（包含标题、描述和解决方案），请你生成一个全新的、语义相关但内容有所变化的需求和解决方案对。
这个新的数据点应该：
1.  **主题相关**: 新的需求和解决方案应与原始输入的主题紧密相关。
2.  **内容变体**: 改变原始需求的措辞、句式结构，或者稍微调整需求的侧重点或细节。相应地，解决方案也需要进行调整或用不同的方式表述，但必须保持技术上的合理性和与新需求的对应关系。
3.  **避免直接复制**: 不要直接复制原始输入的句子或大段落。
4.  **保持格式**: 输出必须是一个包含 "title", "description", "solution" 三个键的 JSON 对象。
5.  **质量**: 生成的内容需要清晰、连贯、专业，并且在技术上是 plausible（貌似可信的）。

# 输入格式
我将提供一个 JSON 字符串，包含原始的 "title", "description", "solution"。

# 输出格式要求
请严格按照以下 JSON 格式返回你生成的新需求和解决方案对，不要包含任何额外的解释性文字或代码块标记：
{
    "title": "新的需求标题",
    "description": "新的需求描述",
    "solution": "新的解决方案描述"
}

# 示例输入 (仅为演示，实际输入会变化)
{
    "title": "用户登录失败率过高",
    "description": "近期线上监控显示，用户尝试登录时失败次数显著增加，尤其是在高峰时段。需要排查原因并降低失败率。",
    "solution": "1. 检查认证服务日志，定位具体错误码。\n2. 分析数据库连接池状态，确认是否有瓶颈。\n3. 增加验证码复杂度，防止恶意尝试。\n4. 优化登录接口性能。"
}

# 示例输出 (基于上面示例输入可能的一种生成结果)
{
    "title": "提升高峰期用户登录稳定性",
    "description": "系统在用户访问高峰期间，登录成功率出现明显下滑，影响用户体验。需分析瓶颈并实施优化措施以保障登录服务的稳定性。",
    "solution": "A. 深入排查高峰时段认证服务的错误日志，识别主要失败类型。\nB. 评估并可能扩展数据库连接资源，缓解高峰压力。\nC. 审视现有防刷机制，考虑引入更智能的验证方式。\nD. 对登录流程涉及的关键接口进行压力测试和性能调优。"
}

# 开始处理
请根据我接下来提供的具体需求内容，生成新的数据。
"""



def empty_validator(json_str: str) -> tuple[bool, str]:
    """空的校验函数"""
    return True, ""



def process_single_file(filepath: Path, output_dir: Path, prompt: str):
    """
    处理单个 JSON 文件：读取、调用 AI、保存结果。
    """
    try:
        print(f"Processing file: {filepath.name}")
        # 1. 读取文件内容
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                requirement_json_str = f.read()
                # 验证一下读取的是否是 JSON (可选，但推荐)
                json.loads(requirement_json_str)
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON content in file {filepath.name}. Skipping.", file=sys.stderr)
                return {"status": "error", "file": filepath.name, "message": "Invalid JSON content"}
            except Exception as e:
                print(f"Error: Failed to read file {filepath.name}: {e}", file=sys.stderr)
                return {"status": "error", "file": filepath.name, "message": f"File read error: {e}"}

        # 2. 调用 AI
        config = load_model_config()  # 加载配置
        ai_response_json = call_ai(
            ai_prompt=prompt,
            requirement_content=requirement_json_str,  # 将整个 JSON 字符串作为输入
            extractor=extract_json_from_text,
            validator=empty_validator,  # 使用空验证器
            max_chat_count=5,
            config=config
        )

        # 3. 处理 AI 响应并保存
        if ai_response_json:
            # 生成唯一文件名
            new_filename = f"augmented_{uuid.uuid4()}.json"
            output_filepath = output_dir / new_filename

            try:
                with open(output_filepath, 'w', encoding='utf-8') as outfile:
                    outfile.write(ai_response_json)
                print(f"Successfully generated and saved: {output_filepath.name}")
                return {"status": "success", "original_file": filepath.name, "new_file": output_filepath.name}
            except IOError as e:
                print(f"Error: Failed to write output file {output_filepath.name}: {e}", file=sys.stderr)
                return {"status": "error", "file": filepath.name, "message": f"File write error: {e}"}
            except Exception as e:
                print(f"Error: Unexpected error saving file {output_filepath.name}: {e}", file=sys.stderr)
                return {"status": "error", "file": filepath.name, "message": f"File saving error: {e}"}
        else:
            print(f"Error: AI processing failed for file {filepath.name}. No valid JSON response.", file=sys.stderr)
            return {"status": "error", "file": filepath.name, "message": "AI processing failed"}

    except Exception as e:
        print(f"Error: Unhandled exception processing file {filepath.name}: {e}", file=sys.stderr)
        # Log the full traceback for debugging if needed
        # import traceback
        # traceback.print_exc()
        return {"status": "error", "file": filepath.name, "message": f"Unhandled exception: {e}"}


# --- Main Execution ---

if __name__ == "__main__":
    # 确保源目录存在
    if not SOURCE_DIRECTORY.is_dir():
        print(f"Error: Source directory '{SOURCE_DIRECTORY}' not found or is not a directory.", file=sys.stderr)
        sys.exit(1)

    # 获取所有 json 文件
    json_files = list(SOURCE_DIRECTORY.glob("*.json"))

    if not json_files:
        print(f"No .json files found in '{SOURCE_DIRECTORY}'.")
        sys.exit(0)

    print(f"Found {len(json_files)} JSON files to process in '{SOURCE_DIRECTORY}'.")
    print(f"Using up to {MAX_WORKERS} threads.")

    # 使用线程池处理
    results = []
    start_time = time.time()

    # 使用 ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交任务
        future_to_file = {executor.submit(process_single_file, filepath, SOURCE_DIRECTORY, AI_PROMPT): filepath for
                          filepath in json_files}

        # 获取结果
        for i, future in enumerate(as_completed(future_to_file)):
            filepath = future_to_file[future]
            try:
                result = future.result()
                results.append(result)
                print(f"Progress: {i + 1}/{len(json_files)} - Result for {filepath.name}: {result['status']}")
            except Exception as exc:
                print(f"Error: An exception occurred for file {filepath.name}: {exc}", file=sys.stderr)
                results.append({"status": "error", "file": filepath.name, "message": f"Thread execution error: {exc}"})

    end_time = time.time()
    total_time = end_time - start_time

    # 统计结果
    success_count = sum(1 for r in results if r and r['status'] == 'success')
    error_count = len(results) - success_count

    print("\n--- Processing Summary ---")
    print(f"Total files processed: {len(results)}")
    print(f"Successful generations: {success_count}")
    print(f"Failed attempts: {error_count}")
    print(f"Total time taken: {total_time:.2f} seconds")

    if error_count > 0:
        print("\nFiles with errors:")
        for r in results:
            if r and r['status'] == 'error':
                print(f"- {r.get('file', 'Unknown file')}: {r.get('message', 'Unknown error')}")
