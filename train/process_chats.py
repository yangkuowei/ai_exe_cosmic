# -*- coding: utf-8 -*-
import json
import os
from pathlib import Path
import sys

from validate_cosmic_table import extract_json_from_text, extract_table_from_text

# --- 配置常量 ---

# 输入目录：存放原始 JSON 聊天记录文件
INPUT_DIR = Path("../chat_history")
# 输出文件：处理后的 JSONL 数据将追加到此文件
OUTPUT_FILE = INPUT_DIR / "chat_processed_data.jsonl"
# 单行 JSONL 数据的最大长度限制
MAX_LENGTH = 1800

# --- 规则常量 ---

# 系统角色内容关键字 (用作类型标识符)
SYSTEM_PROMPT_KEYWORD_COSMIC_EXPERT = "你是一位精通COSMIC功能点度量方法的专家分析师"
SYSTEM_PROMPT_KEYWORD_REQ_ANALYST = "你是一名专业的软件需求分析师"

# 最终用户回复必须包含的验证文本
FINAL_USER_VALIDATION_TEXT = "你真是太棒了"

# 目标 system 内容映射
TARGET_SYSTEM_CONTENT = {
    SYSTEM_PROMPT_KEYWORD_COSMIC_EXPERT: (
        "你是COSMIC功能点专家分析师，根据用户需求描述，严格按COSMIC方法论和用户规则分析拆分，并以精确JSON格式输出结果"
    ),
    SYSTEM_PROMPT_KEYWORD_REQ_ANALYST: (
        "你是软件需求分析师，精通COSMIC功能点度量，根据用户提供的JSON，严格按规则生成规范的Markdown格式COSMIC度量表格"
    )
}

# --- 辅助函数 ---

def _extract_text(text):
    """从AI回复中提取```text ```标记之间的内容"""
    import re
    match = re.search(r'```text\n(.*?)\n```', text, re.DOTALL)
    return match.group(1) if match else text


def validate_and_extract_data(data):
    """
    验证 JSON 数据结构和内容，并提取所需信息及类型。

    Args:
        data (list): 从 JSON 文件加载的列表数据。

    Returns:
        tuple: 包含 (system_type_keyword, system_content, input_content, output_content) 的元组，
               其中 system_type_keyword 是匹配到的关键字 (用于分类)。
               如果验证失败则返回 None。
    """
    # 1. 基本结构校验：必须是列表，且至少包含4项（system, user, assistant, final_user）
    if not isinstance(data, list) or len(data) < 4:
        print("  跳过：数据格式不是列表或长度不足 (<4)。")
        return None

    # 2. 角色校验
    if not (data[0].get("role") == "system" and
            data[1].get("role") == "human" and
            data[-2].get("role") == "ai" and
            data[-1].get("role") == "human"):
        print("  跳过：消息角色顺序不符合预期 (system, user, ..., assistant, user)。")
        return None

    # 3. 最终用户回复校验
    final_user_content = data[-1].get("content", "")
    if FINAL_USER_VALIDATION_TEXT not in final_user_content:
        print(f"  跳过：最终用户回复缺少验证文本 '{FINAL_USER_VALIDATION_TEXT}'。")
        return None

    # 4. 系统角色内容校验并确定目标 system 内容和类型
    system_content_original = data[0].get("content", "")
    target_system = None
    system_type_keyword = None # 用于标识记录类型

    if SYSTEM_PROMPT_KEYWORD_REQ_ANALYST in system_content_original: # 优先检查需求分析师
        system_type_keyword = SYSTEM_PROMPT_KEYWORD_REQ_ANALYST
        target_system = TARGET_SYSTEM_CONTENT[system_type_keyword]
    elif SYSTEM_PROMPT_KEYWORD_COSMIC_EXPERT in system_content_original:
        system_type_keyword = SYSTEM_PROMPT_KEYWORD_COSMIC_EXPERT
        target_system = TARGET_SYSTEM_CONTENT[system_type_keyword]
    else:
        print(f"  跳过：System 内容不包含指定关键字。")
        return None

    # 5. 提取 input 和 output
    input_content = data[1].get("content")
    output_content = data[-2].get("content")

    # 确保提取的内容不为空
    if input_content is None or output_content is None:
         print("  跳过：无法提取 input 或 output 内容。")
         return None

    if system_type_keyword == SYSTEM_PROMPT_KEYWORD_COSMIC_EXPERT:
        output_content = extract_json_from_text(output_content)
        input_content = _extract_text(input_content)

    elif system_type_keyword == SYSTEM_PROMPT_KEYWORD_REQ_ANALYST:
        output_content = extract_table_from_text(output_content)


    # 返回类型关键字和提取的内容
    return system_type_keyword, target_system, input_content, output_content

def format_to_jsonl(system, input_text, output_text):
    """
    将提取的内容格式化为指定的 JSONL 字符串。

    Args:
        system (str): 目标 system 内容。
        input_text (str): 提取的 input 内容。
        output_text (str): 提取的 output 内容。

    Returns:
        str: 格式化后的 JSONL 字符串 (单行)。
             如果发生错误则返回 None。
    """
    # 组装 text 字段的内容
    text_content = f"{system}<|input|>{input_text}<|output|>{output_text}"
    # 构建最终的 JSON 对象
    json_obj = {"text": text_content}

    try:
        # 序列化为 JSON 字符串，确保非 ASCII 字符正确处理
        jsonl_string = json.dumps(json_obj, ensure_ascii=False)
        return jsonl_string
    except Exception as e:
        print(f"  错误：序列化为 JSON 时出错 - {e}")
        return None

# --- 主处理逻辑 ---

def process_chat_history():
    """
    主函数，遍历目录、处理文件，将结果分类暂存，最后按顺序写入输出文件。
    """
    processed_count = 0
    skipped_count = 0
    error_count = 0

    # 用于暂存处理后的 JSONL 行
    req_analyst_lines = [] # 存储 "软件需求分析师" 类型的数据
    cosmic_expert_lines = [] # 存储 "COSMIC专家" 类型的数据

    print(f"开始处理目录: {INPUT_DIR.resolve()}")
    print(f"输出将追加到: {OUTPUT_FILE.resolve()}")
    print("-" * 30)

    # 检查输入目录是否存在
    if not INPUT_DIR.is_dir():
        print(f"错误：输入目录 '{INPUT_DIR}' 不存在或不是一个目录。")
        sys.exit(1) # 退出脚本

    # 确保输出目录存在
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # --- 第一阶段：读取、处理文件并将结果暂存到列表中 ---
    print("阶段 1：读取和处理文件...")
    for file_path in INPUT_DIR.iterdir():
        # 只处理 .json 文件
        if file_path.is_file() and file_path.suffix == '.json':
            print(f"--- 正在处理文件: {file_path.name} ---")
            try:
                # 读取 JSON 文件内容
                with open(file_path, 'r', encoding='utf-8') as infile:
                    chat_data = json.load(infile)

                # 验证数据并提取所需内容和类型
                extracted = validate_and_extract_data(chat_data)

                if extracted:
                    system_type, system, input_text, output_text = extracted

                    # 格式化为 JSONL 字符串
                    jsonl_line = format_to_jsonl(system, input_text, output_text)

                    jsonl_line = jsonl_line.replace(' ','')
                    jsonl_line = jsonl_line.replace('---','-')

                    if jsonl_line:
                        # 校验长度
                        if len(jsonl_line) <= MAX_LENGTH:
                            # 根据类型添加到对应的列表
                            if system_type == SYSTEM_PROMPT_KEYWORD_REQ_ANALYST:
                                req_analyst_lines.append(jsonl_line)
                                print(f"  暂存 (需求分析师): 记录已处理 (长度: {len(jsonl_line)})")
                            elif system_type == SYSTEM_PROMPT_KEYWORD_COSMIC_EXPERT:
                                cosmic_expert_lines.append(jsonl_line)
                                print(f"  暂存 (COSMIC专家): 记录已处理 (长度: {len(jsonl_line)})")
                            processed_count += 1
                        else:
                            print(f"  跳过：生成的 JSONL 记录长度 ({len(jsonl_line)}) 超过限制 {MAX_LENGTH}。")
                            skipped_count += 1
                    else:
                        # format_to_jsonl 内部已打印错误
                        error_count += 1
                else:
                    # validate_and_extract_data 内部已打印跳过原因
                    skipped_count += 1

            except json.JSONDecodeError:
                print(f"  错误：文件 {file_path.name} 不是有效的 JSON 格式。")
                error_count += 1
            except FileNotFoundError:
                print(f"  错误：文件 {file_path.name} 未找到。")
                error_count += 1
            except Exception as e:
                print(f"  处理文件 {file_path.name} 时发生未预料的错误: {e}")
                error_count += 1
        elif file_path.is_file() and file_path.name != OUTPUT_FILE.name:
             print(f"--- 跳过非 JSON 文件: {file_path.name} ---")

    print("-" * 30)
    print("阶段 1 完成。")
    print(f"共暂存 {len(req_analyst_lines)} 条 '需求分析师' 记录。")
    print(f"共暂存 {len(cosmic_expert_lines)} 条 'COSMIC专家' 记录。")
    print("-" * 30)

    # --- 第二阶段：按顺序将暂存的列表写入输出文件 ---
    print(f"阶段 2：将结果按顺序追加写入 {OUTPUT_FILE.name}...")
    try:
        # 以追加模式打开输出文件，使用 utf-8 编码
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
            # 首先写入所有 "软件需求分析师" 的记录
            if req_analyst_lines:
                print(f"  正在写入 {len(req_analyst_lines)} 条 '需求分析师' 记录...")
                for line in req_analyst_lines:
                    outfile.write(line + '\n')
                print("  '需求分析师' 记录写入完成。")

            # 然后写入所有 "COSMIC专家" 的记录
            if cosmic_expert_lines:
                print(f"  正在写入 {len(cosmic_expert_lines)} 条 'COSMIC专家' 记录...")
                for line in cosmic_expert_lines:
                    outfile.write(line + '\n')
                print("  'COSMIC专家' 记录写入完成。")

    except IOError as e:
        print(f"错误：无法打开或写入输出文件 {OUTPUT_FILE}: {e}")
        # 即使写入失败，之前的处理统计仍然有效
        error_count += (len(req_analyst_lines) + len(cosmic_expert_lines)) # 标记这些行为写入错误
        processed_count = 0 # 因为没有成功写入
    except Exception as e:
        print(f"写入文件时发生未预料的错误: {e}")
        error_count += (len(req_analyst_lines) + len(cosmic_expert_lines))
        processed_count = 0

    print("-" * 30)
    print("处理完成。")
    # 注意：这里的 processed_count 反映的是成功处理并暂存的记录数
    # 如果写入文件失败，这些记录实际上并未成功保存到最终文件
    print(f"成功处理并暂存的记录数: {processed_count}")
    print(f"因规则或长度限制跳过的记录数: {skipped_count}")
    print(f"处理或写入过程中发生错误的文件/记录数: {error_count}")
    if error_count == 0 :
         print(f"结果已按顺序追加到: {OUTPUT_FILE.resolve()}")
    else:
         print(f"处理或写入过程发生错误，请检查日志和输出文件: {OUTPUT_FILE.resolve()}")


# --- 程序入口 ---
if __name__ == "__main__":
    process_chat_history()
