import json
import os

def format_history_for_instruction(history_messages):
    """
    将消息字典列表格式化为适合 'instruction' 字段的单一字符串。
    (函数内容与之前相同)
    """
    formatted_parts = []
    for msg in history_messages:
        if not isinstance(msg, dict):
            print(f"    警告：历史记录中发现非字典项，已跳过：{msg}")
            continue
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if role == "system":
            role_prefix = "System"
        elif role == "human":
            role_prefix = "Human"
        elif role == "ai":
            role_prefix = "Assistant"
        else:
            role_prefix = role.capitalize()
        formatted_parts.append(f"{role_prefix}: {content}")
    return "\n\n".join(formatted_parts)

# --- 配置区域 ---
# *** 指定包含 JSON 文件的输入目录 ***
input_dir = '../chat_history'
# *** 指定合并后的输出文件名 ***
output_file = 'train.jsonl'
# --- 配置区域结束 ---

print(f"开始处理目录 '{input_dir}' 中的所有 JSON 文件...")
print(f"结果将写入到文件: {output_file}")

# 检查输入目录是否存在
if not os.path.isdir(input_dir):
    print(f"错误：输入目录 '{input_dir}' 不存在或不是一个目录。")
    exit()

# 获取目录下所有的 .json 文件
json_files = [f for f in os.listdir(input_dir)
              if os.path.isfile(os.path.join(input_dir, f)) and f.lower().endswith('.json')]

if not json_files:
    print(f"错误：在目录 '{input_dir}' 中没有找到任何 .json 文件。")
    exit()

print(f"在 '{input_dir}' 中找到 {len(json_files)} 个 JSON 文件，将进行处理。")

total_examples_written = 0
files_processed = 0

# 打开（或创建）输出文件，准备写入所有结果
# 使用 'w' 模式，如果文件已存在，会覆盖内容
try:
    with open(output_file, 'w', encoding='utf-8') as outfile:
        # 遍历找到的每个 JSON 文件
        for filename in json_files:
            file_path = os.path.join(input_dir, filename)
            print(f"\n--- 正在处理文件: {filename} ---")
            file_examples_written = 0

            try:
                # 读取当前 JSON 文件的内容
                with open(file_path, 'r', encoding='utf-8') as infile:
                    conversation_messages = json.load(infile)

                # 验证加载的数据是否为列表 (结构 B 的核心)
                if not isinstance(conversation_messages, list):
                    print(f"  警告：文件 '{filename}' 的顶层结构不是列表，已跳过。")
                    continue # 跳过这个文件，处理下一个

                print(f"  文件 '{filename}' 加载成功，包含 {len(conversation_messages)} 条消息。")

                history = [] # 每个文件的历史记录独立计算
                # 遍历当前文件中的消息列表
                for i, message in enumerate(conversation_messages):
                    if not isinstance(message, dict):
                        print(f"    警告：在文件 '{filename}' 索引 {i} 处跳过非字典条目：{message}")
                        continue

                    role = message.get("role")
                    content = message.get("content")

                    if role == "ai":
                        if history:
                            instruction = format_history_for_instruction(history)
                            output = content if content is not None else ""
                            training_example = {
                                "instruction": instruction,
                                "input": "",
                                "output": output
                            }
                            # 写入到 *同一个* 输出文件
                            outfile.write(json.dumps(training_example, ensure_ascii=False) + '\n')
                            file_examples_written += 1
                        else:
                            print(f"    警告：文件 '{filename}' 索引 {i} 处的 AI 消息无历史记录，已跳过。")

                    # 将当前消息加入历史
                    history.append(message)

                print(f"  文件 '{filename}' 处理完成，生成了 {file_examples_written} 条训练样本。")
                total_examples_written += file_examples_written
                files_processed += 1

            except json.JSONDecodeError:
                print(f"  错误：解析文件 '{filename}' 时出错。请检查其是否为有效的 JSON 格式。文件已跳过。")
            except Exception as e:
                print(f"  处理文件 '{filename}' 时发生未预料的错误：{e}。文件已跳过。")

except IOError as e:
    print(f"错误：无法打开或写入输出文件 '{output_file}'。请检查权限或路径。错误信息：{e}")
except Exception as e:
     print(f"发生未预料的错误：{e}")

finally:
    print("\n===================================")
    print(f"所有文件处理完毕。")
    print(f"总共处理了 {files_processed} / {len(json_files)} 个有效的 JSON 文件。")
    print(f"总共写入 {total_examples_written} 条训练样本到 '{output_file}'。")
    print("===================================")

