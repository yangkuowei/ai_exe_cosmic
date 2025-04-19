import re
import json

import markdown
from typing import List, Dict, Tuple, Set, Optional, Any, Union
from bs4 import BeautifulSoup
import math

# 校验、文本内容提取相关
import re
from typing import List, Dict, Tuple, Set
from typing import Tuple

# 严格禁止的关键字
FORBIDDEN_KEYWORDS_ERROR = ["校验", "验证", "判断", "是否", "日志", "组装", "构建", "切换", "计算", "重置", "分页",
                            "排序", "适配", "开发", "部署", "迁移", "安装", "缓存", "接口"'异常', '维护', '组件',
                            '检查', '组装报文', '构建报文', '日志保存', '写日志', '标记', '策略', '调用XX接口',
                            '调用接口', '执行SQL', '数据适配', '获取数据', '输入密码', '读取配置', '保存设置',
                            '切换状态', '计算总和',"加载", "解析", "初始化", "点击", "按钮", "页面", "渲染",]
#带条件的
FORBIDDEN_KEYWORDS_WARN = [
    "保存",  # 除非 数据移动类型是 W
    "输入",  # 除非 数据移动类型是 E
    "读取",  # 除非 数据移动类型是 R
    "输出",  # 除非 数据移动类型是 X
    "存储",  # 除非 数据移动类型是 W
]


def validate_cosmic_table(markdown_table_str: str, expected_total_rows: int) -> Tuple[bool, str]:
    """
    校验COSMIC功能点度量表格 (V3 - 允许行数10%浮动)。
    此版本校验精简后的Markdown表格结构和内容，并放宽总行数校验。

    参数：
    markdown_table_str (str): Markdown格式的表格字符串。
    expected_total_rows (int): 预期表格中的数据行总数 (来自JSON的tableRows)。

    返回值：
    tuple: (bool, str)，第一个元素表示校验是否通过，
           第二个元素是错误信息字符串（如果校验不通过, 多个错误用换行符分隔）。
    """

    # --- 常量定义 (根据新Prompt更新) ---
    EXPECTED_HEADERS = ["功能用户", "功能用户需求", "触发事件", "功能过程",
                        "子过程描述", "数据移动类型", "数据组", "数据属性"]
    FORBIDDEN_KEYWORDS_PROCESS = FORBIDDEN_KEYWORDS_ERROR

    FORBIDDEN_KEYWORDS_SUBPROCESS = FORBIDDEN_KEYWORDS_ERROR

    KEYWORDS_WARN_SUBPROCESS = FORBIDDEN_KEYWORDS_WARN

    VALID_DATA_MOVE_TYPES = {"E", "X", "R", "W"}
    FUNCTIONAL_USER_REGEX = r"^发起者:\s*.*?\s*接收者：\s*.*$"
    DATA_ATTRIBUTE_REGEX = r"^[\u4e00-\u9fa5\s,，]+$"
    DATA_ATTRIBUTE_SPLIT_REGEX = r"[,，]\s*"
    ROW_COUNT_TOLERANCE = 0.8  # 10% 容忍度

    # --- 主校验逻辑 ---
    errors: List[str] = []
    table_data: List[Dict[str, str]] = []

    # 1. 解析 Markdown 表格
    try:
        table_data = markdown_table_to_list(markdown_table_str)
        if not isinstance(table_data, list):
            raise TypeError("markdown_table_to_list 未返回列表")
        if table_data:
            if not isinstance(table_data[0], dict):
                raise TypeError("markdown_table_to_list 返回的列表元素不是字典")
            first_row_keys = list(table_data[0].keys())
            if set(first_row_keys) != set(EXPECTED_HEADERS):
                return False, f"Markdown表格解析错误：表头不匹配。\n预期: {EXPECTED_HEADERS}\n实际: {first_row_keys}"
            if first_row_keys != EXPECTED_HEADERS:
                return False, f"Markdown表格解析错误：表头顺序不匹配。\n预期: {EXPECTED_HEADERS}\n实际: {first_row_keys}"
    except Exception as e:
        return False, f"Markdown表格解析失败: {e}"

    # 2. 校验总行数 (允许 +/- 10% 浮动)
    actual_total_rows = len(table_data)
    if expected_total_rows > 0:  # 只有当预期行数大于0时才进行浮动校验
        lower_bound = math.floor(expected_total_rows * (1 - ROW_COUNT_TOLERANCE))
        upper_bound = math.ceil(expected_total_rows * (1 + ROW_COUNT_TOLERANCE))
        # 确保下限至少为1（如果预期行数很少）
        lower_bound = max(1, lower_bound)

        if not (lower_bound <= actual_total_rows <= upper_bound):
            errors.append(
                f"表格总行数错误：预期 {expected_total_rows} 行，允许范围 [{lower_bound}, {upper_bound}]，实际为 {actual_total_rows} 行。")
    elif expected_total_rows == 0 and actual_total_rows != 0:
        errors.append(f"表格总行数错误：预期 0 行，实际为 {actual_total_rows} 行。")
    # 如果 expected_total_rows < 0，这是无效输入，但这里不处理，假设输入是有效的正整数或0

    # --- 初始化检查所需的数据结构 ---
    process_rows: Dict[str, List[Dict[str, Any]]] = {} # 用于按功能过程分组行
    all_data_attributes_tuples: Set[Tuple[str, ...]] = set()
    process_entry_details: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
    process_exit_details: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
    process_read_details: Dict[str, List[Tuple[str, Tuple[str, ...]]]] = {}
    # 全局 seen_sub_processes 字典已移除

    # --- 逐行基础校验 ---
    for row_index, row in enumerate(table_data):
        data_row_num = row_index + 1
        file_row_num = data_row_num + 2
        row['_data_row_num'] = data_row_num
        row['_file_row_num'] = file_row_num

        func_user_cell = row.get("功能用户", "")
        func_req_cell = row.get("功能用户需求", "")
        trigger_event_cell = row.get("触发事件", "")
        process_cell = row.get("功能过程", "")
        sub_process_cell = row.get("子过程描述", "")
        data_move_type_cell = row.get("数据移动类型", "")
        data_group_cell = row.get("数据组", "")
        data_attributes_str_cell = row.get("数据属性", "")

        # 规则 3: 功能用户
        if not func_user_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '功能用户' 不能为空。")
        elif not re.match(FUNCTIONAL_USER_REGEX, func_user_cell.replace('\n', '<br>')):
            errors.append(
                f"数据行 {data_row_num} (文件行 {file_row_num}): '功能用户' ({func_user_cell}) 格式错误，应为 '发起者: [系统]<br>接收者：[系统]'。")

        # 规则 4: 功能用户需求
        if not func_req_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '功能用户需求' 不能为空。")

        # 规则 5: 触发事件
        if not trigger_event_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '触发事件' 不能为空。")

        # 规则 6: 功能过程
        if not process_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '功能过程' 不能为空。")
        else:
            for keyword in FORBIDDEN_KEYWORDS_PROCESS:
                if keyword == "调用XX接口" and "调用" in process_cell and "接口" in process_cell:
                    errors.append(
                        f"数据行 {data_row_num} (文件行 {file_row_num}): '功能过程' ({process_cell}) 包含禁用模式 '调用XX接口'。")
                elif keyword != "调用XX接口" and keyword in process_cell:
                    errors.append(
                        f"数据行 {data_row_num} (文件行 {file_row_num}): '功能过程' ({process_cell}) 包含禁用关键字 '{keyword}'。")

        # 规则 7: 子过程描述
        if not sub_process_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' 不能为空。")
        else:
            if sub_process_cell == process_cell:
                errors.append(
                    f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' ({sub_process_cell}) 不能与 '功能过程' 相同。")
            # 全局子过程重复检查逻辑已移除
            # 检查禁用关键字
            for keyword in FORBIDDEN_KEYWORDS_SUBPROCESS:
                if keyword == "调用XX接口" and "调用" in sub_process_cell and "接口" in sub_process_cell:
                    errors.append(
                        f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' ({sub_process_cell}) 包含禁用模式 '调用XX接口'。")
                elif keyword != "调用XX接口" and keyword in sub_process_cell:
                    errors.append(
                        f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' ({sub_process_cell}) 包含禁用关键字 '{keyword}'。")

            # 检查带条件的关键字
            for keyword in KEYWORDS_WARN_SUBPROCESS:
                if keyword in sub_process_cell:
                    if (keyword in ["保存", "存储"] and data_move_type_cell != "W") or \
                       (keyword == "输入" and data_move_type_cell != "E") or \
                       (keyword == "读取" and data_move_type_cell != "R") or \
                       (keyword == "输出" and data_move_type_cell != "X"):
                        errors.append(
                            f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' ({sub_process_cell}) 包含关键字 '{keyword}' 但数据移动类型为 '{data_move_type_cell}'，应为 " +
                            ("'W'" if keyword in ["保存", "存储"] else "'E'" if keyword == "输入" else "'R'" if keyword == "读取" else "'X'"))

        # 规则 8: 数据移动类型
        if data_move_type_cell not in VALID_DATA_MOVE_TYPES:
            errors.append(
                f"数据行 {data_row_num} (文件行 {file_row_num}): '数据移动类型' ({data_move_type_cell}) 无效，必须是 E, X, R, W 中的一个。")

        # 规则 9: 数据组
        if not data_group_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '数据组' 不能为空。")

        # 规则 10: 数据属性
        if not data_attributes_str_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '数据属性' 不能为空。")
        else:
            if not re.fullmatch(DATA_ATTRIBUTE_REGEX, data_attributes_str_cell):
                invalid_chars = "".join(sorted(list(set(re.sub(r'[\u4e00-\u9fa5\s,，]', '', data_attributes_str_cell)))))
                errors.append(
                    f"数据行 {data_row_num} (文件行 {file_row_num}): '数据属性' ({data_attributes_str_cell}) 包含非中文字符 。应该全部使用中文描述，（如用“客户姓名”而非“custName”或“CUST_NAME”，用“客户编号”而非“客户ID”或“cust_id”）")
            else:
                attributes = [attr.strip() for attr in re.split(DATA_ATTRIBUTE_SPLIT_REGEX, data_attributes_str_cell) if
                              attr.strip()]
                if not (2 <= len(attributes) <= 15):
                    errors.append(
                        f"数据行 {data_row_num} (文件行 {file_row_num}): '数据属性' 数量为 {len(attributes)}，应在 2 到 15 个之间。属性列表: {attributes}")

                attributes_tuple = tuple(sorted(attributes))
                all_data_attributes_tuples.add(attributes_tuple)

                current_details = (data_group_cell, attributes_tuple)
                if process_cell:
                    if data_move_type_cell == 'E':
                        if process_cell in process_entry_details:
                            errors.append(
                                f"数据行 {data_row_num} (文件行 {file_row_num}): 功能过程 '{process_cell}' 检测到多个 'E' 入口。")
                        process_entry_details[process_cell] = current_details
                    elif data_move_type_cell in ('W', 'X'):
                        process_exit_details[process_cell] = current_details
                    elif data_move_type_cell == 'R':
                        if process_cell not in process_read_details:
                            process_read_details[process_cell] = []
                        process_read_details[process_cell].append(current_details)

        # 按功能过程分组行，用于后续跨行检查
        if process_cell:
            if process_cell not in process_rows:
                process_rows[process_cell] = []
            process_rows[process_cell].append(row)

    # --- 跨行校验 ---

    # 1. 检查每个功能过程内部是否有重复的子过程描述
    for process, rows_in_process in process_rows.items():
        seen_sub_processes_in_block: Dict[str, int] = {} # {sub_process_desc: first_seen_data_row_num}
        for row in rows_in_process:
            sub_process_cell = row.get("子过程描述", "")
            data_row_num = row['_data_row_num']
            if sub_process_cell: # 只检查非空的子过程描述
                if sub_process_cell in seen_sub_processes_in_block:
                    first_seen_row = seen_sub_processes_in_block[sub_process_cell]
                    errors.append(
                        f"子过程描述重复错误：在功能过程 '{process}' 内部，行 {data_row_num} 的子过程描述 '{sub_process_cell}' "
                        f"与该功能过程内首次出现的行 {first_seen_row} 重复。")
                else:
                    seen_sub_processes_in_block[sub_process_cell] = data_row_num

    # 2. 检查重复的数据属性 (全局检查)
    seen_attributes = {}
    for i, row in enumerate(table_data):
        attributes_str = row["数据属性"]
        if attributes_str in seen_attributes:
            seen_row = seen_attributes[attributes_str]
            errors.append(
                f"数据属性重复：行 {row['_data_row_num']} 的数据属性 '{attributes_str}' "
                f"与行 {seen_row['_data_row_num']} 的数据属性 '{seen_row['数据属性']}' 完全重复，请更改行 {row['_data_row_num']} 的数据属性以消除重复")
        else:
            seen_attributes[attributes_str] = row

    # 3. 检查每个功能过程内部的数据移动序列
    for process, rows in process_rows.items(): # 使用已分组的 process_rows
        rows.sort(key=lambda r: r['_file_row_num']) # 确保按文件行号排序
        moves = [row["数据移动类型"] for row in rows]
        file_row_nums = [row['_file_row_num'] for row in rows]

        # 规则 8: 数据移动序列
        if not moves: continue
        if moves[0] != 'E':
            errors.append(
                f"功能过程 '{process}' (文件行 {file_row_nums[0]}) 的数据移动序列 '{''.join(moves)}' 未以 'E' 开头。")

        for i in range(len(moves) - 1):
            if moves[i] == 'X' and moves[i + 1] in ('W', 'R'):
                errors.append(
                    f"功能过程 '{process}' (文件行 {file_row_nums[i + 1]}) 存在不允许的 'X{moves[i + 1]}' 数据移动序列。禁止 X 后面再跟随任何数据移动类型")

        if len(moves) >= 3:
            for i in range(len(moves) - 2):
                if moves[i:i + 3] == ['E', 'R', 'W']:
                    errors.append(
                        f"功能过程 '{process}' (涉及文件行: {file_row_nums[i]} 到 {file_row_nums[i + 2]}) 包含不允许的 'ERW' 数据移动组合。应该拆成ERX组合，并修改对应的子过程描述"
                    )

    # 4. 检查功能过程是否不连续重复
    if table_data: # 只有在表格有数据时才执行
        process_blocks: List[Tuple[str, int, int]] = [] # (process_name, start_row_num, end_row_num)
        current_process = table_data[0].get("功能过程", "")
        start_row_num = table_data[0]['_data_row_num']

        for i in range(1, len(table_data)):
            row = table_data[i]
            process_cell = row.get("功能过程", "")
            data_row_num = row['_data_row_num']

            if process_cell != current_process:
                # 当前块结束
                if current_process: # 只添加非空的功能过程块
                    process_blocks.append((current_process, start_row_num, table_data[i-1]['_data_row_num']))
                # 开始新块
                current_process = process_cell
                start_row_num = data_row_num

        # 添加最后一个块
        if current_process: # 确保最后一个块的功能过程非空
             process_blocks.append((current_process, start_row_num, table_data[-1]['_data_row_num']))

        # 检查重复的功能过程块
        process_occurrences: Dict[str, List[Tuple[int, int]]] = {} # {process_name: [(start1, end1), (start2, end2), ...]}
        for name, start, end in process_blocks:
            # name 在这里已经保证非空
            if name not in process_occurrences:
                process_occurrences[name] = []
            process_occurrences[name].append((start, end))

        # 查找不连续的重复
        for name, occurrences in process_occurrences.items():
            if len(occurrences) > 1:
                occurrence_ranges = [f"行 {start}-{end}" for start, end in occurrences]
                errors.append(f"功能过程重复错误：功能过程 '{name}' 在表格中不连续地出现多次，分别在: {', '.join(occurrence_ranges)}。")


    # --- 返回结果 ---
    final_errors = sorted(list(set(errors)))
    return (not final_errors), "\n".join(final_errors)


def markdown_table_to_list(markdown_table_str):
    """
    将Markdown表格字符串转换为Python列表。
    如果输入字符串包含 ```markdown ... ``` 标记，会先提取其中的内容。

    参数：
    markdown_table_str (str): Markdown表格字符串，可以包含代码块标记。

    返回值：
    list of dict: 转换后的Python列表，如果无法解析则返回空列表。
    """
    # 预处理：移除可选的 ```markdown ... ``` 包围符
    match = re.search(r"^\s*```(?:markdown)?\s*\n?(.*?)\n?\s*```\s*$", markdown_table_str, re.DOTALL | re.IGNORECASE)
    if match:
        markdown_content = match.group(1).strip()
    else:
        markdown_content = markdown_table_str.strip()

    if not markdown_content:
        return []

    # 将Markdown转换为HTML
    # extensions = ['tables', 'nl2br']
    extensions = ['tables']  # 只使用表格扩展
    html = markdown.markdown(markdown_content, extensions=extensions)

    # 使用 BeautifulSoup 解析 HTML
    soup = BeautifulSoup(html, 'lxml')  # 或者使用 'html.parser'

    table = soup.find('table')
    if not table:
        # print("Debug: No table found in HTML") # 调试信息
        # print("HTML:", html)
        return []

    headers = []
    header_row = table.find('thead')
    if header_row:
        header_tags = header_row.find_all('th')
        # 提取表头文本
        headers = [th.get_text(strip=True) for th in header_tags]
        # print(f"Debug: Headers found: {headers}") # 调试信息
    # else:
    # print("Debug: No thead found") # 调试信息

    rows = []
    body = table.find('tbody')
    if body:
        data_rows = body.find_all('tr')
        # print(f"Debug: Found {len(data_rows)} data rows in tbody") # 调试信息
        for i, data_row in enumerate(data_rows):
            cells = data_row.find_all('td')
            # *** 关键改动：提取单元格的内部HTML内容 ***
            # 使用 decode_contents() 获取标签内部的完整HTML，然后去除首尾空格
            cell_data = [td.decode_contents().strip() for td in cells]
            # print(f"Debug: Row {i} cell data: {cell_data}") # 调试信息

            if headers and len(headers) == len(cell_data):
                rows.append(dict(zip(headers, cell_data)))
            elif not headers and cell_data:  # 处理没有表头的情况
                rows.append(cell_data)
            # else:
            # print(f"Debug: Row {i} column mismatch or no headers. Headers: {len(headers)}, Cells: {len(cell_data)}") # 调试信息

    # else:
    # print("Debug: No tbody found") # 调试信息

    return rows


def extract_table_from_text(text: str) -> str:
    """
    从包含Markdown表格的文本中提取第一个完整的表格。

    AI 大模型回答输出的内容除了表格有可能还包含其它字符描述，
    这个方法专门提取第一个出现的 Markdown 表格内容。

    参数:
    text (str): 可能包含Markdown表格的文本。

    返回值:
    str: 提取出的Markdown表格字符串，如果未找到表格则返回空字符串。
    """

    # 更精确的 Markdown 表格正则表达式:
    # - `(?:^|\n)`: 匹配字符串开头或换行符，确保表格在新行开始。
    # - `(\s*\|.*?\n`: 匹配并捕获第一组：
    #   - `\s*`: 可选的前导空格。
    #   - `\|`: 行首的管道符。
    #   - `.*?`: 非贪婪匹配任意字符（表头内容）。
    #   - `\n`: 表头行末尾的换行符。
    # - `\s*\|[-:|\s]+\|.*?\n`: 匹配分隔行：
    #   - `\s*`: 可选的前导空格。
    #   - `\|`: 行首的管道符。
    #   - `[-:|\s]+`: 匹配一个或多个连字符、冒号、管道符或空格（分隔符内容）。
    #   - `\|`: 分隔符内容后的管道符。
    #   - `.*?`: 匹配分隔行末尾管道符后的任何内容（允许不规则分隔行）。
    #   - `\n`: 分隔行末尾的换行符。
    # - `(?:\s*\|.*?\n?)+`: 匹配一个或多个数据行（非捕获组）：
    #   - `\s*`: 可选的前导空格。
    #   - `\|`: 行首的管道符。
    #   - `.*?`: 非贪婪匹配任意字符（数据行内容）。
    #   - `\n?`: 行末尾可选的换行符（允许最后一行没有换行符）。
    # - `)`: 结束第一个捕获组。
    # 使用 re.MULTILINE 标志 (^ $ 匹配行的开始结束), 但这里用 (?:^|\n) 效果类似且更易读
    # 使用 re.DOTALL (s 标志) 使 . 匹配换行符，但这里我们按行匹配，不需要

    # 稍微调整后的模式，专注于块匹配，不显式要求每行末尾都有 | (虽然标准MD要求)
    # 它查找一个以 | 开头，包含分隔符行，后面跟着更多以 | 开头的行的块
    table_pattern = r"((?:^|\n)\s*\|.*?\|\s*\n\s*\|[-:|\s]+\|.*?\n(?:\s*\|.*?$(?:\n|\Z))+)"
    # - `(?:^|\n)`: 表格块之前是行首或换行符
    # - `(`: 开始捕获组 1 (整个表格)
    # - `\s*\|.*?\|\s*\n`: 表头行 (允许前后空格，必须以 | 包裹)
    # - `\s*\|[-:|\s]+\|.*?\n`: 分隔行 (允许前导空格，必须有 |...符合分隔符规则...|，允许后面有内容直到换行)
    # - `(?: ... )+`: 匹配一个或多个数据行
    #   - `\s*\|.*?$`: 匹配以 | 开头的数据行内容直到行尾 (允许前导空格)
    #   - `(?:\n|\Z)`: 匹配行尾的换行符 或 整个字符串的末尾 (\Z)
    # - `)`: 结束捕获组 1

    match = re.search(table_pattern, text, re.MULTILINE)  # 使用 MULTILINE 使 ^ $ 匹配行首行尾

    if match:
        # 提取匹配到的整个表格块 (group(1)) 并去除首尾可能存在的空白/换行符
        table_text = match.group(1).strip()
        return table_text
    else:
        return ''


def extract_json_from_text(text: str) -> str:
    """
    从AI回复内容中提取最后一个有效的JSON字符串。
    处理可能包含多个JSON块和注释的情况，只返回最后一个完整的JSON。
    
    Args:
        text: 包含JSON的文本内容
        
    Returns:
        最后一个有效的JSON字符串
        
    Raises:
        ValueError: 如果找不到有效的JSON
    """
    # 匹配所有可能的JSON块
    json_matches = []
    stack = []
    start_index = -1

    # 手动查找JSON块
    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                start_index = i
            stack.append(char)
        elif char == '}':
            if stack:
                stack.pop()
                if not stack and start_index != -1:
                    json_matches.append((start_index, i + 1))
                    start_index = -1

    if not json_matches:
        raise ValueError("文本中未找到JSON内容")

    # 从后向前查找第一个有效的JSON
    for start, end in reversed(json_matches):
        json_str = text[start:end]
        try:
            # 验证JSON是否有效
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            continue

    raise ValueError("文本中未找到有效的JSON内容")


def validate_all_done(current_answer_content):
    # 对于输出行数较多的一次性无法全部回复，需要多轮对话，这里校验是否最后一轮对话
    if re.search(r'continue', current_answer_content, re.IGNORECASE):
        return 1  # 后续还有内容
    elif re.search(r'ALL_DONE', current_answer_content, re.IGNORECASE):
        return 0  # 最后一轮回复
    else:
        return 0  # 最后一轮回复


def validate_trigger_event_json(json_str: str, total_rows: int) -> Tuple[bool, str]:
    """
    根据最新的COSMIC AI提示词规则，校验AI生成的JSON输出。

    Args:
        json_str: AI生成的JSON字符串。
        total_rows: 用户期望的总行数（用于功能过程总数估算）。

    Returns:
        tuple: (bool, str)
            - bool: 校验是否通过 (True/False)。
            - str: 错误/警告信息列表（换行符分隔），如果通过则为空字符串。
    """
    # 功能用户需求(FUR)规则
    FUR_MAX_LEN = 40
    FUR_MIN_TE = 1
    FUR_MAX_TE = 8

    # 触发事件(TE)规则
    TE_MIN_FP = 1
    TE_MAX_FP = 25

    # 功能过程(FP)规则

    # 合并用于检查
    ALL_FORBIDDEN_KEYWORDS = set(FORBIDDEN_KEYWORDS_ERROR)

    # 功能过程(FP)总数估算相关 (基于平均子过程数 2.5 )
    FP_TOTAL_COUNT_FACTOR_MIN = 3.0
    FP_TOTAL_COUNT_FACTOR_MAX = 2.0

    errors: List[str] = []
    all_functional_processes: List[str] = []  # 用于全局功能过程重名检查

    # --- 1. JSON 解析 ---
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        errors.append(f"致命错误: JSON解析失败 - {e}")
        return False, "\n".join(errors)  # 致命错误，停止校验

    # --- 2. 基础结构校验 ---
    if not isinstance(data, dict) or "functional_user_requirements" not in data:
        errors.append("致命错误: JSON顶层结构错误，必须是包含 'functional_user_requirements' 键的字典。")
        return False, "\n".join(errors)  # 致命错误

    if not isinstance(data.get("functional_user_requirements"), list):
        errors.append("致命错误: 'functional_user_requirements' 的值必须是一个列表。")
        return False, "\n".join(errors)  # 致命错误

    if not data.get("functional_user_requirements"):
        errors.append("结构校验错误: 'functional_user_requirements' 列表不能为空，至少需要一个功能用户需求。")
        # 不直接返回，继续检查其他可能的问题

    # --- 3. 详细元素校验 ---
    total_process_count = 0
    total_event_count = 0

    for i, fur in enumerate(data.get("functional_user_requirements", [])):
        fur_path = f"functional_user_requirements[{i}]"  # 用于错误定位

        # 3.1 功能用户需求 (FUR) 校验
        if not isinstance(fur, dict):
            errors.append(f"结构校验错误: {fur_path} 必须是一个字典。")
            continue  # 跳过此FUR的后续检查

        req = fur.get("requirement")
        events = fur.get("trigger_events")

        if not isinstance(req, str) or not req:
            errors.append(f"内容校验错误: {fur_path}['requirement'] 必须是有效的非空字符串。")
        elif len(req) > FUR_MAX_LEN:
            errors.append(f"内容校验错误: {fur_path}['requirement'] '{req}' 长度超过 {FUR_MAX_LEN} 个字符，请概括总结。")

        if not isinstance(events, list):
            errors.append(f"结构校验错误: {fur_path}['trigger_events'] 必须是一个列表。")
            continue  # 没有有效的事件列表，无法继续检查此FUR下的事件

        # 规则2：FUR下的TE数量校验
        if not (FUR_MIN_TE <= len(events) <= FUR_MAX_TE):
            errors.append(
                f"数量校验错误: {fur_path} 包含 {len(events)} 个触发事件，应在 {FUR_MIN_TE} 到 {FUR_MAX_TE} 个之间。")

        if not events:
            errors.append(f"结构校验错误: {fur_path}['trigger_events'] 列表不能为空，至少需要一个触发事件。")

        # 3.2 触发事件 (TE) 和 功能过程 (FP) 校验
        for j, event in enumerate(events):
            event_path = f"{fur_path}['trigger_events'][{j}]"
            total_event_count += 1

            if not isinstance(event, dict):
                errors.append(f"结构校验错误: {event_path} 必须是一个字典。")
                continue  # 跳过此TE的后续检查

            event_desc = event.get("event")
            processes = event.get("functional_processes")

            if not isinstance(event_desc, str) or not event_desc:
                errors.append(f"内容校验错误: {event_path}['event'] 必须是有效的非空字符串。")
                # 可以在此添加对TE命名格式的宽松检查 (可选)
                # 例如：if not re.search(r"[动词名词]", event_desc): errors.append(...)

            if not isinstance(processes, list):
                errors.append(f"结构校验错误: {event_path}['functional_processes'] 必须是一个列表。")
                continue  # 没有有效的功能过程列表

            #规则3：TE下的FP数量校验
            if not (TE_MIN_FP <= len(processes) <= TE_MAX_FP):
                errors.append(
                    f"数量校验错误: {event_path} (触发事件 '{event_desc}') 包含 {len(processes)} 个功能过程，应在 {TE_MIN_FP} 到 {TE_MAX_FP} 个之间 。请细化拆分触发事件！")

            if not processes:
                errors.append(f"结构校验错误: {event_path}['functional_processes'] 列表不能为空，至少需要一个功能过程。")

            # 3.3 功能过程 (FP) 详细校验
            for k, process in enumerate(processes):
                process_path = f"{event_path}['functional_processes'][{k}]"
                total_process_count += 1

                if not isinstance(process, str) or not process:
                    errors.append(f"内容校验错误: {process_path} 必须是有效的非空字符串。")
                    continue  # 跳过此无效过程的后续检查

                # 规则4 & 经验8：禁止的关键字检查
                found_forbidden = []
                for keyword in ALL_FORBIDDEN_KEYWORDS:
                    if keyword in process:
                        level = "错误" if keyword in FORBIDDEN_KEYWORDS_ERROR else "警告"
                        found_forbidden.append(
                            f"{level}: 功能过程 '{process}' ({process_path}) 包含禁用/不推荐关键字 '{keyword}'")
                if found_forbidden:
                    errors.extend(found_forbidden)

                # 规则4 & 经验5：功能过程唯一性检查
                if process in all_functional_processes:
                    errors.append(f"重复性校验错误: 功能过程 '{process}' ({process_path}) 与之前的功能过程重复。")
                else:
                    all_functional_processes.append(process)

    # --- 4. 总体数量校验 ---
    if total_event_count == 0 and not any("functional_user_requirements" in e for e in errors):  # 只有在FUR列表本身有效时才报此错
        errors.append("数量校验错误：整个JSON至少需要包含一个触发事件。")

    if total_process_count == 0 and not any("functional_processes" in e for e in errors):  # 只有在TE列表本身有效时才报此错
        errors.append("数量校验错误：整个JSON至少需要包含一个功能过程。")

    # 规则5：功能过程总数估算校验 (基于总行数)
    # 使用浮点数除法以获得更精确的边界
    lower_bound = int(total_rows / FP_TOTAL_COUNT_FACTOR_MIN)  # 对应每个FP最多子过程数
    upper_bound = int(total_rows / FP_TOTAL_COUNT_FACTOR_MAX)  # 对应每个FP最少子过程数
    # 确保下限不大于上限
    if lower_bound > upper_bound:
        lower_bound, upper_bound = upper_bound, lower_bound  # Swap if needed
    # 提供一个最可能的值，基于提示词示例的 100/2.5
    most_likely_count = round(total_rows / 2.5)

    if total_process_count > 0 and not (lower_bound <= total_process_count <= upper_bound):
        base_warning = f"数量校验警告: 当前生成的功能过程总数 ({total_process_count}) 与预期行数 ({total_rows}) 推算的功能过程数量范围 [{lower_bound}-{upper_bound}]不符。"
        if total_process_count > upper_bound:
            suggestion = "需要减少功能过程数量。"
        elif total_process_count < lower_bound:
            suggestion = "需要增加功能过程数量。"
        else: # This case should technically not be reached due to the outer 'if' condition
            suggestion = "请检查拆分粒度。"
        errors.append(f"{base_warning} {suggestion}")

    # --- 5. 返回结果 ---
    return not errors, "\n".join(errors)



def validate_requirement_analysis_json(json_str: str) -> Tuple[bool, str]:
    # --- 配置常量 ---

    # 功能用户分类规则中允许的参与者类型
    ALLOWED_PARTICIPANT_TYPES: Set[str] = {
        "操作员", "个人网台", "订单中心", "账管中心", "产商品中心",
        "后台进程", "基础中心", "小屏", "短厅"
    }

    # 功能过程名称中绝对禁止的词语
    FORBIDDEN_PROCESS_WORDS: Set[str] = {
        "加载", "解析", "初始化", "点击按钮", "页面", "渲染", "切换", "计算",
        "重置", "分页", "排序", "适配", "开发", "部署", "迁移", "安装",
        "存储", "缓存", "校验", "验证", "是否", "判断", "组装报文", "构建报文"
        # 注意: 保存/输入/读取/输出/存储/缓存 在特定上下文可能允许，但提示词已列为避免，
        # 这里按最严格的“绝对禁止”列表来校验，如果需要放宽，可以从这里移除。
    }

    # 功能过程名称中禁止的模式 (例如，日志记录)
    FORBIDDEN_PROCESS_PATTERNS: List[str] = [
        r"日志记录",
        r"记录.*日志"
    ]

    # 功能用户需求描述字数限制
    FUR_DESC_MIN_LEN: int = 10
    FUR_DESC_MAX_LEN: int = 40

    # 触发事件描述字数限制
    EVENT_DESC_MIN_LEN: int = 10
    EVENT_DESC_MAX_LEN: int = 40

    # 功能过程名称字数限制
    PROCESS_NAME_MIN_LEN: int = 30
    PROCESS_NAME_MAX_LEN: int = 40

    # 工作量估算范围 (当无法从文本提取时)
    WORKLOAD_ESTIMATE_MIN: int = 10
    WORKLOAD_ESTIMATE_MAX: int = 300

    # FUR 拆分工作量基准和浮动比例
    FUR_WORKLOAD_TARGET: int = 30
    FUR_WORKLOAD_FLUCTUATION: float = 0.10  # +/- 10%

    # 功能过程总数与工作量比例基准和浮动比例
    PROCESS_COUNT_WORKLOAD_RATIO: float = 1 / 3
    PROCESS_COUNT_FLUCTUATION: float = 0.05  # +/- 5%

    """
    校验AI生成的COSMIC需求分析JSON字符串是否符合预定义的规则。

    Args:
        json_str: 包含需求分析结果的JSON字符串。

    Returns:
        一个元组，第一个元素是布尔值，表示校验是否通过 (True表示通过, False表示有错误)。
        第二个元素是字符串，如果校验不通过，则包含所有错误信息的描述，用换行符分隔；
        如果校验通过，则为空字符串。
    """
    errors: List[str] = []
    data: Dict[str, Any] = {}
    seen_fur_descs: Set[str] = set()
    seen_event_descs: Set[str] = set()
    seen_process_names: Set[str] = set()
    total_process_count: int = 0

    # 1. 校验JSON基本格式
    try:
        data = json.loads(json_str)
        if not isinstance(data, dict) or "requirementAnalysis" not in data:
            errors.append("AI你好，JSON顶层结构似乎不正确，请确保包含 'requirementAnalysis' 键。")
            return False, "\n".join(errors)
        analysis_data = data["requirementAnalysis"]
        if not isinstance(analysis_data, dict):
             errors.append("AI你好，'requirementAnalysis' 的值应该是JSON对象格式。")
             return False, "\n".join(errors)

    except json.JSONDecodeError as e:
        errors.append(f"AI你好，提供的回复不是有效的JSON格式，解析时出错了：{e}。请检查括号、逗号、引号是否匹配。")
        return False, "\n".join(errors)

    # 2. 校验顶层字段存在性和类型
    required_keys = ["customerRequirement", "customerRequirementWorkload", "functionalUserRequirements"]
    for key in required_keys:
        if key not in analysis_data:
            errors.append(f"AI你好，'requirementAnalysis' 对象中缺少必要的字段 '{key}'。请补充。")
        elif key == "customerRequirement" and not isinstance(analysis_data.get(key), str):
             errors.append(f"AI你好，字段 '{key}' 的值应该是字符串类型。")
        elif key == "customerRequirementWorkload" and not isinstance(analysis_data.get(key), int):
             errors.append(f"AI你好，字段 '{key}' 的值应该是整数类型。")
        elif key == "functionalUserRequirements" and not isinstance(analysis_data.get(key), list):
             errors.append(f"AI你好，字段 '{key}' 的值应该是列表（数组）类型。")

    # 如果基础结构错误，提前返回
    if errors:
        return False, "\n".join(errors)

    # 3. 校验 customerRequirementWorkload 范围 (仅当它是估算值时，但我们无法区分，所以统一校验范围)
    #   更新：根据提示词，如果能提取到明确值，可能超出10-300。因此只校验类型（已在上面完成）。
    #   如果需要强制估算值也在10-300内，可以取消下面注释，但这可能与提取逻辑冲突。
    # workload = analysis_data.get("customerRequirementWorkload", 0)
    # if not (WORKLOAD_ESTIMATE_MIN <= workload <= WORKLOAD_ESTIMATE_MAX):
    #     errors.append(f"AI你好，'customerRequirementWorkload' 的值 ({workload}) 超出了建议的估算范围 ({WORKLOAD_ESTIMATE_MIN}-{WORKLOAD_ESTIMATE_MAX})。如果这是估算值，请调整；如果是提取值，请忽略此条。")

    workload = analysis_data.get("customerRequirementWorkload", 0) # 后续计算需要

    # 4. 校验 functionalUserRequirements (FURs)
    furs = analysis_data.get("functionalUserRequirements", [])
    num_furs = len(furs)

    # 4.1 校验FUR数量与工作量的关系
    if workload > 0: # 避免除以零
        target_furs = workload / FUR_WORKLOAD_TARGET
        min_expected_furs = round(target_furs * (1 - FUR_WORKLOAD_FLUCTUATION))
        max_expected_furs = round(target_furs * (1 + FUR_WORKLOAD_FLUCTUATION))
        if not (min_expected_furs <= num_furs <= max_expected_furs):
             errors.append(f"AI你好，根据工作量 {workload}，预期的功能用户需求(FUR)数量应在 {min_expected_furs}-{max_expected_furs} 个左右 (每个FUR约{FUR_WORKLOAD_TARGET}工作量)。当前数量为 {num_furs} 个，请检查FUR的拆分是否合理。")

    for i, fur in enumerate(furs):
        if not isinstance(fur, dict):
            errors.append(f"AI你好，功能用户需求列表中的第 {i+1} 项不是有效的JSON对象格式。")
            continue # 跳过对此项的后续检查

        # 4.2 校验FUR描述 (`description`)
        fur_desc = fur.get("description")
        fur_ref = f"功能用户需求列表第 {i+1} 项"
        if not fur_desc or not isinstance(fur_desc, str):

            errors.append(f"AI你好，{fur_ref} 缺少 'description' 字段或其值不是字符串。")
        else:
            # 校验字数
            if not (FUR_DESC_MIN_LEN <= len(fur_desc) <= FUR_DESC_MAX_LEN):
                errors.append(f"AI你好，{fur_ref} 的描述 '{fur_desc}' 长度为 {len(fur_desc)} 字，不符合 {FUR_DESC_MIN_LEN}-{FUR_DESC_MAX_LEN} 字的要求。请调整描述长度。")
            # 校验唯一性
            if fur_desc in seen_fur_descs:
                errors.append(f"AI你好，{fur_ref} 的描述 '{fur_desc}' 与之前的某个功能用户需求描述重复了。请确保每个描述都是唯一的。")
            seen_fur_descs.add(fur_desc)

        # 4.3 校验 triggeringEvents 列表
        triggering_events = fur.get("triggeringEvents")
        if not isinstance(triggering_events, list):
             errors.append(f"AI你好，{fur_ref} 缺少 'triggeringEvents' 字段或其值不是列表。")
             continue # 跳过事件检查

        for j, event in enumerate(triggering_events):
            if not isinstance(event, dict):
                errors.append(f"AI你好，{fur_ref} 的触发事件列表中的第 {j+1} 项不是有效的JSON对象格式。")
                continue # 跳过对此事件的后续检查

            event_ref = f"{fur_ref} 的触发事件列表第 {j+1} 项"

            # 4.3.1 校验触发事件描述 (`eventDescription`)
            event_desc = event.get("eventDescription")
            if not event_desc or not isinstance(event_desc, str):
                errors.append(f"AI你好，{event_ref} 缺少 'eventDescription' 字段或其值不是字符串。")
            else:
                # 校验字数
                if not (EVENT_DESC_MIN_LEN <= len(event_desc) <= EVENT_DESC_MAX_LEN):
                    errors.append(f"AI你好，{event_ref} 的描述 '{event_desc}' 长度为 {len(event_desc)} 字，不符合 {EVENT_DESC_MIN_LEN}-{EVENT_DESC_MAX_LEN} 字的要求。请调整描述长度。")
                # 校验唯一性 (与其他事件描述)
                if event_desc in seen_event_descs:
                     errors.append(f"AI你好，{event_ref} 的描述 '{event_desc}' 与之前的某个触发事件描述重复了。请确保每个触发事件描述都是唯一的。")
                seen_event_descs.add(event_desc)
                # 校验唯一性 (与FUR描述)
                if event_desc in seen_fur_descs:
                     errors.append(f"AI你好，{event_ref} 的描述 '{event_desc}' 与某个功能用户需求的描述相同了。请修改触发事件描述，使其与功能用户需求描述不同。")
                # 提示词要求了命名格式，但自动化校验困难，这里省略对格式的严格检查

            # 4.3.2 校验参与者 (`participants`)
            participants_str = event.get("participants")
            if not participants_str or not isinstance(participants_str, str):
                errors.append(f"AI你好，{event_ref} 缺少 'participants' 字段或其值不是字符串。")
            else:
                lines = participants_str.strip().split('\n')
                initiator_type = ""
                receiver_type = ""
                format_ok = False
                if len(lines) == 2:
                    line1 = lines[0].strip()
                    line2 = lines[1].strip()
                    if line1.startswith("发起者:") and line2.startswith("接收者："): # 注意冒号是中文还是英文
                         initiator_type = line1.replace("发起者:", "").strip()
                         receiver_type = line2.replace("接收者：", "").strip()
                         format_ok = True
                    elif line1.startswith("发起者：") and line2.startswith("接收者："): # 兼容中文冒号
                         initiator_type = line1.replace("发起者：", "").strip()
                         receiver_type = line2.replace("接收者：", "").strip()
                         format_ok = True

                if not format_ok:
                    errors.append(f"AI你好，{event_ref} 的 'participants' 字段 ('{participants_str}') 格式不正确。请严格按照 '发起者: [类型]\\n接收者：[类型]' 的格式书写，注意换行。")
                else:
                    # 校验发起者类型
                    if initiator_type not in ALLOWED_PARTICIPANT_TYPES:
                        errors.append(f"AI你好，{event_ref} 的 'participants' 中的发起者类型 '{initiator_type}' 不在允许的类型列表中 ({', '.join(ALLOWED_PARTICIPANT_TYPES)})。请修正。")
                    # 校验接收者类型
                    if receiver_type not in ALLOWED_PARTICIPANT_TYPES:
                         errors.append(f"AI你好，{event_ref} 的 'participants' 中的接收者类型 '{receiver_type}' 不在允许的类型列表中 ({', '.join(ALLOWED_PARTICIPANT_TYPES)})。请修正。")

            # 4.3.3 校验 functionalProcesses 列表
            functional_processes = event.get("functionalProcesses")
            if not isinstance(functional_processes, list):
                errors.append(f"AI你好，{event_ref} 缺少 'functionalProcesses' 字段或其值不是列表。")
                continue # 跳过过程检查

            total_process_count += len(functional_processes) # 累加功能过程总数

            for k, process in enumerate(functional_processes):
                 if not isinstance(process, dict):
                     errors.append(f"AI你好，{event_ref} 的功能过程列表中的第 {k+1} 项不是有效的JSON对象格式。")
                     continue # 跳过对此过程的后续检查

                 process_ref = f"{event_ref} 的功能过程列表第 {k+1} 项"

                 # 校验功能过程名称 (`processName`)
                 process_name = process.get("processName")
                 if not process_name or not isinstance(process_name, str):
                     errors.append(f"AI你好，{process_ref} 缺少 'processName' 字段或其值不是字符串。")
                 else:
                     # 校验字数
                     if not (PROCESS_NAME_MIN_LEN <= len(process_name) <= PROCESS_NAME_MAX_LEN):
                         errors.append(f"AI你好，{process_ref} 的名称 '{process_name}' 长度为 {len(process_name)} 字，不符合 {PROCESS_NAME_MIN_LEN}-{PROCESS_NAME_MAX_LEN} 字的要求。请调整名称，使其更丰富或简洁。")
                     # 校验唯一性
                     if process_name in seen_process_names:
                         errors.append(f"AI你好，{process_ref} 的名称 '{process_name}' 与之前的某个功能过程名称重复了。请确保每个功能过程名称都是唯一的，并考虑是否需要合并相似的过程。")
                     seen_process_names.add(process_name)
                     # 校验禁用词
                     found_forbidden = []
                     for word in FORBIDDEN_PROCESS_WORDS:
                         if word in process_name:
                             found_forbidden.append(word)
                     if found_forbidden:
                         errors.append(f"AI你好，{process_ref} 的名称 '{process_name}' 中包含了禁用词: '{', '.join(found_forbidden)}'。请修改名称，避免使用这些词语。")
                     # 校验禁用模式 (日志)
                     for pattern in FORBIDDEN_PROCESS_PATTERNS:
                         if re.search(pattern, process_name):
                             errors.append(f"AI你好，{process_ref} 的名称 '{process_name}' 似乎与日志记录有关，这通常不应作为独立的功能过程。请检查是否应移除或合并。")
                             break # 找到一个匹配就够了

    # 5. 校验功能过程总数与工作量的关系
    if workload > 0:
        target_processes = workload * PROCESS_COUNT_WORKLOAD_RATIO
        min_expected_processes = round(target_processes * (1 - PROCESS_COUNT_FLUCTUATION))
        max_expected_processes = round(target_processes * (1 + PROCESS_COUNT_FLUCTUATION))
        if not (min_expected_processes <= total_process_count <= max_expected_processes):
            errors.append(f"AI你好，根据工作量 {workload}，预期的功能过程总数量应在 {min_expected_processes}-{max_expected_processes} 个左右 (约为工作量的1/3)。当前总共识别出 {total_process_count} 个功能过程。请检查功能过程的拆分和合并是否合理，以符合总量要求。")

    # 返回结果
    return not errors, "\n".join(errors)