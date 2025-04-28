import re
from collections import defaultdict
from typing import Tuple, Dict, List, Any, Optional

# --- 基于提示词规则定义的常量 ---

# 预期表头列名和顺序 (强制规则 2)
EXPECTED_COLUMNS = [
    "客户需求", "功能用户", "功能用户需求", "触发事件", "功能过程",
    "子过程描述", "数据移动类型", "数据组", "数据属性", "复用度", "CFP", "ΣCFP"
]

# 指示查询类功能过程的关键字 (强制规则 8.a) - 用于判断行数规则
QUERY_KEYWORDS = ["查询", "查看", "获取", "展示"]

# 有效的数据移动类型 (强制规则 9)
VALID_DATA_MOVEMENT_TYPES = {'E', 'R', 'W', 'X'}

# '子过程描述' 中的绝对禁止关键字 (强制规则 8.f)
# 注意: 检查时会转换为小写进行匹配
FORBIDDEN_KEYWORDS_SUBPROCESS_ABSOLUTE = {
    "临时表", "内存", "缓存", "检验", "校验", "分析", "判断", "解析",
    "后台", "数据库读取", "接口返回", "接口调用", "生成一条"
}

# '子过程描述' 中的其他禁止关键字或模式 (强制规则 8.f)
# 注意: 检查时会转换为小写进行匹配
FORBIDDEN_KEYWORDS_SUBPROCESS_OTHER = {
    "组装报文", "构建报文", "日志保存", "写日志", "加载",
    "初始化", "点击按钮", "页面", "渲染",
    "保存", # 特指UI保存按钮
    "输入", # 特指UI输入动作
    "读取", # 特指底层IO
    "获取", # 过于泛化时
    "输出", # 特指底层IO
    "切换", "计算", "重置", "分页", "排序", "适配", "开发", "部署", "系统"
    "迁移", "安装", "存储", # 特指物理存储
    "调用" # 特指调用接口
}
# 用于匹配 '校验XXX', '验证XXX', '检查XXX', '判断XXX' 的正则表达式 (强制规则 8.f)
FORBIDDEN_PATTERN_REGEX = re.compile(r'(校验|验证|检查|判断)\S+')


# 固定列的预期值 (强制规则 12)
FIXED_VALUES = {
    "复用度": "新增",
    "CFP": "1",
    "ΣCFP": "1"
}

# 数据属性规则 (强制规则 11)
MIN_ATTR = 3
MAX_ATTR = 10
ATTR_SEPARATOR = r'[，,、]' # 支持中文逗号、英文逗号和顿号
# 用于检查数据属性是否只包含中文、字母、数字和指定分隔符的正则
VALID_ATTR_CHAR_REGEX = re.compile(r'^[a-zA-Z0-9\u4e00-\u9fa5，,、\s]+$')
# 用于检查是否包含英文字段名的正则 (简单检查，可能误判)
ENGLISH_FIELD_REGEX = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b')


# 子过程描述模板动词 (强制规则 8.b, 9.b) - 用于一致性检查
TEMPLATE_VERBS = {
    'E': ['输入'],
    'R': ['读取'],
    'W': ['保存', '更新', '删除'], # 允许多个，检查是否是其中之一
    'X': ['返回', '输出', '发送']  # 允许多个，检查是否是其中之一
}

# --- 辅助函数 ---

def parse_markdown_table(markdown_table_str: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    解析 Markdown 表格字符串为字典列表 (每行一个字典)。
    返回解析后的数据和解析过程中发现的格式错误列表。

    Args:
        markdown_table_str: 包含 Markdown 表格的字符串。

    Returns:
        一个元组，包含:
        - data (List[Dict[str, str]]): 解析后的表格数据，每个字典代表一行。
        - errors (List[str]): 解析过程中遇到的格式错误信息。
    """
    lines = [line.strip() for line in markdown_table_str.strip().split('\n')]
    errors = []
    data = []
    header = []
    header_checked = False
    actual_headers = [] # 存储实际解析到的表头，即使它不符合预期

    if len(lines) < 3:
        # 错误提示：表格结构不完整
        errors.append("格式错误：表格必须包含表头、分隔符和至少一行数据。请确保表格结构完整。")
        return data, errors

    for i, line in enumerate(lines):
        # 检查行是否以 | 开始和结束
        if not line.startswith('|') or not line.endswith('|'):
            # 特殊处理分隔符行，允许不严格闭合，但内容要符合规范
            if i == 1 and re.match(r'^[| :\-]+$', line):
                cells = [cell.strip() for cell in line.strip('|').split('|')]
                # 检查分隔符单元格是否为 --- 或 :---: 等形式
                if not all(re.match(r'^-+$', cell.replace(':', '')) for cell in cells if cell):
                    # 仅作为格式建议，不阻塞校验
                    # errors.append(f"格式建议 (第 {i+1} 行): 分隔符行格式不完全符合标准 Markdown (例如 `|---|---|`)。虽然不影响本次解析，但建议修正以确保兼容性。")
                    pass # 不添加错误，因为提示词未强制分隔符格式
                continue # 跳过分隔符行处理
            else:
                # 错误提示：行格式不正确
                errors.append(f"格式错误 (第 {i+1} 行): 表格的每一行（包括表头和数据行）都必须以 '|' 开始并以 '|' 结束。请修正行 '{line}' 的格式。")
                continue # 跳过此行

        # 去掉首尾 '|' 并按 '|' 分割单元格
        cells = [cell.strip() for cell in line[1:-1].split('|')]

        if i == 0: # 处理表头
            actual_headers = cells # 记录实际的表头
            # --- 表头校验 (强制规则 2) ---
            if actual_headers != EXPECTED_COLUMNS:
                # 错误提示：表头不符合要求
                errors.append(f"表头错误: 表格的列名或顺序不正确。\n规则要求列为: {EXPECTED_COLUMNS}\n当前表格列为: {actual_headers}\n请严格按照规则要求的列名和顺序修改表头。")
                # 即使表头错误，也标记为已检查，并使用实际表头尝试继续解析
            header = actual_headers # 使用实际表头进行后续解析
            header_checked = True
        elif i == 1: # 跳过分隔符行 (已在前面处理)
            continue
        else: # 处理数据行
            if not header_checked:
                 # 错误提示：未解析到表头
                 errors.append("解析中断：由于未能正确解析表头，无法继续处理数据行。请先修正表头问题。")
                 break # 无法继续

            # 检查数据行单元格数量是否与表头匹配
            if len(cells) != len(header):
                # 错误提示：单元格数量不匹配
                errors.append(f"数据行结构错误 (第 {i+1} 行): 该行包含 {len(cells)} 个单元格，但表头有 {len(header)} 列。每一数据行必须包含与表头相同数量的单元格。请修正该行。")
                continue # 跳过此行，因为它无法正确映射到列

            # 将单元格数据与表头组合成字典
            row_data = dict(zip(header, cells))
            data.append(row_data)

    # 如果表头检查通过但没有数据行被成功解析
    if header_checked and not data and len(lines) > 2:
         # 仅作为警告，不阻塞
         # errors.append("解析警告：成功解析表头，但未能解析任何有效的数据行。请检查数据行的格式。")
         pass

    return data, errors

# --- 主校验函数 ---

def validate_cosmic_table(markdown_table_str: str, table_rows: Optional[int] = None) -> Tuple[bool, str]:
    """
    校验 AI 生成的 COSMIC 度量 Markdown 表格是否符合所有强制规则。

    Args:
        markdown_table_str: AI 生成的包含 Markdown 表格的字符串。

    Returns:
        一个元组，包含:
        - is_valid (bool): 如果表格符合所有强制规则，则为 True，否则为 False。
        - error_message (str): 如果校验失败，包含所有检测到的错误信息，每条占一行；
                               如果校验成功，则为空字符串。
    """
    final_errors: List[str] = [] # 存储最终返回的所有错误信息

    # 1. 解析 Markdown 表格
    parsed_data, parsing_errors = parse_markdown_table(markdown_table_str)
    final_errors.extend(parsing_errors)

    # 如果解析本身出错严重，或者没有解析到数据，则提前返回
    if not parsed_data:
        if not final_errors: # 如果解析没报错但没数据，加个通用错误
            final_errors.append("校验中断：未能从输入中解析出任何有效的表格数据。")
        # 即使解析有错，也返回 False 和错误信息
        return (not final_errors), "\n".join(final_errors)

    # 如果表头不匹配，后续基于列名的校验可能无效，但仍可进行部分检查
    headers_match = EXPECTED_COLUMNS == list(parsed_data[0].keys()) if parsed_data else False


    # --- 逐行校验 ---
    # 存储每一行的信息，包括行号，方便错误定位
    table_rows_with_index = []
    for i, row in enumerate(parsed_data):
        table_rows_with_index.append({"index": i, "data": row, "row_num": i + 3}) # row_num 是原始 markdown 行号

    # --- 校验固定值 (强制规则 12) ---
    if headers_match: # 只有在表头正确时才能按列名校验
        for row_info in table_rows_with_index:
            row_num = row_info["row_num"]
            row_data = row_info["data"]
            for col, expected_value in FIXED_VALUES.items():
                actual_value = row_data.get(col, "").strip()
                if actual_value != expected_value:
                    # 错误提示：固定值不匹配
                    final_errors.append(f"固定值错误 (第 {row_num} 行, 列 '{col}'): 值应为 '{expected_value}'，但当前为 '{actual_value}'。请修正此单元格的值。")

    # --- 校验数据移动类型 (强制规则 9) ---
    if headers_match:
        for row_info in table_rows_with_index:
            row_num = row_info["row_num"]
            dm_type = row_info["data"].get("数据移动类型", "").strip()
            if dm_type not in VALID_DATA_MOVEMENT_TYPES:
                # 错误提示：无效的数据移动类型
                final_errors.append(f"数据移动类型错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 值 '{dm_type}' 不是有效的数据移动类型 ({VALID_DATA_MOVEMENT_TYPES})。请使用 E, R, W, 或 X 中的一个。")

    # --- 校验数据属性 (强制规则 11) ---
    if headers_match:
        for row_info in table_rows_with_index:
            row_num = row_info["row_num"]
            attributes_str = row_info["data"].get("数据属性", "").strip()
            if not attributes_str:
                # 错误提示：数据属性不能为空 (隐含强制)
                final_errors.append(f"数据属性错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 数据属性不能为空。请填写 3-10 个关键业务属性。")
                continue

            attributes = [attr.strip() for attr in re.split(ATTR_SEPARATOR, attributes_str) if attr.strip()]
            attr_count = len(attributes)

            # 检查数量 (强制)
            if not (MIN_ATTR <= attr_count <= MAX_ATTR):
                # 错误提示：属性数量不符合要求
                final_errors.append(f"数据属性数量错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 属性数量为 {attr_count}，要求在 {MIN_ATTR} 到 {MAX_ATTR} 个之间。请调整属性数量。")

            # 检查内容格式 (强制)
            if not VALID_ATTR_CHAR_REGEX.match(attributes_str):
                 # 错误提示：包含无效字符
                 final_errors.append(f"数据属性格式错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 属性 '{attributes_str}' 中包含除中文、字母、数字、空格和中文逗号之外的字符。要求使用中文业务术语。请修正。")
            # 检查是否包含疑似英文/数据库字段名 (强制禁止)
            for attr in attributes:
                # 允许纯大写缩写如ID, GUID, URL等，或者包含数字的如 10GPON
                if ENGLISH_FIELD_REGEX.search(attr) and not re.match(r'^[A-Z0-9/]+$', attr):
                     # 错误提示：包含英文字段名
                     final_errors.append(f"数据属性格式错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 属性 '{attr}' 包含英文或数据库字段名。要求使用中文业务术语。请检查并修正。")


    # --- 校验子过程描述 (强制规则 8) ---
    if headers_match:
        # 检查禁止词和与功能过程名称的对比
        for row_info in table_rows_with_index:
            row_num = row_info["row_num"]
            sub_process_desc = row_info["data"].get("子过程描述", "").strip()
            process_name = row_info["data"].get("功能过程", "").strip()
            sub_process_desc_lower = sub_process_desc.lower() # 转小写用于匹配禁止词

            if not sub_process_desc:
                 # 错误提示：子过程描述不能为空 (隐含强制)
                 final_errors.append(f"子过程描述错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 子过程描述不能为空。请填写。")
                 continue

            # 检查绝对禁止词 (强制规则 8.f)
            for keyword in FORBIDDEN_KEYWORDS_SUBPROCESS_ABSOLUTE:
                if keyword in sub_process_desc_lower:
                    # 错误提示：包含绝对禁止词
                    final_errors.append(f"子过程描述禁止词错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 子过程描述 '{sub_process_desc}' 中包含绝对禁止使用的关键字 '{keyword}'。请移除该关键字。")

            # 检查其他禁止词 (强制规则 8.f)
            for keyword in FORBIDDEN_KEYWORDS_SUBPROCESS_OTHER:
                 if keyword in sub_process_desc_lower and keyword not in ['输入', '读取', '保存', '更新', '删除', '返回', '输出', '发送']: # 排除模板动词本身
                    # 错误提示：包含其他禁止词
                     final_errors.append(f"子过程描述禁止词错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 子过程描述 '{sub_process_desc}' 中包含禁止使用的关键字 '{keyword}'。请移除或替换该关键字。")

            # 检查禁止模式 (如 '校验XXX') (强制规则 8.f)
            match = FORBIDDEN_PATTERN_REGEX.search(sub_process_desc)
            if match:
                # 错误提示：包含禁止模式
                        final_errors.append(f"子过程描述禁止模式错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 子过程描述 '{sub_process_desc}' 中包含禁止使用的模式 '{match.group(0)}' (如 '校验XXX')。请修改描述，避免此类校验/判断性词语。")

            # 检查是否与功能过程名称相同 (强制规则 8.c)
            if sub_process_desc == process_name:
                # 错误提示：子过程与功能过程相同
                final_errors.append(f"子过程描述冗余错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 子过程描述 '{sub_process_desc}' 与其对应的功能过程名称 '{process_name}' 完全相同。子过程必须是对功能过程的分解，不能相同。请修改子过程描述。")


    # --- 按功能过程分组，校验序列、行数、唯一性、一致性 (强制规则 8, 9) ---
    if headers_match:
        # 使用功能过程名称和触发事件作为分组键
        grouped_processes: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for row_info in table_rows_with_index:
            process_name = row_info["data"].get("功能过程", "未知功能过程")
            trigger_event = row_info["data"].get("触发事件", "未知触发事件")
            grouped_processes[(process_name, trigger_event)].append(row_info)

        for (process_name, trigger_event), rows_info in grouped_processes.items():
            # 对同一功能过程的行按原始行号排序
            rows_info.sort(key=lambda x: x["index"])
            rows_data = [info["data"] for info in rows_info]
            row_nums = [info["row_num"] for info in rows_info]
            start_row, end_row = row_nums[0], row_nums[-1]
            row_count = len(rows_data)

            dm_types = [row.get("数据移动类型", "") for row in rows_data]
            sub_descs = [row.get("子过程描述", "") for row in rows_data]
            data_groups = [row.get("数据组", "") for row in rows_data] # 用于可能的未来一致性检查

            # 校验数据移动类型序列基础规则 (强制规则 9)
            if row_count > 0:
                first_dm_type = dm_types[0]
                last_dm_type = dm_types[-1]
                # 检查开头
                if first_dm_type != 'E':
                    # 错误提示：序列未以 E 开头
                    final_errors.append(f"数据移动序列错误 (功能过程: '{process_name}', 触发事件: '{trigger_event}', 数据行 {rows_info[0]['index']+1}-{rows_info[-1]['index']+1} (文件行 {start_row}-{end_row})): 功能过程的第一步必须是 'E'，当前为 '{first_dm_type}'。请修正序列。")
                # 检查结尾
                if last_dm_type not in ('W', 'X'):
                     # 错误提示：序列未以 W 或 X 结尾
                    final_errors.append(f"数据移动序列错误 (功能过程: '{process_name}', 触发事件: '{trigger_event}', 数据行 {rows_info[0]['index']+1}-{rows_info[-1]['index']+1} (文件行 {start_row}-{end_row})): 功能过程的最后一步必须是 'W' 或 'X'，当前为 '{last_dm_type}'。请修正序列。")
                # 检查不允许的相邻组合 (WX, XW, XR)
                for i in range(row_count - 1):
                    pair = dm_types[i] + dm_types[i+1]
                    if pair in ('WX', 'XW', 'XR'):
                         # 错误提示：包含无效的相邻类型
                        final_errors.append(f"数据移动序列错误 (功能过程: '{process_name}', 触发事件: '{trigger_event}', 数据行 {rows_info[i]['index']+1}-{rows_info[i+1]['index']+1} (文件行 {row_nums[i]}-{row_nums[i+1]})): 检测到无效的序列 '{pair}'。请修正数据移动类型序列，避免 WX, XW, XR 组合。")

            # 校验查询类行数和序列 (强制规则 8.a)
            is_query = any(keyword in process_name for keyword in QUERY_KEYWORDS)
            if is_query:
                expected_rows = 3
                expected_sequence = "ERX"
                if row_count != expected_rows:
                    # 错误提示：查询类行数不为 3
                    final_errors.append(f"子过程行数错误 (功能过程: '{process_name}', 触发事件: '{trigger_event}', 数据行 {rows_info[0]['index']+1}-{rows_info[-1]['index']+1} (文件行 {start_row}-{end_row})): 功能过程是查询类，要求必须有 {expected_rows} 行 ({expected_sequence})，实际有 {row_count} 行。请修正子过程数量和对应的数据移动类型。")
                elif "".join(dm_types) != expected_sequence:
                     # 错误提示：查询类序列不为 ERX
                     final_errors.append(f"数据移动序列错误 (功能过程: '{process_name}', 触发事件: '{trigger_event}', 数据行 {rows_info[0]['index']+1}-{rows_info[-1]['index']+1} (文件行 {start_row}-{end_row})): 功能过程是查询类，要求数据移动类型序列必须为 '{expected_sequence}'，当前为 '{''.join(dm_types)}'。请修正数据移动类型。")
            # else: # 非查询类
                # 非查询类的行数 (2行) 和序列 (EW/EX) 是建议性的，不在此处强制校验

            # 校验子过程描述唯一性 (强制规则 8.e)
            seen_sub_descs = set()
            for i, desc in enumerate(sub_descs):
                if desc in seen_sub_descs:
                    # 错误提示：子过程描述重复
                    final_errors.append(f"子过程描述重复错误 (功能过程: '{process_name}', 触发事件: '{trigger_event}', 数据行 {rows_info[i]['index']+1} (文件行 {row_nums[i]})): 在同一个功能过程内，子过程描述 '{desc}' 重复出现。每个子过程描述应唯一。请修改重复的描述以体现差异。")
                seen_sub_descs.add(desc)

            # 校验子过程描述模板动词 (强制规则 8.b, 9.b)
            for i in range(row_count):
                dm_type = dm_types[i]
                desc = sub_descs[i]
                row_num = row_nums[i]
                if dm_type in TEMPLATE_VERBS:
                    expected_verbs = TEMPLATE_VERBS[dm_type]
                    # 检查描述是否以模板动词之一开头
                    if not any(desc.startswith(verb) for verb in expected_verbs):
                         # 错误提示：未使用模板动词开头
                        final_errors.append(f"子过程描述动词错误 (数据行 {row_info['index']+1} (文件行 {row_num})): 数据移动类型为 '{dm_type}'，但子过程描述 '{desc}' 未使用建议的动词 ({expected_verbs}) 开头。请使用推荐动词之一修正描述。")

            # 术语一致性 ("信息" vs "数据") 是建议性的，不在此处强制校验

    # 数据属性差异性 (EW/ERX) 是建议性的，不在此处强制校验

    # --- 校验表格行数 (如果提供了预期行数) ---
    if table_rows is not None and parsed_data:
        actual_rows = len(parsed_data)
        min_rows = int(table_rows * 0.7)  # 10% lower bound
        max_rows = int(table_rows * 1.1)  # 10% upper bound
        
        if not (min_rows <= actual_rows <= max_rows):
            final_errors.append(
                f"表格行数错误: 预期行数约为 {table_rows} (允许±10%浮动)，实际行数为 {actual_rows}。"
                f"请检查表格内容是否符合功能过程数量要求。"
            )

    # --- 返回结果 ---
    is_valid = not final_errors
    # 使用集合去重错误信息，然后转换回列表保持顺序（如果需要）或直接join
    unique_errors = sorted(list(set(final_errors)), key=final_errors.index) # 保持首次出现的顺序
    error_message = "\n".join(unique_errors)

    return is_valid, error_message
