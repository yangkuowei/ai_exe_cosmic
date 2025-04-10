import re
import json

import markdown
from typing import List, Dict, Tuple, Set, Optional, Any, Union
from bs4 import BeautifulSoup

# 校验、文本内容提取相关
import re
from typing import List, Dict, Tuple, Set
from typing import Tuple
# 假设 markdown_table_to_list 函数已经定义

def validate_cosmic_table(markdown_table_str: str, request_name: str) -> Tuple[bool, str]:
    """
    校验COSMIC功能点度量表格。
    此版本校验Markdown表格内部的结构和内容是否符合COSMIC规则。

    参数：
    markdown_table_str (str): Markdown格式的表格字符串。
    request_name (str): 客户需求名称 (用于校验表格第一列)。

    返回值：
    tuple: (bool, str)，第一个元素表示校验是否通过，
           第二个元素是错误信息字符串（如果校验不通过, 多个错误用换行符分隔）。
    """

    # --- 常量定义 ---
    EXPECTED_HEADERS = ["客户需求", "功能用户", "功能用户需求", "触发事件", "功能过程",
                        "子过程描述", "数据移动类型", "数据组", "数据属性", "复用度", "CFP", "ΣCFP"]

    FORBIDDEN_KEYWORDS_PROCESS = {
        '加载', '解析', '初始化', '点击按钮', '页面', '渲染', '保存', '输入', '读取', '获取', '输出', '切换', '计算',
        '重置', '分页', '排序', '适配', '开发', '部署', '迁移', '安装', '存储', '缓存', '校验', '验证', '是否', '判断',
        '异常', '维护', '日志', '组件', '加载', '解析', '初始化', '点击按钮', '页面', '渲染', '保存', '输入', '读取',
        '获取', '输出', '切换', '计算', '重置', '分页', '排序', '适配', '开发', '部署', '迁移', '安装', '存储', '缓存',
        '校验', '验证', '是否', '判断', '组件', '检查', '组装报文', '构建报文', '日志保存', '写日志', '配置', '标记',
        '策略', '调用XX接口'
    }

    FORBIDDEN_KEYWORDS_SUBPROCESS = FORBIDDEN_KEYWORDS_PROCESS

    VALID_DATA_MOVE_TYPES = {"E", "X", "R", "W"}
    FUNCTIONAL_USER_REGEX = r"^发起者:\s*.*?\s*接收者：\s*.*$"
    DATA_ATTRIBUTE_REGEX = r"^[\u4e00-\u9fa5\s,，]+$"
    DATA_ATTRIBUTE_SPLIT_REGEX = r"[,，]\s*"

    # --- 主校验逻辑 ---
    errors: List[str] = []
    table_data: List[Dict[str, str]] = [] # 初始化为空列表

    # 1. 调用外部函数解析 Markdown 表格
    try:
        # 假设 markdown_table_to_list 存在于当前作用域或已导入
        # 并且在解析失败时会抛出异常
        table_data = markdown_table_to_list(markdown_table_str)
        # 可以在这里添加对返回类型的基本检查，如果需要的话
        if not isinstance(table_data, list):
             raise TypeError("markdown_table_to_list 未返回列表")
        if table_data and not isinstance(table_data[0], dict):
             raise TypeError("markdown_table_to_list 返回的列表元素不是字典")
        # 可以在这里检查表头是否与预期一致，如果解析函数不保证的话
        if table_data:
             first_row_keys = list(table_data[0].keys()) # 假设解析函数保留了原始顺序
             if first_row_keys != EXPECTED_HEADERS:
                 # 注意：如果 markdown_table_to_list 不保证列顺序，这个检查可能不可靠
                 # 或者，如果 markdown_table_to_list 返回的是无序字典，需要检查键集合是否相等
                 if set(first_row_keys) != set(EXPECTED_HEADERS):
                      return False, f"Markdown表格解析错误：表头不匹配。\n预期: {EXPECTED_HEADERS}\n实际: {first_row_keys}"
                 else:
                      # 如果只是顺序不同，可以接受或重新排序，但这里按严格匹配处理
                      return False, f"Markdown表格解析错误：表头顺序不匹配。\n预期: {EXPECTED_HEADERS}\n实际: {first_row_keys}"


    except Exception as e:
        # 捕获解析过程中可能出现的任何异常
        return False, f"Markdown表格解析失败: {e}"

    # 检查解析结果是否为空（例如，只有表头的情况）
    if not table_data:
        # 根据需求决定空表是否为错误
        # return False, "表格内容不能为空"
        pass # 当前允许空表，后续检查会跳过

    # --- 初始化检查所需的数据结构 ---
    process_rows: Dict[str, List[Dict[str, Any]]] = {}
    all_data_attributes_tuples: Set[Tuple[str, ...]] = set()
    process_entry_details: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
    process_exit_details: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
    process_read_details: Dict[str, List[Tuple[str, Tuple[str, ...]]]] = {}


    # --- 逐行基础校验 ---
    # 假设 markdown_table_to_list 返回的列表不包含表头行
    # 行号需要根据 markdown_table_str 的原始行数计算，或者简化为基于数据的行号
    # 为了简化，这里的行号将是基于 table_data 的索引 + 1 （数据区的行号）
    # 如果需要精确的文件行号，需要在解析函数或这里做额外处理
    for row_index, row in enumerate(table_data):
        data_row_num = row_index + 1 # 数据区的行号 (从1开始)
        # 如果需要文件行号，大约是 data_row_num + 2 (假设表头和分隔行各占1行)
        file_row_num = data_row_num + 2

        # 添加行号信息到row字典中，方便后续错误报告
        row['_data_row_num'] = data_row_num
        row['_file_row_num'] = file_row_num

        # 从行数据中提取字段 (使用 .get() 增加健壮性，以防列缺失)
        req_name_cell = row.get("客户需求", "")
        func_user_cell = row.get("功能用户", "")
        func_req_cell = row.get("功能用户需求", "") # 可能为空
        trigger_event_cell = row.get("触发事件", "")
        process_cell = row.get("功能过程", "")
        sub_process_cell = row.get("子过程描述", "")
        data_move_type_cell = row.get("数据移动类型", "")
        data_group_cell = row.get("数据组", "")
        data_attributes_str_cell = row.get("数据属性", "")
        reuse_cell = row.get("复用度", "")
        cfp_cell = row.get("CFP", "")
        sum_cfp_cell = row.get("ΣCFP", "") # 确认是 Sigma CFP

        # --- 执行单行校验 ---

        # 规则 3: 客户需求
        if req_name_cell != request_name:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '客户需求' ({req_name_cell}) 与指定的需求名称 ({request_name}) 不匹配。")

        # 规则 4 & 输入校验: 功能用户
        if not func_user_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '功能用户' 不能为空。")
        elif not re.match(FUNCTIONAL_USER_REGEX, func_user_cell):
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '功能用户' ({func_user_cell}) 格式错误，应为 '发起者: [系统] 接收者：[系统]'。")

        # 规则 6 & 输入校验: 触发事件
        if not trigger_event_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '触发事件' 不能为空。")

        # 规则 7: 功能过程
        if not process_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '功能过程' 不能为空。")
        else:
            for keyword in FORBIDDEN_KEYWORDS_PROCESS:
                if keyword in process_cell:
                    errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '功能过程' ({process_cell}) 包含禁用关键字 '{keyword}'。")

        # 规则 8: 子过程描述
        if not sub_process_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' 不能为空。")
        else:
            if sub_process_cell == process_cell:
                errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' ({sub_process_cell}) 不能与 '功能过程' 相同。")
            
            # 新增规则: 数据移动类型为E时，子过程描述不能以"提交"开头
            if data_move_type_cell == 'E' and sub_process_cell.startswith('提交'):
                errors.append(
                    f"数据行 {data_row_num} (文件行 {file_row_num}): '如果数据移动类型是E，子过程描述' ({sub_process_cell}) 不能以'提交'开头。"
                    "建议使用'输入'、'传入'、'接收'等词语开头。"
                )
            
            for keyword in FORBIDDEN_KEYWORDS_SUBPROCESS:
                if keyword == "调用XX接口" and "调用" in sub_process_cell and "接口" in sub_process_cell:
                     errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' ({sub_process_cell}) 包含禁用模式 '调用XX接口'。")
                elif keyword != "调用XX接口" and keyword in sub_process_cell:
                     errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '子过程描述' ({sub_process_cell}) 包含禁用关键字 '{keyword}'。")

        # 规则 9: 数据移动类型
        if data_move_type_cell not in VALID_DATA_MOVE_TYPES:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '数据移动类型' ({data_move_type_cell}) 无效，必须是 E, X, R, W 中的一个。")

        # 规则 10: 数据组
        if not data_group_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '数据组' 不能为空。")

        # 规则 11: 数据属性
        if not data_attributes_str_cell:
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '数据属性' 不能为空。")
        else:
            if not re.fullmatch(DATA_ATTRIBUTE_REGEX, data_attributes_str_cell):
                # 提取无效字符用于提示
                invalid_chars = "".join(sorted(list(set(re.sub(r'[\u4e00-\u9fa5\s,，]', '', data_attributes_str_cell)))))
                errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '数据属性' ({data_attributes_str_cell}) 包含非中文、逗号或空格的字符 (例如: '{invalid_chars}')。")
            else:
                attributes = [attr.strip() for attr in re.split(DATA_ATTRIBUTE_SPLIT_REGEX, data_attributes_str_cell) if attr.strip()]
                if not (3 <= len(attributes) <= 15):
                    errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '数据属性' 数量为 {len(attributes)}，应在 3 到 15 个之间。属性列表: {attributes}")

                attributes_tuple = tuple(sorted(attributes))
                if attributes_tuple in all_data_attributes_tuples:
                    # errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): 数据属性组合 '{data_attributes_str_cell}' 与其他行重复。") # 规则未强制唯一
                    pass
                else:
                    all_data_attributes_tuples.add(attributes_tuple)

                current_details = (data_group_cell, attributes_tuple)
                if data_move_type_cell == 'E':
                    if process_cell in process_entry_details:
                         errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): 功能过程 '{process_cell}' 检测到多个 'E' 入口。")
                    process_entry_details[process_cell] = current_details
                elif data_move_type_cell in ('W', 'X'):
                    process_exit_details[process_cell] = current_details # 保留最后一个W/X
                elif data_move_type_cell == 'R':
                    if process_cell not in process_read_details:
                        process_read_details[process_cell] = []
                    process_read_details[process_cell].append(current_details)

        # 规则 12: 固定字段
        if reuse_cell != "新增":
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): '复用度' ({reuse_cell}) 应为 '新增'。")
        if cfp_cell != "1":
            errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): 'CFP' ({cfp_cell}) 应为 '1'。")
        if sum_cfp_cell != "1":
             errors.append(f"数据行 {data_row_num} (文件行 {file_row_num}): 'ΣCFP' ({sum_cfp_cell}) 应为 '1'。")

        # --- 收集数据用于后续跨行校验 ---
        if process_cell: # 仅在功能过程非空时收集
            if process_cell not in process_rows:
                process_rows[process_cell] = []
            process_rows[process_cell].append(row) # 存储包含行号信息的整行数据

    # --- 跨行校验 ---
    if not table_data and not errors: # 如果解析成功但表格是空的,且之前没有解析错误
        # errors.append("校验警告：表格内容为空。") # 根据需求决定是否报错
        pass # 允许空表

    for process, rows in process_rows.items():
        # 按文件行号排序，确保数据移动顺序正确
        rows.sort(key=lambda r: r['_file_row_num'])
        moves = [row["数据移动类型"] for row in rows]
        # 使用文件行号列表进行错误报告
        file_row_nums = [row['_file_row_num'] for row in rows]

        # 规则 8: 子过程数量
        if not (2 <= len(rows) <= 5):
            errors.append(f"功能过程 '{process}' (涉及文件行: {file_row_nums}) 包含 {len(rows)} 个子过程，应在 2 到 5 个之间。")

        # 规则 9: 数据移动序列
        if not moves: continue

        if moves[0] != 'E':
            errors.append(f"功能过程 '{process}' (文件行 {file_row_nums[0]}) 的数据移动序列 '{''.join(moves)}' 未以 'E' 开头。")
        if moves[-1] not in ('W', 'X'):
             errors.append(f"功能过程 '{process}' (文件行 {file_row_nums[-1]}) 的数据移动序列 '{''.join(moves)}' 未以 'W' 或 'X' 结尾。")

        for i in range(len(moves) - 1):
            if moves[i] == 'W' and moves[i+1] == 'X':
                errors.append(f"功能过程 '{process}' (文件行 {file_row_nums[i+1]}) 存在不允许的 'WX' 相邻数据移动。")
            if moves[i] == 'X' and moves[i+1] in ('W', 'R'):
                 errors.append(f"功能过程 '{process}' (文件行 {file_row_nums[i+1]}) 存在不允许的 'X{moves[i+1]}' 数据移动序列。")

        # 规则 10 & 11: 数据组和属性逻辑
        is_query = (len(moves) == 3 and moves == ['E', 'R', 'X'])

        # 新增规则: 检查ERW组合
        if len(moves) >= 3:
            for i in range(len(moves) - 2):
                if moves[i] == 'E' and moves[i+1] == 'R' and moves[i+2] == 'W':
                    errors.append(
                        f"功能过程 '{process}' (涉及文件行: {file_row_nums}) 包含不允许的 'ERW' 数据移动组合。"
                        "建议拆分成两个子过程描述: 第一个包含ER(输入-读取), 第二个包含EW(输入-写入)。"
                    )

        if process in process_entry_details and process in process_exit_details:
            entry_group, entry_attrs_tuple = process_entry_details[process]
            exit_group, exit_attrs_tuple = process_exit_details[process]
            if moves[-1] == 'W' and entry_attrs_tuple == exit_attrs_tuple:
                 # 定位到最后一个W行的文件行号
                 last_w_row_num = rows[-1]['_file_row_num']
                 errors.append(f"功能过程 '{process}' 的入口 'E' (数据组 '{entry_group}') 和最终出口 'W' (数据组 '{exit_group}', 文件行 {last_w_row_num}) 的数据属性完全相同，'W' 的属性应有所增加或不同。")

        if is_query and process in process_read_details and process in process_exit_details:
            # 确保ERX结构下只有一个R的数据被记录
            if len(process_read_details.get(process, [])) == 1:
                read_group, _ = process_read_details[process][0]
                exit_group, _ = process_exit_details[process]
                if read_group != exit_group:
                    # 对于ERX, R在第二行, X在第三行 (基于排序后的rows列表)
                    read_row_num = rows[1]['_file_row_num']
                    exit_row_num = rows[2]['_file_row_num']
                    errors.append(f"功能过程 '{process}' (查询类 ERX): 'R' (数据组 '{read_group}', 文件行 {read_row_num}) 和 'X' (数据组 '{exit_group}', 文件行 {exit_row_num}) 的数据组不同，通常应相同。")
            elif len(rows) == 3: # 如果确实是3行但R记录不唯一（理论上不应发生）
                 errors.append(f"功能过程 '{process}' (查询类 ERX, 文件行 {file_row_nums}) 内部逻辑错误：未能正确记录唯一的 'R' 详情。")
            # else: # 如果行数不是3，则前面的行数检查会报错，这里无需重复

    # --- 返回结果 ---
    final_errors = sorted(list(set(errors))) # 去重并排序
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
    extensions = ['tables'] # 只使用表格扩展
    html = markdown.markdown(markdown_content, extensions=extensions)

    # 使用 BeautifulSoup 解析 HTML
    soup = BeautifulSoup(html, 'lxml') # 或者使用 'html.parser'

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
            elif not headers and cell_data: # 处理没有表头的情况
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
                    json_matches.append((start_index, i+1))
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
    TE_MAX_FP = 6

    # 功能过程(FP)规则
    # 严格禁止的关键字
    FP_FORBIDDEN_KEYWORDS_ERROR = ["校验", "验证", "判断", "是否", "日志", "组装", "构建"]
    # 建议避免的关键字 (技术/实现细节, 来自规则4, 经验8)
    FP_FORBIDDEN_KEYWORDS_WARN = [
        "加载", "解析", "初始化", "点击", "按钮", "页面", "渲染",
        "保存",  # 除非指持久化存储 W
        "输入",  # 除非指数据入口 E
        "读取",  # 除非指数据读取 R
        "获取",  # 倾向于使用更具体的 R/E
        "输出",  # 除非指数据出口 X
        "切换", "计算", "重置", "分页", "排序", "适配",
        "开发", "部署", "迁移", "安装",
        "存储",  # 除非指持久化存储 W
        "缓存", "接口"  # 避免前后端重复计数 (经验5)
    ]
    # 合并用于检查
    ALL_FORBIDDEN_KEYWORDS = set(FP_FORBIDDEN_KEYWORDS_ERROR+FP_FORBIDDEN_KEYWORDS_WARN)

    # 功能过程(FP)总数估算相关 (基于平均子过程数 2.5 )
    FP_TOTAL_COUNT_FACTOR_MIN = 3.0
    FP_TOTAL_COUNT_FACTOR_MAX = 2.0


    errors: List[str] = []
    all_functional_processes: List[str] = [] # 用于全局功能过程重名检查


    # --- 1. JSON 解析 ---
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        errors.append(f"致命错误: JSON解析失败 - {e}")
        return False, "\n".join(errors) # 致命错误，停止校验

    # --- 2. 基础结构校验 ---
    if not isinstance(data, dict) or "functional_user_requirements" not in data:
        errors.append("致命错误: JSON顶层结构错误，必须是包含 'functional_user_requirements' 键的字典。")
        return False, "\n".join(errors) # 致命错误

    if not isinstance(data.get("functional_user_requirements"), list):
         errors.append("致命错误: 'functional_user_requirements' 的值必须是一个列表。")
         return False, "\n".join(errors) # 致命错误

    if not data.get("functional_user_requirements"):
        errors.append("结构校验错误: 'functional_user_requirements' 列表不能为空，至少需要一个功能用户需求。")
        # 不直接返回，继续检查其他可能的问题

    # --- 3. 详细元素校验 ---
    total_process_count = 0
    total_event_count = 0

    for i, fur in enumerate(data.get("functional_user_requirements", [])):
        fur_path = f"functional_user_requirements[{i}]" # 用于错误定位

        # 3.1 功能用户需求 (FUR) 校验
        if not isinstance(fur, dict):
            errors.append(f"结构校验错误: {fur_path} 必须是一个字典。")
            continue # 跳过此FUR的后续检查

        req = fur.get("requirement")
        events = fur.get("trigger_events")

        if not isinstance(req, str) or not req:
            errors.append(f"内容校验错误: {fur_path}['requirement'] 必须是有效的非空字符串。")
        elif len(req) > FUR_MAX_LEN:
            errors.append(f"内容校验错误: {fur_path}['requirement'] '{req}' 长度超过 {FUR_MAX_LEN} 个字符，请概括总结。")

        if not isinstance(events, list):
            errors.append(f"结构校验错误: {fur_path}['trigger_events'] 必须是一个列表。")
            continue # 没有有效的事件列表，无法继续检查此FUR下的事件

        # 规则2：FUR下的TE数量校验
        if not (FUR_MIN_TE <= len(events) <= FUR_MAX_TE):
             errors.append(f"数量校验错误: {fur_path} 包含 {len(events)} 个触发事件，应在 {FUR_MIN_TE} 到 {FUR_MAX_TE} 个之间。")

        if not events:
             errors.append(f"结构校验错误: {fur_path}['trigger_events'] 列表不能为空，至少需要一个触发事件。")


        # 3.2 触发事件 (TE) 和 功能过程 (FP) 校验
        for j, event in enumerate(events):
            event_path = f"{fur_path}['trigger_events'][{j}]"
            total_event_count += 1

            if not isinstance(event, dict):
                errors.append(f"结构校验错误: {event_path} 必须是一个字典。")
                continue # 跳过此TE的后续检查

            event_desc = event.get("event")
            processes = event.get("functional_processes")

            if not isinstance(event_desc, str) or not event_desc:
                errors.append(f"内容校验错误: {event_path}['event'] 必须是有效的非空字符串。")
                # 可以在此添加对TE命名格式的宽松检查 (可选)
                # 例如：if not re.search(r"[动词名词]", event_desc): errors.append(...)

            if not isinstance(processes, list):
                errors.append(f"结构校验错误: {event_path}['functional_processes'] 必须是一个列表。")
                continue # 没有有效的功能过程列表

            # 规则3：TE下的FP数量校验
            if not (TE_MIN_FP <= len(processes) <= TE_MAX_FP):
                 errors.append(f"数量校验错误: {event_path} (触发事件 '{event_desc}') 包含 {len(processes)} 个功能过程，应在 {TE_MIN_FP} 到 {TE_MAX_FP} 个之间 。")

            if not processes:
                 errors.append(f"结构校验错误: {event_path}['functional_processes'] 列表不能为空，至少需要一个功能过程。")


            # 3.3 功能过程 (FP) 详细校验
            for k, process in enumerate(processes):
                process_path = f"{event_path}['functional_processes'][{k}]"
                total_process_count += 1

                if not isinstance(process, str) or not process:
                    errors.append(f"内容校验错误: {process_path} 必须是有效的非空字符串。")
                    continue # 跳过此无效过程的后续检查

                # 规则4 & 经验8：禁止的关键字检查
                found_forbidden = []
                for keyword in ALL_FORBIDDEN_KEYWORDS:
                    if keyword in process:
                        level = "错误" if keyword in FP_FORBIDDEN_KEYWORDS_ERROR else "警告"
                        found_forbidden.append(f"{level}: 功能过程 '{process}' ({process_path}) 包含禁用/不推荐关键字 '{keyword}'")
                if found_forbidden:
                    errors.extend(found_forbidden)

                # 规则4 & 经验5：功能过程唯一性检查
                if process in all_functional_processes:
                    errors.append(f"重复性校验错误: 功能过程 '{process}' ({process_path}) 与之前的功能过程重复。")
                else:
                    all_functional_processes.append(process)

    # --- 4. 总体数量校验 ---
    if total_event_count == 0 and not any("functional_user_requirements" in e for e in errors): # 只有在FUR列表本身有效时才报此错
        errors.append("数量校验错误：整个JSON至少需要包含一个触发事件。")

    if total_process_count == 0 and not any("functional_processes" in e for e in errors): # 只有在TE列表本身有效时才报此错
         errors.append("数量校验错误：整个JSON至少需要包含一个功能过程。")


    # 规则5：功能过程总数估算校验 (基于总行数)
    # 使用浮点数除法以获得更精确的边界
    lower_bound = int(total_rows / FP_TOTAL_COUNT_FACTOR_MIN) # 对应每个FP最多子过程数
    upper_bound = int(total_rows / FP_TOTAL_COUNT_FACTOR_MAX) # 对应每个FP最少子过程数
    # 确保下限不大于上限
    if lower_bound > upper_bound:
        lower_bound, upper_bound = upper_bound, lower_bound # Swap if needed
    # 提供一个最可能的值，基于提示词示例的 100/2.5
    most_likely_count = round(total_rows / 2.5)

    if total_process_count > 0 and not (lower_bound <= total_process_count <= upper_bound):
         errors.append(f"数量校验警告: 当前生成的功能过程总数 ({total_process_count}) 与预期行数 ({total_rows}) 推算的功能过程数量范围 [{lower_bound}-{upper_bound}] (最可能约 {most_likely_count} 个) 不符。请检查拆分粒度。")


    # --- 5. 返回结果 ---
    return not errors, "\n".join(errors)
