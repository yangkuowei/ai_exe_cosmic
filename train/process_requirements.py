# -*- coding: utf-8 -*-
import os
import json
import logging

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 配置 ---
# 输入目录：包含各个子文件夹，每个子文件夹下有 requirement_extraction.txt
INPUT_BASE_DIR = '../out_put_files/杨扩威20250504'
# 输出文件：用于追加保存处理后的 JSONL 数据
OUTPUT_JSONL_FILE = '../out_put_files/processed_data.jsonl'
# 输入文件名
REQUIREMENT_FILENAME = 'requirement_extraction.txt'
# JSONL 行最大长度（字节数），超过则跳过
MAX_JSONL_LENGTH_BYTES = 3900
# 需要提取的字段的 key 文本（注意冒号是中文冒号）
# 使用精确匹配的 key 文本
KEYS_TO_EXTRACT = {
    "需求名称": "需求名称:", # 注意这里去掉了后面的中文冒号，因为原始代码用的是英文冒号，统一用英文冒号
    "需求背景": "需求背景:",
    "需求解决方案": "需求解决方案:"
}
# 其他可能出现的 key，用于确定字段的结束位置（也使用英文冒号）
STOP_KEYS = ["涉及系统:", "cosmic总行数:"]

# --- 函数定义 ---

def parse_requirement_file(file_path):
    """
    解析单个 requirement_extraction.txt 文件内容。
    能够处理 key 和 value 分开在不同行的情况。

    Args:
        file_path (str): requirement_extraction.txt 文件的完整路径。

    Returns:
        dict or None: 包含提取到的 "需求名称", "需求背景", "需求解决方案" 的字典，
                      如果文件不存在、无法读取或解析失败则返回 None。
                      如果某个字段缺失，其对应的值会是空字符串。
    """
    extracted_data = {key: "" for key in KEYS_TO_EXTRACT} # 初始化结果字典，值为空字符串
    all_keys_map = {**KEYS_TO_EXTRACT, **{key: key for key in STOP_KEYS}} # 合并所有 key 到一个 map，方便查找

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        current_internal_key = None # 当前正在处理的字段的内部 key 名称（例如 "需求名称"）
        current_value_lines = [] # 当前字段对应的内容行

        for line in lines:
            stripped_line = line.strip() # 去除行首尾空白

            found_key_text = None # 标记当前行是否是某个 key 的起始行
            next_internal_key = None # 存储找到的 key 对应的内部名称（如 "需求名称"）

            # 检查当前行是否以任何一个已知的 key 开头
            # 修改：直接用 stripped_line 和字典里的 key 比较
            for internal_key, key_text in all_keys_map.items():
                if stripped_line == key_text: # 要求 key 单独占一行
                    found_key_text = key_text
                    # 只有需要提取的 key 才设置 next_internal_key
                    if internal_key in KEYS_TO_EXTRACT:
                        next_internal_key = internal_key
                    else:
                        next_internal_key = None # Stop key 不需要存储值
                    break
                # 也处理 key 和 value 在同一行的情况 (虽然示例不是这样，但保留兼容性)
                elif stripped_line.startswith(key_text):
                    found_key_text = key_text
                    if internal_key in KEYS_TO_EXTRACT:
                        next_internal_key = internal_key
                    else:
                        next_internal_key = None
                    break


            # 如果找到了一个新的 key 行 (found_key_text 不为 None)
            if found_key_text:
                # 1. 保存上一个 key 的内容（如果存在且是需要提取的 key）
                if current_internal_key and current_value_lines:
                    extracted_data[current_internal_key] = "\n".join(current_value_lines).strip()

                # 2. 更新当前 key
                current_internal_key = next_internal_key # 更新为内部 key 名称或 None

                # 3. **修改点：** 处理当前 key 行可能包含的内容，并重置/初始化 current_value_lines
                value_on_same_line = ""
                # 检查是否 key 和 value 在同一行
                if stripped_line.startswith(found_key_text) and len(stripped_line) > len(found_key_text):
                     value_on_same_line = stripped_line[len(found_key_text):].strip()

                if value_on_same_line:
                    # 如果 key 行有内容，作为第一行
                    current_value_lines = [value_on_same_line]
                else:
                    # 如果 key 行没有内容（或 key 单独一行），则清空列表，准备接收下一行的内容
                    current_value_lines = []

            # 如果当前行不是 key 行，并且我们正在某个需要提取的 key 的内容块内
            elif current_internal_key and stripped_line: # 只添加非空行
                current_value_lines.append(stripped_line)
            # 如果当前行不是 key 行，也不是空行，但 current_internal_key 是 None (比如在 stop key 之后)
            # 则忽略这些行，直到遇到下一个要提取的 key
            elif not current_internal_key and stripped_line:
                 pass # 忽略掉在 stop key 之后，下一个目标 key 之前的内容


        # 处理文件末尾最后一个 key 的内容
        if current_internal_key and current_value_lines:
            extracted_data[current_internal_key] = "\n".join(current_value_lines).strip()

        # 检查是否所有需要的字段都被提取到了（即使是空字符串也算提取到）
        # 这里改为检查提取到的值是否非空，如果需要即使为空也生成，则去掉这个检查
        if all(extracted_data.get(k) for k in KEYS_TO_EXTRACT): # 确保三个主要字段都有内容
             # 确保返回的字典只包含我们明确要提取的key
            return {k: extracted_data[k] for k in KEYS_TO_EXTRACT}
        else:
            missing_keys = [k for k in KEYS_TO_EXTRACT if not extracted_data.get(k)]
            logging.warning(f"文件 {file_path} 解析不完整，缺少或内容为空的字段: {missing_keys}。跳过此文件。")
            return None # 如果有字段内容为空，则不生成该条记录

    except FileNotFoundError:
        logging.error(f"文件未找到: {file_path}")
        return None
    except Exception as e:
        logging.error(f"读取或解析文件 {file_path} 时出错: {e}")
        return None

def format_to_jsonl(data):
    """
    将提取的数据格式化为指定的 JSONL 字符串。

    Args:
        data (dict): 包含 "需求名称", "需求背景", "需求解决方案" 的字典。

    Returns:
        str: 格式化后的 JSONL 字符串。
    """
    # 从字典中获取数据，如果键不存在则使用空字符串 (理论上 parse 函数已保证存在)
    name = data.get("需求名称", "")
    background = data.get("需求背景", "")
    solution = data.get("需求解决方案", "")

    # 构建目标 "text" 字段的内容
    # 注意：保持模板和用户要求一致
    text_content = (
        f"你是一个专业的软件解决方案大师，请根据以下需求名称、需求背景输出有利于生成COSMIC度量表格的解决方案"
        f"<|input|>需求名称:{name}，需求背景：{background}"
        f"<|output|>需求解决方案：{solution}"
    )

    # 构建最终的字典
    output_dict = {"text": text_content}

    # 将字典转换为 JSON 字符串，确保中文字符不被转义
    # ensure_ascii=False 保证中文正常显示，而不是 \uXXXX 格式
    json_line = json.dumps(output_dict, ensure_ascii=False)
    return json_line

# --- 主逻辑 ---
def main():
    processed_count = 0 # 成功处理并写入的文件计数
    skipped_count = 0   # 因超长或解析不完整而跳过的文件计数
    parse_failed_count = 0 # 解析失败或文件格式有问题的文件计数
    found_files_count = 0 # 找到的目标文件计数

    # 确保输出目录存在，如果不存在则创建
    output_dir = os.path.dirname(OUTPUT_JSONL_FILE)
    if output_dir and not os.path.exists(output_dir):
        logging.info(f"输出目录 {output_dir} 不存在，正在创建...")
        os.makedirs(output_dir)
        logging.info(f"输出目录 {output_dir} 创建成功。")

    # 遍历 INPUT_BASE_DIR 下的所有子文件夹
    logging.info(f"开始在目录 {INPUT_BASE_DIR} 中查找 {REQUIREMENT_FILENAME}...")
    # 检查输入目录是否存在
    if not os.path.isdir(INPUT_BASE_DIR):
        logging.error(f"输入目录 {INPUT_BASE_DIR} 不存在或不是一个有效的目录。请检查路径。")
        return # 目录不存在，直接退出

    for item in os.listdir(INPUT_BASE_DIR):
        item_path = os.path.join(INPUT_BASE_DIR, item)
        # 检查是否是文件夹
        if os.path.isdir(item_path):
            subdir_path = item_path # 重命名以更清晰
            requirement_file_path = os.path.join(subdir_path, REQUIREMENT_FILENAME)
            # 检查目标文件是否存在
            if os.path.isfile(requirement_file_path):
                found_files_count += 1
                logging.info(f"找到并处理文件: {requirement_file_path}")

                # 1. 解析文件内容
                extracted_data = parse_requirement_file(requirement_file_path)

                if extracted_data:
                    # 2. 组装成 JSONL 格式
                    jsonl_line = format_to_jsonl(extracted_data)

                    # 3. 校验长度（按字节数）
                    # 使用 utf-8 编码计算字节长度
                    jsonl_bytes_length = len(jsonl_line.encode('utf-8'))

                    if jsonl_bytes_length <= MAX_JSONL_LENGTH_BYTES:
                        # 4. 追加写入到输出文件
                        try:
                            # 使用 'a' 模式追加写入，确保换行
                            with open(OUTPUT_JSONL_FILE, 'a', encoding='utf-8') as outfile:
                                outfile.write(jsonl_line + '\n')
                            processed_count += 1
                            # logging.info(f"成功处理并写入: {requirement_file_path} (长度: {jsonl_bytes_length} bytes)") # 可以取消注释以获得更详细日志
                        except IOError as e:
                            logging.error(f"写入文件 {OUTPUT_JSONL_FILE} 时出错: {e}")
                            # 如果写入失败，计入解析失败或跳过
                            parse_failed_count += 1
                    else:
                        # 长度超过限制，跳过并记录
                        skipped_count += 1
                        logging.warning(f"跳过文件 (超长: {jsonl_bytes_length} > {MAX_JSONL_LENGTH_BYTES} bytes): {requirement_file_path}")
                else:
                    # 解析失败或文件格式有问题，计入失败计数
                    parse_failed_count += 1
                    # logging.warning(f"文件解析失败或格式不完整，跳过: {requirement_file_path}") # parse_requirement_file 内部已有日志

            else:
                logging.debug(f"在子目录 {subdir_path} 中未找到文件 {REQUIREMENT_FILENAME}")
        else:
             logging.debug(f"跳过非目录项: {item_path}")

    # --- 结果报告 ---
    logging.info("\n--- 处理结果 ---")
    logging.info(f"总共扫描子目录数: {len([d for d in os.listdir(INPUT_BASE_DIR) if os.path.isdir(os.path.join(INPUT_BASE_DIR, d))])}")
    logging.info(f"总共找到 {REQUIREMENT_FILENAME} 文件数量: {found_files_count}")
    logging.info(f"成功处理并写入 {OUTPUT_JSONL_FILE} 的文件数量: {processed_count}")
    logging.info(f"因长度超过 {MAX_JSONL_LENGTH_BYTES} 字节而跳过的文件数量: {skipped_count}")
    logging.info(f"因解析失败或内容不完整而跳过的文件数量: {parse_failed_count}")
    logging.info(f"处理完成。输出文件位于: {OUTPUT_JSONL_FILE}")

# --- 程序入口 ---
if __name__ == "__main__":
    main()
