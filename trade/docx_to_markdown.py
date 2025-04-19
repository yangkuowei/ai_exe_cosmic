# -*- coding: utf-8 -*-
import docx
import os
import re  # 用于简化列表处理


def get_paragraph_text(p):
    """
    获取段落内所有 Run 的文本，并处理基本的加粗和斜体。
    """
    text = ""
    for run in p.runs:
        run_text = run.text
        # 替换掉 Word 中可能的特殊空白符，如不间断空格
        run_text = run_text.replace('\u00A0', ' ')

        is_bold = run.bold
        is_italic = run.italic

        processed_text = run_text.strip() if run_text else ""  # 处理空的 run 或只有空格的 run

        # 仅在有实际内容时添加标记
        if processed_text:
            if is_bold and is_italic:
                text += f"***{processed_text}***"
            elif is_bold:
                text += f"**{processed_text}**"
            elif is_italic:
                text += f"*{processed_text}*"
            else:
                # 对于非粗非斜的文本，保留原始文本（可能包含首尾空格，后面统一处理）
                text += run_text
        elif run_text:  # 如果原始 run_text 不是空的（例如只包含空格）
            text += run_text  # 保留这些空格，以便后续连接

    # 清理和规范化空格：将多个空格替换为单个空格，并去除首尾多余空格
    # 但请注意，这可能会影响代码块等需要精确空格的场景（当前脚本未处理代码块）
    text = ' '.join(text.split())
    return text


def convert_word_to_markdown(docx_path, md_path):
    """
    将指定的 Word 文档转换为 Markdown 文件。

    Args:
        docx_path (str): 输入的 Word 文档 (.docx) 文件路径。
        md_path (str): 输出的 Markdown (.md) 文件路径。
    """
    try:
        document = docx.Document(docx_path)
        md_content = []
        list_level = 0  # 用于跟踪列表层级（简化处理）
        list_type = None  # 'bullet' or 'number'
        prev_para_was_list = False  # 标记上一个段落是否是列表项

        for i, para in enumerate(document.paragraphs):
            current_para_is_list = False  # 标记当前段落是否是列表项
            md_line = ""  # 当前段落转换后的 Markdown 行

            # --- 1. 处理标题 ---
            style_name = para.style.name.lower()
            heading_level = 0
            if style_name.startswith('heading'):
                try:
                    level_str = style_name.split()[-1]
                    if level_str.isdigit():
                        heading_level = int(level_str)
                        heading_level = max(1, min(6, heading_level))
                except (IndexError, ValueError):
                    print(
                        f"Warning: Could not parse heading level from style '{para.style.name}'. Treating as normal text.")
                    heading_level = 0

            if heading_level > 0:
                para_text = get_paragraph_text(para).strip()
                if para_text:  # 确保标题有内容
                    md_line = "#" * heading_level + " " + para_text
                list_type = None  # 标题后重置列表状态
                current_para_is_list = False
            else:
                # --- 2. 处理列表 (简化版) ---
                # 检查段落格式中的 numId (更可靠的方式判断列表)
                is_list_item = False
                num_fmt = None  # list format (e.g., bullet, decimal)
                try:
                    # 检查是否存在编号属性 <w:numPr>
                    numpr_elem = para._element.xpath('.//w:numPr')
                    if numpr_elem:
                        is_list_item = True
                        # 尝试获取列表类型 (bullet or number) - 这部分比较复杂，简化处理
                        # 通过检查 numFmt 的值来区分
                        numfmt_elem = para._element.xpath('.//w:numFmt')
                        if numfmt_elem and len(numfmt_elem) > 0:
                            num_fmt = numfmt_elem[0].get(docx.oxml.shared.qn('w:val'))

                        # 尝试获取列表层级 ilvl (用于缩进) - 同样简化
                        ilvl_elem = para._element.xpath('.//w:ilvl')
                        current_level = 0
                        if ilvl_elem and len(ilvl_elem) > 0:
                            level_val = ilvl_elem[0].get(docx.oxml.shared.qn('w:val'))
                            if level_val and level_val.isdigit():
                                current_level = int(level_val)

                        indentation = "  " * current_level  # Markdown 缩进 (2 spaces per level)

                        para_text = get_paragraph_text(para).strip()

                        # 移除 Word 自动添加的列表标记（如果存在于文本开头）
                        # 注意：这可能误删用户输入的类似标记
                        para_text = re.sub(r'^\s*[\*\-•]\s+', '', para_text)  # 移除常见项目符号
                        para_text = re.sub(r'^\s*\d+[\.)]\s+', '', para_text)  # 移除常见数字标记

                        if para_text:  # 确保列表项有内容
                            if num_fmt == 'decimal' or num_fmt == 'decimalEnclosedCircle' or (
                                    num_fmt is None and list_type == 'number'):  # 假设数字列表
                                md_line = f"{indentation}1. {para_text}"
                                list_type = 'number'  # 记住当前列表类型
                            else:  # 默认或识别为项目符号
                                md_line = f"{indentation}- {para_text}"
                                list_type = 'bullet'  # 记住当前列表类型
                            current_para_is_list = True
                        else:  # 如果列表项为空，则忽略
                            list_type = None
                            current_para_is_list = False

                except Exception as e:
                    # XPath 或属性访问可能出错，打印警告并回退到普通段落
                    print(f"Warning: Error processing list item properties: {e}. Treating as normal text.")
                    is_list_item = False
                    list_type = None
                    current_para_is_list = False

                # --- 3. 处理普通段落 ---
                if not is_list_item and heading_level == 0:
                    para_text = get_paragraph_text(para).strip()
                    if para_text:
                        md_line = para_text
                    list_type = None  # 非列表项，重置列表状态
                    current_para_is_list = False

            # --- 添加处理后的行到结果列表 ---
            if md_line:  # 只添加有内容的行
                # 处理段落间距：
                # - 在标题后总是添加空行 (通过 \n\n join 实现)
                # - 在连续的列表项之间不添加额外空行
                # - 在列表项和普通段落之间添加空行
                # - 在普通段落之间添加空行 (通过 \n\n join 实现)

                # 如果当前是列表项，并且上一个也是列表项，则直接添加
                if current_para_is_list and prev_para_was_list:
                    md_content.append(md_line)
                # 否则（标题、普通段落、列表项的开始、列表项后的第一个非列表项）
                # 使用分隔符（None）来让后续的 join 添加空行
                else:
                    if md_content and md_content[-1] is not None:  # 避免在开头加分隔符或连续加分隔符
                        md_content.append(None)  # 用 None 作为分隔符标记
                    md_content.append(md_line)

            prev_para_was_list = current_para_is_list  # 更新上一个段落的状态

        # --- 4. 组合并写入文件 ---
        # 过滤掉 None 分隔符，并用 '\n\n' 连接非列表项，用 '\n' 连接连续列表项
        final_md_lines = []
        for i, line in enumerate(md_content):
            if line is not None:
                final_md_lines.append(line)
            # 如果当前行是 None (表示需要空行)，并且不是最后一个元素，
            # 并且下一个元素也不是 None (避免多个空行)
            elif i < len(md_content) - 1 and md_content[i + 1] is not None:
                final_md_lines.append("")  # 添加一个空字符串代表空行

        final_md = "\n".join(final_md_lines)

        # 简单的后处理：确保标题后至少有一个空行
        final_md = re.sub(r'(^#+ .*\n)(?![\n#])', r'\1\n', final_md, flags=re.MULTILINE)
        # 简单的后处理：确保列表结束后有空行（如果后面不是另一个列表或标题）
        final_md = re.sub(r'(^([ \t]*)([\*\-\+]|\d+\.) .*\n)(?![\n\1])', r'\1\n', final_md, flags=re.MULTILINE)

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(final_md)

        print(f"Successfully converted '{docx_path}' to '{md_path}'")

    except FileNotFoundError:
        print(f"Error: Input file not found at '{docx_path}'")
    except Exception as e:
        print(f"An error occurred during conversion: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # --- 配置区 ---
    # 在这里修改你要转换的 Word 文档的路径和文件名
    # 例如: "C:/Users/YourUser/Documents/报告.docx"
    # 或者只是文件名 (如果文件在脚本所在的目录下): "我的文档.docx"
    input_docx_path = "广西CHBN融合项目总体设计说明_V1.5.docx"
    # --- 配置区结束 ---

    # 检查输入文件是否存在且是 .docx 文件
    if not os.path.exists(input_docx_path):
        print(f"错误：输入文件未找到 '{input_docx_path}'")
    elif not input_docx_path.lower().endswith('.docx'):
        print(f"错误：输入文件 '{input_docx_path}' 不是有效的 .docx 文件。")
    else:
        # 自动生成输出文件名 (例如: 你的示例文档.md)
        base_name = os.path.splitext(input_docx_path)[0]
        output_md_path = base_name + ".md"

        print(f"正在将 '{input_docx_path}' 转换为 '{output_md_path}'...")
        convert_word_to_markdown(input_docx_path, output_md_path)

