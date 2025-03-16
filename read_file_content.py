import os

import re
import pandas as pd

from openpyxl import load_workbook
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
# 文件操作

def read_file_content(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read().strip()
        except Exception as e:
            print(f"读取文件出错: {e}")
            exit(1)
    else:
        print(f"文件不存在: {file_path}")


def save_content_to_file(file_name: str, output_dir: str, content: str, content_type: str = "text"):
    """
    保存内容到文件，支持不同类型的文件。

    Args:
        file_name: 输出文件名（不含扩展名）
        output_dir: 输出目录路径
        content: 要保存的字符串内容
        content_type: 内容类型 ("text", "json", "markdown", "other")
    """

    try:
        # 1. 提取基础文件名
        base_name = os.path.splitext(file_name)[0]

        # 2. 创建输出目录（如果不存在）
        os.makedirs(output_dir, exist_ok=True)

        # 4. 根据 content_type 确定文件扩展名和保存逻辑
        if content_type == "json":
            output_filename = os.path.join(output_dir, f"{base_name}.json")
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(content)
        elif content_type == "text":
            output_filename = os.path.join(output_dir, f"{base_name}.txt")
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(content)

        elif content_type == "markdown":
            output_filename = os.path.join(output_dir, f"{base_name}.md")
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(content)
        elif content_type == 'xlsx':
            output_filename = os.path.join(output_dir, f"{base_name}.xlsx")
            df = markdown_table_to_df(content)
            if df is not None:
                df.to_excel(output_filename, index=False)  # 保存为 Excel
        elif content_type == 'docx':
            ##先读取excel 文件
            excel_file = os.path.join(output_dir, f"{base_name}.xlsx")
            output_filename = os.path.join(output_dir, f"{base_name}.docx")
            create_function_design_doc(excel_file, output_filename)
        else:  # 默认情况，可以根据需要添加更多类型
            # 获取原始文件的扩展名
            original_extension = os.path.splitext(file_name)[1]
            output_filename = os.path.join(output_dir, f"{base_name}{original_extension}")
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(content)

        print(f"已创建文件: {output_filename}")

    except Exception as e:
        print(f"处理文件 {file_name} 时发生错误: {e}")


def extract_number(text):
    """
      Args:
        text: 包含数字的文本字符串。

      Returns:
        提取到的数字 (整数)，如果没有找到，则返回 None。
      """
    match = re.search(r"表格总行数要求：(\d+)", text)  # 使用正则表达式精确匹配
    if match:
        return int(match.group(1))  # 将匹配到的字符串转为整数
    else:
        return None


def markdown_table_to_df(table_text):
    # 分割行
    lines = table_text.strip().split('\n')

    # --- 表头处理 (关键改进) ---
    header_line = lines[0]
    separator_line = lines[1]

    # 获取表头单元格数量（基于分隔符行）
    header_cols = [s.strip() for s in re.split(r'(?<!\\)\|', separator_line)[1:-1]]
    num_cols = len(header_cols)

    # 解析表头行，并根据分隔符行的数量进行调整
    header = [h.strip() for h in re.split(r'(?<!\\)\|', header_line)[1:-1]]
    header = (header + [''] * (num_cols - len(header)))[:num_cols]  # 补齐或截断

    # --- 数据行处理 ---
    data = []
    for line in lines[2:]:
        row = [cell.strip() for cell in re.split(r'(?<!\\)\|', line)[1:-1]]
        row = (row + [''] * (num_cols - len(row)))  # 补齐
        row = [cell.replace("<br>", "\n") for cell in row]
        data.append(row)

    df = pd.DataFrame(data, columns=header)
    return df


def process_markdown_table(markdown_table_string, num_cols_to_process=5):
    """
    处理Markdown表格，合并指定数量列中连续相同内容的单元格。

    Args:
        markdown_table_string: Markdown表格的字符串。
        num_cols_to_process: 要处理的列数。

    Returns:
        处理后的Markdown表格字符串。
    """

    lines = markdown_table_string.strip().split('\n')
    header = lines[0:2]
    data_rows = lines[2:]

    table_data = [re.split(r'\s*\|\s*', row.strip('|')) for row in data_rows]

    num_cols = len(table_data[0])

    # 限制处理的列数
    num_cols_to_process = min(num_cols_to_process, num_cols)

    for col_index in range(num_cols_to_process):
        previous_value = None
        for row_index in range(len(table_data)):
            current_value = table_data[row_index][col_index]
            if current_value == previous_value:
                table_data[row_index][col_index] = ""
            else:
                previous_value = current_value

    processed_rows = ['| ' + ' | '.join(row) + ' |' for row in table_data]
    result_table = '\n'.join(header + processed_rows)

    return result_table



def create_function_design_doc(excel_file, docx_file):
    """
    根据COSMIC Excel表格生成功能设计文档（.docx）。
    (处理合并单元格，设置标题颜色为黑色)

    Args:
        excel_file: COSMIC Excel文件的路径。
        docx_file:  生成的Word文档的路径。
    """

    workbook = load_workbook(filename=excel_file)
    sheet = workbook.active

    document = Document()

    # 第4章 系统功能设计 (固定内容)
    heading = document.add_heading("第4章 系统功能设计", level=1)
    heading.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = heading.runs[0]
    run.font.name = '黑体'
    run.font.size = Pt(22)
    run.font.color.rgb = RGBColor(0, 0, 0)  # 设置为黑色

    section_num = 4
    current_requirement = None

    for row in sheet.iter_rows(min_row=2, values_only=True):
        requirement = row[2]
        process = row[4]

        if requirement:
            current_requirement = requirement
            section_num += 0.1
            section_num = round(section_num, 1)

            # 功能用户需求标题
            heading = document.add_heading(f"{section_num} {current_requirement}", level=2)
            run = heading.runs[0]
            run.font.name = '黑体'
            run.font.size = Pt(16)
            run.font.color.rgb = RGBColor(0, 0, 0)  # 设置为黑色
            current_process_num = 1  # 重置计数器

        if process:
            paragraph = document.add_paragraph(f"（{current_process_num}）{process}")
            run = paragraph.runs[0]
            run.font.name = '宋体'
            run.font.size = Pt(10.5)
            current_process_num += 1

    document.save(docx_file)
