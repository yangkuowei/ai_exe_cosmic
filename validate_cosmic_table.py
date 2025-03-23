import re
import json

import markdown
from typing import List, Dict, Tuple, Set


# 校验、文本内容提取相关
def validate_cosmic_table(markdown_table_str: str,request_name: str) -> Tuple[bool, str]:
    """
    校验COSMIC功能点度量表格。

    参数：
    markdown_table_str (str): Markdown格式的表格字符串。

    返回值：
    tuple: (bool, str)，第一个元素表示校验是否通过，
           第二个元素是错误信息字符串（如果校验不通过, 多个错误用换行符分隔）。
    """


    try:
        table = markdown_table_to_list(markdown_table_str)
    except Exception as e:
        return False, f"解析 Markdown 表格失败: {e}"

    errors: List[str] = []

    # 检查表头
    expected_headers = ["客户需求", "功能用户", "功能用户需求", "触发事件", "功能过程",
                        "子过程描述", "数据移动类型", "数据组", "数据属性", "复用度", "CFP", "ΣCFP"]
    if not table or list(table[0].keys()) != expected_headers:
        errors.append("表头错误，应包含以下列：" + ", ".join(expected_headers))
        return False, "\n".join(errors)  # 表头不对，直接返回

    # 用于跟踪每个功能过程的数据移动类型
    process_data_moves: Dict[str, List[str]] = {}
    # 用于检查数据属性的唯一性
    all_data_attributes: Set[Tuple] = set()
    # 用于检查触发事件和功能过程的对应关系, 存储每个触发事件对应的功能过程列表
    trigger_process_map: Dict[str, List[str]] = {}
    # 用于存储每个功能过程对应的子过程描述列表
    process_subprocesses_map: Dict[str, List[str]] = {}

    for row_num, row in enumerate(table, 1):  # row_num从1开始，方便错误信息提示
        request_name_str = row["客户需求"]
        trigger_event = row["触发事件"]
        process = row["功能过程"]
        sub_process = row["子过程描述"]
        data_move_type = row["数据移动类型"]
        data_group = row["数据组"]
        data_attributes_str = row["数据属性"]


        if request_name_str != request_name:
            errors.append(f" 客户需求 必须为[{request_name}]'。")

        # 1. 触发事件与功能过程的对应关系
        if trigger_event not in trigger_process_map:
            trigger_process_map[trigger_event] = [process]
        else:
            if process not in trigger_process_map[trigger_event]:
                trigger_process_map[trigger_event].append(process)

        # 2. 功能过程 - 避免开发术语，不包含“校验”
        if "校验" in process:
            errors.append(f"第{row_num}行：功能过程 '{process}' 禁止包含 '校验'，请替换表达词语。")

        # 3. 子过程描述规则
        if "校验" in sub_process:
            #errors.append(f"第{row_num}行：子过程描述 '{sub_process}' 禁止包含 '校验'，请替换表达词语。")
            pass
        if sub_process == process:
            errors.append(f"第{row_num}行：子过程描述 '{sub_process}' 不能与功能过程描述相同。")

        # 4. 数据移动类型规则
        if data_move_type not in ("E", "X", "R", "W"):
            errors.append(f"第{row_num}行：数据移动类型 '{data_move_type}' 无效。")

        # 跟踪每个功能过程的数据移动
        if process not in process_data_moves:
            process_data_moves[process] = []
        process_data_moves[process].append(data_move_type)

        # 5. 数据组 - 输入输出不能相同 (更严格的检查在所有行处理完后进行)

        # 6. 数据属性规则
        if not data_attributes_str:
            errors.append(f"第{row_num}行：数据属性不能为空。")
        else:
            data_attributes = [attr.strip() for attr in re.split(r"[、，,]", data_attributes_str)]  # 使用中文逗号和顿号分割

            if not (2 <= len(data_attributes) <= 15):
                errors.append(f"第{row_num}行：数据属性数量应在2到15个之间。")

            data_attributes_tuple = tuple(sorted(data_attributes))  # 排序后转为元组，用于比较
            if data_attributes_tuple in all_data_attributes:
                errors.append(f"第{row_num}行：数据属性组合 '{data_attributes_str}' 重复。")
            all_data_attributes.add(data_attributes_tuple)

        # 7. 记录功能过程和子过程描述的对应关系
        if process not in process_subprocesses_map:
            process_subprocesses_map[process] = [sub_process]
        else:
            if sub_process not in process_subprocesses_map[process]:
                process_subprocesses_map[process].append(sub_process)

    # 循环结束后检查触发事件对应的功能过程数量
    for trigger_event, processes in trigger_process_map.items():
        if not 1 <= len(processes) <= 6:
            errors.append(f"触发事件 '{trigger_event}' 对应功能过程数量不符合要求（应为1到6个）。")

    # 循环结束后检查功能过程对应的子过程描述数量
    for process, subprocesses in process_subprocesses_map.items():
        if not 2 <= len(subprocesses) <= 5:
            errors.append(f"功能过程 '{process}' 包含子过程描述数量不符合要求（应为2到5个）。")

    # 检查每个功能过程的数据移动类型是否符合要求 (E开头，W/X结尾, 以及 R 的数量)
    for process, moves in process_data_moves.items():
        if not moves:
            continue  # 允许moves为空
        if moves[0] != "E" or moves[-1] not in ("W", "X"):
            errors.append(f"功能过程 '{process}' 的数据移动类型不符合要求（应以E开头，W/X结尾）。")
            continue  # 继续检查下一个功能过程

        WX = ''
        for move in moves:
            if move == "W":
                WX += 'W'
            if move == 'X':
                WX += 'X'
            else:
                WX = ''
            if WX == 'WX':
                errors.append(f"功能过程 '{process}' 的数据移动类型不能是WX结构。")

        # 检查查询类功能是否为ERX结构
        if len(moves) == 3 and moves == ["E", "R", "X"]:
            continue  # 查询类，跳过后续检查

        # 检查连续R的数量 (新增)
        r_count = 0
        for move in moves:
            if move == "R":
                r_count += 1
                if r_count > 2:
                    errors.append(f"功能过程 '{process}' 的数据移动类型中包含连续2个或更多个R。")
                    break  # 发现连续2个R，停止检查此功能过程
            else:
                r_count = 0  # 重置连续R的计数

        # 检查其他类型功能是否为EX或EW结构（可包含R）
        if not ("E" in moves and moves[-1] in ("X", "W") and all(m in ("E", "X", "R", "W") for m in moves)):
            errors.append(f"功能过程 '{process}' 的数据移动类型不符合EX、EW或E-R-X/W结构。")

    # 更严格的数据组检查（在所有行处理完后）
    input_groups: Set[str] = set()
    output_groups: Set[str] = set()
    for row in table:
        data_move_type = row["数据移动类型"]
        data_group = row["数据组"]
        if data_move_type == "E":
            input_groups.add(data_group)
        elif data_move_type in ("X", "W"):  # 允许W作为出口
            output_groups.add(data_group)
    if input_groups.intersection(output_groups):
        errors.append("存在相同的数据组既用于输入又用于输出。")

    return (not errors), "\n".join(errors)


def markdown_table_to_list(markdown_table_str):
    """
    将Markdown表格字符串转换为Python列表。

    参数：
    markdown_table_str (str): Markdown表格字符串。

    返回值：
    list of dict: 转换后的Python列表。
    """
    html = markdown.markdown(markdown_table_str, extensions=['tables'])
    # 使用正则表达式提取表格内容
    table_match = re.search(r'<table>(.*?)</table>', html, re.DOTALL)
    if not table_match:
        return []
    table_html = table_match.group(1)

    rows = []
    header = []
    # 提取表头
    header_match = re.search(r'<thead>.*?<tr>(.*?)</tr>.*?</thead>', table_html, re.DOTALL)
    if header_match:
        header_row_html = header_match.group(1)
        header = [th.strip() for th in re.findall(r'<th.*>(.*?)</th>', header_row_html)]

    # 提取数据行
    body_match = re.search(r'<tbody>(.*?)</tbody>', table_html, re.DOTALL)
    if body_match:
        body_html = body_match.group(1)
        row_matches = re.findall(r'<tr>(.*?)</tr>', body_html, re.DOTALL)
        for row_html in row_matches:
            row_data = [td.strip() for td in re.findall(r'<td.*>(.*?)</td>', row_html)]
            if header:
                rows.append(dict(zip(header, row_data)))  # 与标题对应
            else:
                rows.append(row_data)  # 没有标题则直接返回列表
    return rows


def extract_table_from_text(text: str) -> str:
    """
    AI大模型回答输出的内容除了表格有可能还包含其它字符描述，这个方法专门提取表格内容。

    参数：
    text (str): 包含Markdown表格的文本。

    返回值：
    str: 提取出的Markdown表格字符串，如果未找到表格则返回None。
    """

    # 匹配Markdown表格的正则表达式（改进版，支持表格前后有空行）
    table_pattern = r"(?s)(?:^|\n)(?=\|)(.+?\n\|[-:| ]+\|.+?)(?:\n\n|\n*$)"

    match = re.search(table_pattern, text)

    if match:
        # 提取整个表格（包括表头和分隔行）
        table_text = match.group(0).strip()
        return table_text
    else:
        return ''


def extract_json_from_text(text: str) -> str:
    """
    AI大模型回答输出的内容除了表格有可能还包含其它字符描述，这个方法专门提取JSON。
    """
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    json_str = json_match.group(0)
    data = json.loads(json_str)

    return json_str


def validate_all_done(current_answer_content):
    # 对于输出行数较多的一次性无法全部回复，需要多轮对话，这里校验是否最后一轮对话
    if re.search(r'continue', current_answer_content, re.IGNORECASE):
        return 1  # 后续还有内容
    elif re.search(r'ALL_DONE', current_answer_content, re.IGNORECASE):
        return 0  # 最后一轮回复
    else:
        return 0  # 最后一轮回复


def validate_trigger_event_json(json_str, total_rows) -> Tuple[bool, str]:
    """
    校验AI生成的触发事件和功能过程列表（JSON格式）。

    Args:
        ai_response: AI的完整回复（可能包含非JSON内容）。
        total_rows:  预期的总行数。

    Returns:
        tuple: (bool, list)
            - 第一个元素: 是否校验通过 (True/False)。
            - 第二个元素: 如果校验失败，返回错误原因列表；如果校验通过，返回空列表。
    """

    errors: List[str] = []

    # 1. 尝试提取JSON
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        errors.append(f"JSON解析错误: {e}")
        return False, "\n".join(errors)  # 如果JSON解析失败，直接返回

    # 2. 结构校验
    if not isinstance(data, dict) or "functional_user_requirements" not in data:
        errors.append("JSON结构错误：缺少 'functional_user_requirements' 键。")

    else:
        for req_index, req in enumerate(data["functional_user_requirements"]):
            if not isinstance(req, dict) or "requirement" not in req or "trigger_events" not in req:
                errors.append(
                    f"JSON结构错误：'functional_user_requirements'[{req_index}] 缺少 'requirement' 或 'trigger_events' 键。")
                continue  # 如果缺少关键键，跳过当前需求，继续检查下一个

            # 新增校验 1: requirement 长度校验
            if len(req["requirement"]) > 40:
                errors.append(
                    f"功能用户需求[{req['requirement']}]名称长度不能超过40，请概况总结")

            if not isinstance(req["trigger_events"], list):
                errors.append(
                    f"JSON结构错误: 'functional_user_requirements'[{req_index}]['trigger_events'] 必须是列表。")
                continue

            # 新增校验 2: 同一个 functional_user_requirements 下的 trigger_events 数量不能超过 5 个
            if len(req["trigger_events"]) > 6:
                errors.append(
                    f"数量校验错误: 'functional_user_requirements'[{req_index}] 的触发事件 'trigger_events' 数量不能超过 6 个。可以拆分更多的功能用户需求来解决"
                )

            for event_index, event in enumerate(req["trigger_events"]):
                if not isinstance(event, dict) or "event" not in event or "functional_processes" not in event:
                    errors.append(
                        f"JSON结构错误：'functional_user_requirements'[{req_index}]['trigger_events'][{event_index}] 缺少 'event' 或 'functional_processes' 键。")
                    continue

                if not isinstance(event["functional_processes"], list):
                    errors.append(
                        f"JSON结构错误：'functional_user_requirements'[{req_index}]['trigger_events'][{event_index}]['functional_processes'] 必须是列表。")
                    continue

                if not all(isinstance(process, str) for process in event["functional_processes"]):
                    errors.append(
                        f"JSON结构错误：'functional_user_requirements'[{req_index}]['trigger_events'][{event_index}]['functional_processes'] 的元素必须是字符串。")
                    continue

                # 3. 数量和关系校验
                if not (1 <= len(event["functional_processes"]) <= 6):
                    errors.append(
                        f"数量校验错误：'functional_user_requirements'[{req_index}]['trigger_events'][{event_index}]['functional_processes'] 应该包含 1 到 6 个元素。一个触发事件一般对应1到6个功能过程")

        # 4. 触发事件数量校验 (至少一个)
        all_trigger_events = [event for req in data["functional_user_requirements"] for event in req["trigger_events"]]
        if not all_trigger_events:
            errors.append("数量校验错误：至少需要一个触发事件。")

        # 5. 功能过程总数校验 (根据总行数计算范围)
        total_processes = sum(len(event["functional_processes"]) for event in all_trigger_events)
        lower_bound = total_rows // 3.3
        upper_bound = total_rows // 2.5
        m_bound = total_rows // 3
        if not (lower_bound <= total_processes <= upper_bound):
            errors.append(f"数量校验错误：功能过程的总数应在 {m_bound} 个左右（基于总行数 {total_rows}）。")

        # 6. 触发事件和功能过程的描述格式校验 (仅当 all_trigger_events 不为空时)
        if all_trigger_events:
            for event in all_trigger_events:
                # 以下校验太严格，先注释掉
                # if not re.match(r"^[\u4e00-\u9fa5_a-zA-Z0-9]+[操作|点击|打开|触发][\u4e00-\u9fa5_a-zA-Z0-9]+$", event["event"]) and \
                #    not re.match(r"^[\u4e00-\u9fa5_a-zA-Z0-9]+被[\u4e00-\u9fa5_a-zA-Z0-9]+$", event["event"]) :
                #     errors.append(f"格式校验错误：触发事件描述 '{event['event']}' 不符合 '操作+对象' 或 '对象+被操作' 的格式。")

                for process in event["functional_processes"]:
                    if "校验" in process:
                        errors.append(f"格式校验错误：功能过程描述 '{process}' 禁止包含 '校验'，请替换表达词语。")

        # 7. 功能过程判重
        all_processes = []
        for req in data["functional_user_requirements"]:
            for event in req["trigger_events"]:
                for process in event["functional_processes"]:
                    if process in all_processes:
                        errors.append(f"重复性校验错误: 功能过程 '{process}' 重复。")
                    else:
                        all_processes.append(process)

    # 返回校验结果和错误信息

    return not errors, "\n".join(errors)
