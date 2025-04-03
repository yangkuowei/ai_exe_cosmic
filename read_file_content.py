# 标准库导入
import os
import re
import logging
from pathlib import Path
from typing import Optional, Union, List
import docx
# 第三方库导入
import pandas as pd
from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Pt, RGBColor
from openpyxl import load_workbook
from openpyxl.styles import Alignment
# 文件操作

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def read_file_content(file_path: Union[str, Path]) -> Optional[str]:
    """读取文件内容并返回去除首尾空格的字符串
    
    Args:
        file_path: 文件路径，支持字符串或Path对象
        
    Returns:
        str: 文件内容（去除首尾空格）
        None: 文件不存在或读取失败
        
    Raises:
        FileNotFoundError: 文件不存在
        IOError: 文件读取失败
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path
    
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    try:
        with path.open('r', encoding='utf-8') as file:
            return file.read().strip()
    except UnicodeDecodeError as e:
        raise IOError(f"文件解码失败: {path}") from e
    except Exception as e:
        raise IOError(f"读取文件出错: {path}") from e


# 常量定义
EXCEL_COLUMN_NAMES = {
    "requirement": 2,  # 需求列索引
    "process": 4       # 流程列索引
}

DEFAULT_FONT_STYLES = {
    "heading1": {"name": "黑体", "size": Pt(22), "color": RGBColor(0, 0, 0)},
    "heading2": {"name": "黑体", "size": Pt(16), "color": RGBColor(0, 0, 0)},
    "body": {"name": "宋体", "size": Pt(10.5)}
}

def save_content_to_file(
    file_name: str, 
    output_dir: Union[str, Path],
    content: str, 
    content_type: str = "text"
) -> Path:
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

            # 合并表格单元格
            merge_cells_by_column(output_filename, "Sheet1")
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

        logging.info(f"已创建文件: {output_filename}")

    except Exception as e:
        logging.error(f"处理文件 {file_name} 时发生错误", exc_info=True)


def extract_content_from_requst(text, extract_type: str = "total_rows"):
    """
      Args:
        text: 包含数字的文本字符串。

      Returns:
        提取到的数字 (整数)，如果没有找到，则返回 None。
      """
    if extract_type == 'total_rows' :
        match = re.search(r"表格总行数要求：(\d+)", text)  #
        return int(match.group(1))
    if extract_type == 'request_name':
        match = re.search(r"客户需求：(.*)", text)  # 需求名称
        return match.group(1)
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



def apply_font_style(run, style_name: str) -> None:
    """应用预定义的字体样式
    
    Args:
        run: docx的Run对象
        style_name: 样式名称（heading1/heading2/body）
    """
    style = DEFAULT_FONT_STYLES[style_name]
    run.font.name = style["name"]
    run.font.size = style["size"]
    if "color" in style:
        run.font.color.rgb = style["color"]

def create_function_design_doc(excel_file: Union[str, Path], docx_file: Union[str, Path]) -> None:
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
        requirement = row[EXCEL_COLUMN_NAMES["requirement"]]
        process = row[EXCEL_COLUMN_NAMES["process"]]

        if requirement:
            current_requirement = requirement
            section_num += 0.1
            section_num = round(section_num, 1)

            # 添加功能用户需求标题
            heading = document.add_heading(f"{section_num} {current_requirement}", level=2)
            apply_font_style(heading.runs[0], "heading2")
            current_process_num = 1  # 重置流程计数器

        if process:
            paragraph = document.add_paragraph(f"（{current_process_num}）{process}")
            run = paragraph.runs[0]
            run.font.name = '宋体'
            run.font.size = Pt(10.5)
            current_process_num += 1

    document.save(docx_file)


def merge_cells_by_column(filename, sheetname):
    """
    按列合并 Excel 单元格。

    Args:
        filename: Excel 文件名。
        sheetname: 要处理的 Sheet 名称。
    """
    workbook = load_workbook(filename)
    sheet = workbook[sheetname]

    # 处理 A 到 E 列 (0-4)
    for col_index in range(5):  # 列索引从0开始
        start_row = None
        start_value = None
        end_row = None  # 新增：记录批次的结束行

        # 循环每一行，从第二行开始（跳过标题行）
        for row_index in range(2, sheet.max_row + 1):
            cell = sheet.cell(row=row_index, column=col_index + 1)
            cell_value = cell.value

            if cell_value is not None and cell_value != "":  # 非空单元格
                if start_row is None:  # 找到第一个非空单元格
                    start_row = row_index
                    start_value = cell_value
                    end_row = row_index  # 初始时，结束行就是起始行
                elif cell_value != start_value:  # 遇到不同内容的非空单元格
                    # 合并单元格 (如果 end_row 有效)
                    if end_row is not None:
                        sheet.merge_cells(
                            start_row=start_row,
                            start_column=col_index + 1,
                            end_row=end_row,  # 使用 end_row
                            end_column=col_index + 1,
                        )
                        merged_cell = sheet.cell(row=start_row, column=col_index + 1)
                        merged_cell.alignment = Alignment(
                            horizontal="center", vertical="center", wrap_text=True
                        )
                        merged_cell.value = start_value

                    # 重置起始位置和结束位置
                    start_row = row_index
                    start_value = cell_value
                    end_row = row_index
                else:  # 遇到相同内容的非空单元格
                    end_row = row_index  # 更新结束行

            elif start_row is not None:  # 遇到空单元格，且已经有起始位置
                end_row = row_index      # 更新结束行

        # 处理最后一批单元格（如果存在）
        if start_row is not None and end_row is not None:
            sheet.merge_cells(
                start_row=start_row,
                start_column=col_index + 1,
                end_row=end_row,  # 使用 end_row
                end_column=col_index + 1,
            )
            merged_cell = sheet.cell(row=start_row, column=col_index + 1)
            merged_cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
            merged_cell.value = start_value

    workbook.save(filename)  # 保存修改


def merge_temp_files(temp_files: List[Path]) -> str:
    """合并临时Markdown表格文件"""
    full_content = []

    for i, file_path in enumerate(sorted(temp_files)):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().splitlines()

            if i == 0:
                # 保留第一个文件的完整头
                full_content.extend(content)
            else:
                # 跳过后续文件的头两行（标题和分隔符）
                full_content.extend(content[2:])

    return "\n".join(full_content)


def read_docx_content(file_path):
    """
    读取 .docx 文件的文本内容。

    Args:
        file_path (str): Word 文档的路径。

    Returns:
        str: 文档的文本内容，段落之间用换行符分隔。
             如果文件不存在或读取失败，则返回 None 或错误信息。
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误：文件未找到 - {file_path}")
        return None
    # 检查文件扩展名是否为 .docx
    if not file_path.lower().endswith('.docx'):
        print(f"警告：文件 '{os.path.basename(file_path)}' 可能不是标准的 .docx 格式。尝试读取...")
    # 注意：虽然我们会尝试，但 python-docx 主要用于 .docx

    try:
        # 打开 Word 文档
        doc = docx.Document(file_path)

        # 用于存储所有段落文本的列表
        full_text = []

        # 遍历文档中的所有段落
        for para in doc.paragraphs:
            full_text.append(para.text)

        # 将列表中的所有文本连接成一个字符串，段落间用换行符分隔
        return '\n'.join(full_text)

    except docx.opc.exceptions.PackageNotFoundError:
        print(f"错误：无法打开文件，可能不是有效的 Word (.docx) 文件 - {file_path}")
        return None
    except Exception as e:
        print(f"读取文件时发生未知错误：{e}")
        return None


# --- 使用示例 ---
if __name__ == "__main__":
    # --- !!! 修改为你实际的 Word 文档路径 !!! ---
    # 例如: 'C:/Users/YourUser/Documents/mydocument.docx' (Windows)
    # 或: '/home/youruser/documents/mydocument.docx' (Linux/Mac)
    word_file_path = 'C:\\Users\\yangkw\\Desktop\\temp\\【集团需求】关于一级家开平台订购流程和数据一致性优化改造需求 - 关于数据一致性.docx'  # <--- 在这里替换成你的文件路径

    print(f"正在尝试读取文件: {word_file_path}")

    # 调用函数读取内容
    content = read_docx_content(word_file_path)

    # 如果成功读取到内容，则打印
    if content is not None:
        print("\n--- 文档内容 ---")
        print(content)
        print("--- 内容结束 ---")
    else:
        print("\n未能成功读取文档内容。")