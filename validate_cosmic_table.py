import re
import json

import markdown
from typing import List, Dict, Tuple, Set, Optional, Any, Union

# 校验、文本内容提取相关
import re
from typing import List, Dict, Tuple, Set
from typing import Tuple
# 假设 markdown_table_to_list 函数已经定义

def validate_cosmic_table(markdown_table_str: str, request_name: str) -> Tuple[bool, str]:
    """
    校验COSMIC功能点度量表格。

    参数：
    markdown_table_str (str): Markdown格式的表格字符串。
    request_name (str): 客户需求名称。

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

        # 检查是否为 WX 结构
        if moves == ["E","W", "X"]:
            errors.append(f"功能过程 '{process}' 的数据移动类型不能是 WX 结构。")

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
    如果输入字符串包含 ```markdown ... ``` 标记，会先提取其中的内容。

    参数：
    markdown_table_str (str): Markdown表格字符串，可以包含代码块标记。

    返回值：
    list of dict: 转换后的Python列表，如果无法解析则返回空列表。
    """
    # 预处理：移除可选的 ```markdown ... ``` 包围符
    # 匹配 ```markdown 开头 (忽略前后空格和换行) 和 ``` 结尾
    # 并提取中间的内容
    match = re.search(r"^\s*```(?:markdown)?\s*\n?(.*?)\n?\s*```\s*$", markdown_table_str, re.DOTALL | re.IGNORECASE)
    if match:
        markdown_content = match.group(1).strip() # 提取括号里的内容并去除首尾空格
    else:
        # 如果没有匹配到代码块标记，假定整个输入就是Markdown内容
        markdown_content = markdown_table_str.strip()

    if not markdown_content: # 如果提取后内容为空，则直接返回
        return []

    # 将Markdown转换为HTML (只转换提取出的内容)
    html = markdown.markdown(markdown_content, extensions=['tables'])
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



# --- 配置和常量 ---

# 允许的功能用户枚举值 (值必须是中文)
ALLOWED_FUNCTIONAL_USERS = {
    "操作员",
    "个人网台",
    "订单中心",
    "账管中心",
    "基础中心",
    "产商品中心",
    "后台进程",
}

# 预期的顶层键
EXPECTED_TOP_LEVEL_KEYS = {
    "customerRequirement",
    "requirementBackground",
    "functionalPoints",
}

# 预期的功能点内键
EXPECTED_FUNCTIONAL_POINT_KEYS = {
    "functionalUser",
    "requirementDescription",
    "detailedSolution",
    "workloadPercentage",
}

# 预期的功能用户键
EXPECTED_FUNCTIONAL_USER_KEYS = {"initiator", "receiver"}

# 禁止的键
FORBIDDEN_KEYS_IN_FUNCTIONAL_POINT = {"processingLogic"}

# --- 辅助函数 ---

def is_primarily_chinese(text: str) -> bool:
    """
    检查字符串是否主要包含中文字符。
    一个简单的检查，判断是否存在至少一个 CJK 统一表意文字。
    """
    if not isinstance(text, str) or not text.strip():
        return False # 空字符串或非字符串不视作中文
    # CJK Unified Ideographs (基本常用汉字范围)
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def validate_structure_and_types(data: Any, errors: List[str]) -> bool:
    """校验顶层结构和基本类型"""
    if not isinstance(data, dict):
        errors.append("顶层必须是一个 JSON 对象 (字典)")
        return False

    # 检查顶层键是否存在
    missing_top_keys = EXPECTED_TOP_LEVEL_KEYS - data.keys()
    if missing_top_keys:
        errors.append(f"顶层缺少必需的键: {', '.join(missing_top_keys)}")

    # 检查多余的顶层键
    extra_top_keys = data.keys() - EXPECTED_TOP_LEVEL_KEYS
    if extra_top_keys:
        errors.append(f"顶层包含不允许的键: {', '.join(extra_top_keys)}")

    # 检查类型和中文值
    if "customerRequirement" in data:
        if not isinstance(data["customerRequirement"], str):
            errors.append("customerRequirement 的值必须是字符串")
        elif not is_primarily_chinese(data["customerRequirement"]):
             errors.append("customerRequirement 的值必须是中文")

    if "requirementBackground" in data:
        if not isinstance(data["requirementBackground"], str):
            errors.append("requirementBackground 的值必须是字符串")
        elif not is_primarily_chinese(data["requirementBackground"]):
             errors.append("requirementBackground 的值必须是中文")

    if "functionalPoints" in data and not isinstance(data["functionalPoints"], list):
        errors.append("functionalPoints 的值必须是一个数组 (列表)")

    # 返回是否有结构性错误（不包括类型/值错误，那些继续检查）
    return not bool(missing_top_keys or extra_top_keys)


# --- 主要校验函数 ---

def validate_requirement_json(json_str: str) -> Tuple[bool, str]:
    """
    校验软件需求 JSON 字符串是否符合预定义规则。

    Args:
        json_str: 包含 JSON 数据的字符串。

    Returns:
        一个元组 (is_valid, error_message)，其中 is_valid 是布尔值，
        error_message 是包含所有校验错误的单个字符串（错误间用换行符分隔），
        如果 JSON 有效，则 error_message 为空字符串。
    """
    errors: List[str] = []
    data: Optional[Dict[str, Any]] = None

    # 1. 解析 JSON 字符串
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        errors.append(f"JSON 解析失败: {e}")
        return False, "\n".join(errors)
    except Exception as e:
        errors.append(f"解析 JSON 时发生意外错误: {e}")
        return False, "\n".join(errors)

    if data is None: # 理论上 json.loads 成功就不会是 None，但作为防御性检查
         errors.append("未能成功解析数据")
         return False, "\n".join(errors)

    # 2. 校验顶层结构和类型
    validate_structure_and_types(data, errors) # 收集结构和顶层类型错误

    # 3. 校验 functionalPoints 列表 (即使顶层结构有误也尝试检查，以收集更多信息)
    functional_points = data.get("functionalPoints")
    total_workload = 0
    if not isinstance(functional_points, list):
        # 如果 functionalPoints 存在但不是列表，之前已记录错误，此处无需重复
        # 如果 functionalPoints 不存在，之前已记录错误
        pass
    else: # functional_points 是一个列表
        if not functional_points:
             errors.append("functionalPoints 列表不能为空")

        for i, fp in enumerate(functional_points):
            fp_prefix = f"functionalPoints[{i}]"

            if not isinstance(fp, dict):
                errors.append(f"{fp_prefix}: 每个功能点必须是一个对象 (字典)")
                continue # 跳过对此项的进一步检查

            # 检查功能点内部的键
            missing_fp_keys = EXPECTED_FUNCTIONAL_POINT_KEYS - fp.keys()
            if missing_fp_keys:
                errors.append(f"{fp_prefix}: 缺少必需的键: {', '.join(missing_fp_keys)}")

            extra_fp_keys = fp.keys() - EXPECTED_FUNCTIONAL_POINT_KEYS
            if extra_fp_keys:
                errors.append(f"{fp_prefix}: 包含不允许的键: {', '.join(extra_fp_keys)}")

            # 检查禁止的键
            forbidden_found = FORBIDDEN_KEYS_IN_FUNCTIONAL_POINT.intersection(fp.keys())
            if forbidden_found:
                 errors.append(f"{fp_prefix}: 包含禁止的键: {', '.join(forbidden_found)}")

            # 校验 functionalUser
            fu = fp.get("functionalUser")
            if "functionalUser" in fp:
                if not isinstance(fu, dict):
                    errors.append(f"{fp_prefix}.functionalUser: 必须是一个对象 (字典)")
                else:
                    missing_fu_keys = EXPECTED_FUNCTIONAL_USER_KEYS - fu.keys()
                    if missing_fu_keys:
                        errors.append(f"{fp_prefix}.functionalUser: 缺少必需的键: {', '.join(missing_fu_keys)}")
                    extra_fu_keys = fu.keys() - EXPECTED_FUNCTIONAL_USER_KEYS
                    if extra_fu_keys:
                         errors.append(f"{fp_prefix}.functionalUser: 包含不允许的键: {', '.join(extra_fu_keys)}")

                    for user_key in ["initiator", "receiver"]:
                        user_value = fu.get(user_key)
                        if user_key in fu:
                            if not isinstance(user_value, str):
                                errors.append(f"{fp_prefix}.functionalUser.{user_key}: 值必须是字符串")
                            elif not user_value:
                                errors.append(f"{fp_prefix}.functionalUser.{user_key}: 值不能为空字符串")
                            elif user_value not in ALLOWED_FUNCTIONAL_USERS:
                                errors.append(f"{fp_prefix}.functionalUser.{user_key}: 值 '{user_value}' 不在允许的枚举列表中: {ALLOWED_FUNCTIONAL_USERS}")

            # 校验 requirementDescription
            req_desc = fp.get("requirementDescription")
            if "requirementDescription" in fp:
                if not isinstance(req_desc, str):
                    errors.append(f"{fp_prefix}.requirementDescription: 值必须是字符串")
                elif not is_primarily_chinese(req_desc):
                     errors.append(f"{fp_prefix}.requirementDescription: 值必须是中文")

            # 校验 detailedSolution
            det_sol = fp.get("detailedSolution")
            if "detailedSolution" in fp:
                if not isinstance(det_sol, list):
                    errors.append(f"{fp_prefix}.detailedSolution: 值必须是一个数组 (列表)")
                else:
                    if not det_sol:
                        errors.append(f"{fp_prefix}.detailedSolution: 列表不能为空")
                    for j, sol_item in enumerate(det_sol):
                        if not isinstance(sol_item, str):
                            errors.append(f"{fp_prefix}.detailedSolution[{j}]: 列表中的每个元素都必须是字符串")
                        elif not is_primarily_chinese(sol_item):
                             errors.append(f"{fp_prefix}.detailedSolution[{j}]: 字符串值必须是中文")

            # 校验 workloadPercentage
            wp = fp.get("workloadPercentage")
            if "workloadPercentage" in fp:
                if not isinstance(wp, int) or isinstance(wp, bool): # bool is subclass of int
                    errors.append(f"{fp_prefix}.workloadPercentage: 值必须是整数 (非布尔值)")
                elif not (0 <= wp <= 100):
                    errors.append(f"{fp_prefix}.workloadPercentage: 值 {wp} 必须在 0 到 100 之间")
                else:
                    total_workload += wp

    # 4. 校验总工作量占比 (仅当 functionalPoints 是非空列表时)
    if isinstance(functional_points, list) and functional_points:
        if total_workload != 100:
            errors.append(f"所有 functionalPoints 的 workloadPercentage 总和 ({total_workload}) 不等于 100")

    # 5. 返回结果
    is_valid = not bool(errors)
    error_message = "\n".join(errors)
    return is_valid, error_message
