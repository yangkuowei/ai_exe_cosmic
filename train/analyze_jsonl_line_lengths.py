import json
from collections import defaultdict

def analyze_jsonl_line_lengths(file_path):
    """
    读取 JSONL 文件，统计每行长度，并按 50 的档位输出分布情况。

    Args:
        file_path (str): JSONL 文件的路径。
    """
    length_counts = defaultdict(int)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # 去除行尾的换行符，然后计算长度
                line_length = len(line.rstrip('\n'))
                # 计算长度所在的档位
                length_bin = (line_length // 50) * 50
                length_counts[length_bin] += 1

        # 按档位排序并输出结果
        print(f"文件 '{file_path}' 行长度分布统计 (按 50 长度档位):")
        print("-" * 50)
        sorted_bins = sorted(length_counts.keys())
        for bin_start in sorted_bins:
            bin_end = bin_start + 49
            count = length_counts[bin_start]
            print(f"长度范围 [{bin_start}-{bin_end}]: {count} 行")

    except FileNotFoundError:
        print(f"错误: 文件 '{file_path}' 未找到。")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    # 请将 'your_jsonl_file.jsonl' 替换为你实际的 JSONL 文件路径
    jsonl_file = '../chat_history/chat_processed_data.jsonl'
    analyze_jsonl_line_lengths(jsonl_file)
