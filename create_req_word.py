import json
from docxtpl import DocxTemplate
import docx
import os
from docx.shared import Cm # 使用厘米作为单位，也可以用 Inches
# 1. 加载 JSON 数据
json_file_path = 'C:\\Users\\yangkw\\git_rep\\pythonProject\\out_put_files\\梁海祥\\需求规格说明书_202405111579786_关于实体卡工作号绑定、解绑结果通知优化的需求\\req_description_需求规格说明书_202405111579786_关于实体卡工作号绑定、解绑结果通知优化的需求.json' # 你的 JSON 文件路径
with open(json_file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 2. 加载 Word 模板
template_path = 'C:\\Users\\yangkw\\git_rep\\pythonProject\\requirements\\template\\template.docx' # 你的 Word 模板路径
doc = DocxTemplate(template_path)

# 3. 准备上下文数据 (将 JSON 数据映射到模板变量)
#    注意：这里的键需要和你模板中的占位符精确对应
context = {
    'requirement_description': data.get('requirement_description', {}),
    'system_status': data.get('system_status', {}),
    'functional_architecture_diagram': data.get('functional_architecture_diagram', {}),
    # 如果模板直接用顶级键，可以这样扁平化一部分，根据模板设计调整
    'overall_description': data.get('requirement_description', {}).get('overall_description', ''),
    'construction_goals': data.get('requirement_description', {}).get('construction_goals', []),
    'necessity': data.get('requirement_description', {}).get('necessity', []),
    'system_overview': data.get('system_status', {}).get('system_overview', []),
    'implemented_features': data.get('system_status', {}).get('implemented_features', []),
    'existing_problems': data.get('system_status', {}).get('existing_problems', ''),
    # 可以直接传递整个子对象，然后在模板里用 . 访问
    # 'req_desc': data.get('requirement_description', {}), # 模板里用 {{ req_desc.overall_description }}
}

# 4. 渲染模板
doc.render(context)

# 5. 保存新文档
output_path = 'output_document.docx'
doc.save(output_path)

print(f"文档已生成: {output_path}")

# --- 关于 Mermaid 的说明 ---
# 上述脚本会将 Mermaid 代码作为纯文本填充到 Word 中。
# 如果需要自动将 Mermaid 代码渲染成图片并插入 Word，会复杂得多。
# 可能需要：
# 1. 在 Python 脚本中调用 Mermaid CLI (mmdc) 或类似工具，将 Mermaid 代码字符串渲染成图片文件。
# 2. 使用 python-docx 的功能将生成的图片文件插入到渲染后的 Word 文档的指定位置（这比较高级，需要精确定位）。
# 这通常比直接填充文本要复杂很多。



def replace_placeholder_with_image(doc_path, placeholder_text, image_path, width_cm=None):
    """
    在 Word 文档中查找占位符文本并将其替换为图片。

    Args:
        doc_path (str): 要修改的 Word 文档的路径。
        placeholder_text (str): 文档中标记插入位置的唯一占位符文本。
        image_path (str): 要插入的图片文件的路径。
        width_cm (float, optional): 图片的期望宽度（单位：厘米）。
                                   如果为 None，则使用图片的原始宽度。

    Returns:
        bool: 如果成功找到占位符并插入图片，则返回 True，否则返回 False。
    """
    if not os.path.exists(doc_path):
        print(f"错误：找不到文档 '{doc_path}'")
        return False
    if not os.path.exists(image_path):
        print(f"错误：找不到图片 '{image_path}'")
        return False

    try:
        doc = docx.Document(doc_path)
        placeholder_found = False

        # --- 遍历文档中的段落 ---
        for paragraph in doc.paragraphs:
            if placeholder_text in paragraph.text:
                print(f"在段落中找到占位符: '{placeholder_text}'")
                # 清除占位符所在的整个段落内容可能更简单，
                # 但更精确的方法是清除包含占位符的 'run'
                inline = paragraph.runs
                # 从后往前遍历 run，以便安全地修改文本
                for i in range(len(inline) - 1, -1, -1):
                    if placeholder_text in inline[i].text:
                        # 清除包含占位符的 run 的文本
                        inline[i].text = inline[i].text.replace(placeholder_text, '')
                        # 在这个 run 的位置（或紧随其后）添加图片
                        # 注意：直接在原 run 添加图片可能不理想，通常在段落末尾添加新 run 插入
                        # 一个简单的方法是在段落末尾添加图片
                # 在段落末尾添加图片（如果上面清除了占位符）
                # 或者，如果占位符是段落唯一内容，清空段落再添加
                paragraph.clear() # 清空段落所有内容
                run = paragraph.add_run() # 添加一个新的 run
                if width_cm:
                    run.add_picture(image_path, width=Cm(width_cm))
                else:
                    run.add_picture(image_path)
                placeholder_found = True
                print(f"已插入图片 '{os.path.basename(image_path)}'")
                # 如果确定占位符唯一，可以取消注释下面的 break
                # break

        # --- （可选）遍历表格中的单元格 ---
        # 如果你的占位符可能在表格里
        if not placeholder_found: # 只有在段落中没找到时才搜索表格
             for table in doc.tables:
                 for row in table.rows:
                     for cell in row.cells:
                         for paragraph in cell.paragraphs:
                             if placeholder_text in paragraph.text:
                                 print(f"在表格单元格中找到占位符: '{placeholder_text}'")
                                 # 清除占位符并插入图片，逻辑同上
                                 inline = paragraph.runs
                                 for i in range(len(inline) - 1, -1, -1):
                                     if placeholder_text in inline[i].text:
                                         inline[i].text = inline[i].text.replace(placeholder_text, '')
                                 paragraph.clear()
                                 run = paragraph.add_run()
                                 if width_cm:
                                     run.add_picture(image_path, width=Cm(width_cm))
                                 else:
                                     run.add_picture(image_path)
                                 placeholder_found = True
                                 print(f"已在表格单元格插入图片 '{os.path.basename(image_path)}'")
                                 # break # 可能需要跳出多层循环

        if placeholder_found:
            doc.save(doc_path) # 保存修改到原文件
            # 或者保存为新文件: doc.save('final_document_with_images.docx')
            return True
        else:
            print(f"警告：在文档中未找到占位符 '{placeholder_text}'")
            return False

    except Exception as e:
        print(f"处理文档时发生错误: {e}")
        return False

image_path = 'C:\\Users\\yangkw\\git_rep\\pythonProject\\out_put_files\\梁海祥\\需求规格说明书_202405111579786_关于实体卡工作号绑定、解绑结果通知优化的需求\\output.png'
replace_placeholder_with_image(output_path,'sequence_diagram_mermaid', image_path)