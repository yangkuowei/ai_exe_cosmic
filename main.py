from functools import partial

import os

from ai_exe_cosmic.openAi_cline import call_ai
from ai_exe_cosmic.read_file_content import process_markdown_table
from ai_exe_cosmic.read_file_content import read_file_content, save_content_to_file, extract_number
from ai_exe_cosmic.validate_cosmic_table import validate_cosmic_table, extract_table_from_text, extract_json_from_text, validate_trigger_event_json

'''
一、生成触发事件列表
1. 读取/ai_promote/create_trigger_events.md文件得到生成触发事件的AI系统提示词
2. 根据文件名读取requirements目录下的指定文件内容作为AI生成触发事件列表的输入
3. 调用AI大模型生成内容
4. 校验AI生成结果
 - 校验不通过则把校验结果传给AI继续生成
 - 校验通过则提取JSON数据，在/out_put_files目录下新建一个目录（如果不存在），然后在新建的目录下新建一个文件保存JSON数据，文件名是第2步中的文件名+JSON.JSON

二、生成cosmic表格
1. 读取/ai_promote/create_cosmic_table_from_trigger_events.md文件得到生成cosmic表格的AI系统提示词
2. 根据文件名读取requirements目录下的指定文件内容，在原有内容基础上追加第一步生成的JSON文件，然后作为AI生成cosmic表格的输入
3. 调用AI大模型生成内容
4. 校验AI生成结果
 - 校验不通过则把校验结果传给AI继续生成
 - 校验通过则在第一中的4生成的目录下新建一个.md文件保存经过校验的markdown格式的表格
 - 读取.md文件合并单元格
 - 将处理过的markdown格式表格转换成excel表格输出到目录下
'''

base_out_put_dir = os.path.join(os.getcwd(), "out_put_files")
# 1. 读取系统提示词 create_trigger_events.md
create_trigger_events_dir = os.path.join(os.getcwd(), "ai_promote")
create_trigger_events_file = os.path.join(create_trigger_events_dir, "create_trigger_events.md")
create_trigger_events_promote = read_file_content(create_trigger_events_file)

# 2. 读取需求内容
request_file_name = '202411291723184关于全光WiFi（FTTR）业务流程-转普通宽带智能网关出库的补充需求.txt'
requirement_file_dir = os.path.join(os.getcwd(), "requirements")
requirement_file = os.path.join(requirement_file_dir, request_file_name)
requirement_ontent = read_file_content(requirement_file)
# 提取
total_rows = extract_number(requirement_ontent)
if total_rows == None:
    raise ValueError(f'{request_file_name} 没有输入表格总行数要求')

# 3. AI大模型调用
# 使用 partial 创建一个新的 validator 函数
custom_validator = partial(validate_trigger_event_json, total_rows=total_rows)
json_str = call_ai(
    create_trigger_events_promote,
    requirement_ontent,
    extract_json_from_text,
    custom_validator,
)
# 保存json文件
save_content_to_file(request_file_name, base_out_put_dir, json_str, content_type="json")

# 4. 读取系统提示词 create_cosmic_table_from_trigger_events.md
create_cosmic_table_dir = os.path.join(os.getcwd(), "ai_promote")
create_cosmic_table_file = os.path.join(create_cosmic_table_dir, "create_cosmic_table_from_trigger_events.md")
create_cosmic_table_promote = read_file_content(create_cosmic_table_file)

# 需求描述后面拼接 json
requirement_ontent_create = f'{requirement_ontent}\n触发事件与功能过程列表：\n{json_str}'

# 5. AI大模型调用
markdown_table_str = call_ai(
    create_cosmic_table_promote,
    requirement_ontent_create,
    extract_table_from_text,
    validate_cosmic_table
)

# 6. 保存经过校验的markdown格式的表格
save_content_to_file(request_file_name, base_out_put_dir, markdown_table_str, content_type="markdown")
# 合并单元格
markdown_table_str = process_markdown_table(markdown_table_str)
# 7. 将处理过的markdown格式表格转换成excel表格输出到目录下
save_content_to_file(request_file_name, base_out_put_dir, markdown_table_str, content_type="xlsx")

# 8. 根据excel表格生成 docx
save_content_to_file(request_file_name, base_out_put_dir, '',content_type="docx")

exit(0)