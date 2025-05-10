import json
import re
from collections import defaultdict
from math import ceil, floor
from typing import Tuple, Dict, List, Any, Set
from cosmic_processor.utils.validators import calculate_levenshtein_similarity


def validate_requirement_analysis_json(json_str: str) -> Tuple[bool, str]:
    # --- 配置常量 ---

    # 功能用户分类规则中允许的参与者类型
    ALLOWED_PARTICIPANT_TYPES: Set[str] = {
        "操作员", "个人网台", "订单中心", "账管中心", "产商品中心",
        "后台进程", "基础中心", "小屏", "短厅"
    }

    # 功能用户分类规则中允许的参与者类型
    ALLOWED_PARTICIPANT_R_TYPES: Set[str] = {
        "订单中心", "账管中心", "产商品中心",
        "后台进程", "基础中心"
    }

    # 功能过程名称中绝对禁止的词语
    FORBIDDEN_PROCESS_WORDS: Set[str] = {
        "加载", "解析", "初始化", "点击按钮", "页面", "渲染", "切换", "计算",
        "重置", "分页", "排序", "适配", "开发", "部署", "迁移", "安装",
        "存储", "缓存", "校验", "验证", "是否", "判断", "组装报文", "构建报文",
        '临时表', '内存', '缓存', '检验', '校验', '分析',
        '判断', '解析', '后台', '数据库读取', '接口返回', '接口调用', '生成一条','维护','配置','执行' ,"系统","检索","政策"
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
    EVENT_DESC_MIN_LEN: int = 8
    EVENT_DESC_MAX_LEN: int = 40

    # 功能过程名称字数限制
    PROCESS_NAME_MIN_LEN: int = 8
    PROCESS_NAME_MAX_LEN: int = 40

    # 工作量估算范围 (当无法从文本提取时)
    WORKLOAD_ESTIMATE_MIN: int = 10
    WORKLOAD_ESTIMATE_MAX: int = 300

    # FUR 拆分工作量基准和浮动比例
    FUR_WORKLOAD_TARGET: int = 30
    FUR_WORKLOAD_FLUCTUATION: float = 0.10  # +/- 10%

    # 功能过程总数与工作量比例基准和浮动比例
    PROCESS_COUNT_WORKLOAD_RATIO: float = 2 / 5
    PROCESS_COUNT_FLUCTUATION: float = 0.05  # +/- 5%


    MAX_SIMILARITY: float = 0.8  # 文本相似度

    MAX_FUNCTIONAL_PROCESSES: int = 20  # 每个触发事件的最大功能过程数量

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
            errors.append("JSON校验不通过，JSON顶层结构似乎不正确，请确保包含 'requirementAnalysis' 键。")
            return False, "\n".join(errors)
        analysis_data = data["requirementAnalysis"]
        if not isinstance(analysis_data, dict):
             errors.append("JSON校验不通过，'requirementAnalysis' 的值应该是JSON对象格式。")
             return False, "\n".join(errors)

    except json.JSONDecodeError as e:
        errors.append(f"JSON校验不通过，提供的回复不是有效的JSON格式，解析时出错了：{e}。请检查括号、逗号、引号是否匹配。")
        return False, "\n".join(errors)

    # 2. 校验顶层字段存在性和类型
    required_keys = ["customerRequirement", "customerRequirementWorkload", "functionalUserRequirements"]
    for key in required_keys:
        if key not in analysis_data:
            errors.append(f"JSON校验不通过，'requirementAnalysis' 对象中缺少必要的字段 '{key}'。请补充。")
        elif key == "customerRequirement" and not isinstance(analysis_data.get(key), str):
             errors.append(f"JSON校验不通过，字段 '{key}' 的值应该是字符串类型。")
        elif key == "customerRequirementWorkload" and not isinstance(analysis_data.get(key), int):
             errors.append(f"JSON校验不通过，字段 '{key}' 的值应该是整数类型。")
        elif key == "functionalUserRequirements" and not isinstance(analysis_data.get(key), list):
             errors.append(f"JSON校验不通过，字段 '{key}' 的值应该是列表（数组）类型。")

    # 如果基础结构错误，提前返回
    if errors:
        return False, "\n".join(errors)

    # 3. 校验 customerRequirementWorkload 范围 (仅当它是估算值时，但我们无法区分，所以统一校验范围)
    #   更新：根据提示词，如果能提取到明确值，可能超出10-300。因此只校验类型（已在上面完成）。
    #   如果需要强制估算值也在10-300内，可以取消下面注释，但这可能与提取逻辑冲突。
    # workload = analysis_data.get("customerRequirementWorkload", 0)
    # if not (WORKLOAD_ESTIMATE_MIN <= workload <= WORKLOAD_ESTIMATE_MAX):
    #     errors.append(f"JSON校验不通过，'customerRequirementWorkload' 的值 ({workload}) 超出了建议的估算范围 ({WORKLOAD_ESTIMATE_MIN}-{WORKLOAD_ESTIMATE_MAX})。如果这是估算值，请调整；如果是提取值，请忽略此条。")

    workload = analysis_data.get("customerRequirementWorkload", 0) # 后续计算需要

    # 4. 校验 functionalUserRequirements (FURs)
    furs = analysis_data.get("functionalUserRequirements", [])
    num_furs = len(furs)

    # 4.1 校验FUR数量与工作量的关系
    if workload > 0: # 避免除以零
        target_furs = workload / FUR_WORKLOAD_TARGET
        min_expected_furs = floor(target_furs * (1 - FUR_WORKLOAD_FLUCTUATION))
        max_expected_furs = ceil(target_furs * (1 + FUR_WORKLOAD_FLUCTUATION))
        if not (min_expected_furs <= num_furs <= max_expected_furs):
             errors.append(f"JSON校验不通过，根据工作量 {workload}，预期的功能用户需求(FUR)数量应在 {min_expected_furs}-{max_expected_furs} 个左右 (每个FUR约{FUR_WORKLOAD_TARGET}工作量)。当前数量为 {num_furs} 个，请检查FUR的拆分是否合理。")

    # First collect all event descriptions with their full paths
    all_events = []
    for i, fur in enumerate(furs):
        if not isinstance(fur, dict):
            errors.append(f"JSON校验不通过，功能用户需求列表中的第 {i+1} 项不是有效的JSON对象格式。")
            continue # 跳过对此项的后续检查

        fur_ref = f"功能用户需求列表第 {i+1} 项"
        triggering_events = fur.get("triggeringEvents", [])
        
        for j, event in enumerate(triggering_events):
            if not isinstance(event, dict):
                continue
                
            event_desc = event.get("eventDescription", "")
            if event_desc and isinstance(event_desc, str):
                all_events.append({
                    "desc": event_desc,
                    "fur_idx": i,
                    "event_idx": j,
                    "fur_ref": fur_ref,
                    "event_ref": f"{fur_ref} 的触发事件列表第 {j+1} 项"
                })

    fb_flag = False
    for i, fur in enumerate(furs):
        if not isinstance(fur, dict):
            continue # Already checked above

        # 4.2 校验FUR描述 (`description`)
        fur_desc = fur.get("description")
        fur_ref = f"功能用户需求列表第 {i+1} 项"
        if not fur_desc or not isinstance(fur_desc, str):

            errors.append(f"JSON校验不通过，{fur_ref} 缺少 'description' 字段或其值不是字符串。")
        else:
            # 校验字数
            if not (FUR_DESC_MIN_LEN <= len(fur_desc) <= FUR_DESC_MAX_LEN):
                errors.append(f"JSON校验不通过，{fur_ref} 的描述 '{fur_desc}' 长度为 {len(fur_desc)} 字，不符合 {FUR_DESC_MIN_LEN}-{FUR_DESC_MAX_LEN} 字的要求。请调整描述长度。")
            # 校验唯一性
            if fur_desc in seen_fur_descs:
                errors.append(f"JSON校验不通过，{fur_ref} 的描述 '{fur_desc}' 与之前的某个功能用户需求描述重复了。请确保每个描述都是唯一的。")
            seen_fur_descs.add(fur_desc)

        # 4.3 校验 triggeringEvents 列表
        triggering_events = fur.get("triggeringEvents")
        if not isinstance(triggering_events, list):
             errors.append(f"JSON校验不通过，{fur_ref} 缺少 'triggeringEvents' 字段或其值不是列表。")
             continue # 跳过事件检查

        for j, event in enumerate(triggering_events):
            if not isinstance(event, dict):
                errors.append(f"JSON校验不通过，{fur_ref} 的触发事件列表中的第 {j+1} 项不是有效的JSON对象格式。")
                continue # 跳过对此事件的后续检查

            event_ref = f"{fur_ref} 的触发事件列表第 {j+1} 项"

            # 4.3.1 校验触发事件描述 (`eventDescription`)
            event_desc = event.get("eventDescription")
            if not event_desc or not isinstance(event_desc, str):
                errors.append(f"JSON校验不通过，{event_ref} 缺少 'eventDescription' 字段或其值不是字符串。")
            else:
                # 校验字数
                if not (EVENT_DESC_MIN_LEN <= len(event_desc) <= EVENT_DESC_MAX_LEN):
                    errors.append(f"JSON校验不通过，{event_ref} 的描述 '{event_desc}' 长度为 {len(event_desc)} 字，不符合 {EVENT_DESC_MIN_LEN}-{EVENT_DESC_MAX_LEN} 字的要求。请调整描述长度。")
                # 校验唯一性 (与其他事件描述)
                if event_desc in seen_event_descs:
                     errors.append(f"JSON校验不通过，{event_ref} 的描述 '{event_desc}' 与之前的某个触发事件描述重复了。请确保每个触发事件描述都是唯一的。")
                seen_event_descs.add(event_desc)
                # 校验唯一性 (与FUR描述)
                if event_desc in seen_fur_descs:
                     errors.append(f"JSON校验不通过，{event_ref} 的描述 '{event_desc}' 与某个功能用户需求的描述相同了。请修改触发事件描述，使其与功能用户需求描述不同。")

            # 4.3.2 校验参与者 (`participants`)
            participants_str = event.get("participants")
            if not participants_str or not isinstance(participants_str, str):
                errors.append(f"JSON校验不通过，{event_ref} 缺少 'participants' 字段或其值不是字符串。")
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
                    errors.append(f"JSON校验不通过，{event_ref} 的 'participants' 字段 ('{participants_str}') 格式不正确。请严格按照 '发起者: [类型]\\n接收者：[类型]' 的格式书写，注意换行。")
                else:
                    # 校验发起者类型
                    if initiator_type not in ALLOWED_PARTICIPANT_TYPES:
                        errors.append(f"JSON校验不通过，{event_ref} 的 'participants' 中的发起者类型 '{initiator_type}' 不在允许的类型列表中 ({', '.join(ALLOWED_PARTICIPANT_TYPES)})。请修正。")
                    # 校验接收者类型
                    if receiver_type not in ALLOWED_PARTICIPANT_R_TYPES:
                         errors.append(f"JSON校验不通过，{event_ref} 的 'participants' 中的接收者类型 '{receiver_type}' 不在允许的类型列表中 ({', '.join(ALLOWED_PARTICIPANT_R_TYPES)})。请修正。")
                    # 校验发起者和接收者不能相同
                    if initiator_type == receiver_type:
                         errors.append(f"JSON校验不通过，{event_ref} 的 'participants' 中发起者和接收者类型相同 ('{initiator_type}')。发起者和接收者不能是同一类型。请修正。")

            # 4.3.3 校验 functionalProcesses 列表
            functional_processes = event.get("functionalProcesses")
            if not isinstance(functional_processes, list):
                errors.append(f"JSON校验不通过，{event_ref} 缺少 'functionalProcesses' 字段或其值不是列表。")
                continue # 跳过过程检查

            # 校验功能过程数量不超过6个
            if len(functional_processes) > MAX_FUNCTIONAL_PROCESSES:
                errors.append(f"JSON校验不通过，{event_ref} 的功能过程数量 ({len(functional_processes)}) 超过{MAX_FUNCTIONAL_PROCESSES}个。每个触发事件的功能过程不能超过{MAX_FUNCTIONAL_PROCESSES}个，请考虑拆分该触发事件。")

            total_process_count += len(functional_processes) # 累加功能过程总数

            for k, process in enumerate(functional_processes):
                 if not isinstance(process, dict):
                     errors.append(f"JSON校验不通过，{event_ref} 的功能过程列表中的第 {k+1} 项不是有效的JSON对象格式。")
                     continue # 跳过对此过程的后续检查

                 process_ref = f"{event_ref} 的功能过程列表第 {k+1} 项"

                 # 校验功能过程名称 (`processName`)
                 process_name = process.get("processName")
                 if not process_name or not isinstance(process_name, str):
                     errors.append(f"JSON校验不通过，{process_ref} 缺少 'processName' 字段或其值不是字符串。")
                 else:
                     # 校验字数
                     if not (PROCESS_NAME_MIN_LEN <= len(process_name) <= PROCESS_NAME_MAX_LEN):
                         errors.append(f"JSON校验不通过，{process_ref} 的名称 '{process_name}' 长度为 {len(process_name)} 字，不符合 {PROCESS_NAME_MIN_LEN}-{PROCESS_NAME_MAX_LEN} 字的要求。请调整名称，使其更丰富或简洁。")
                     # 校验唯一性
                     if process_name in seen_process_names:
                         errors.append(f"JSON校验不通过，{process_ref} 的名称 '{process_name}' 与之前的某个功能过程名称重复了。请确保每个功能过程名称都是唯一的，并考虑是否需要合并相似的过程。")
                     seen_process_names.add(process_name)
                     
                     # 校验功能过程名称相似度
                     for other_process in functional_processes[:k]:
                         other_name = other_process.get("processName", "")
                         if other_name and isinstance(other_name, str):
                             similarity = calculate_levenshtein_similarity(process_name, other_name)
                             if similarity > MAX_SIMILARITY:
                                 errors.append(f"JSON校验不通过，{process_ref} 的名称 '{process_name}' 与功能过程名称 '{other_name}' 相似度过高 ({similarity:.2f})。相似度超过{MAX_SIMILARITY}，请重新生成更明确区分的、语义不同的功能过程名称。")
                     
                     # 校验禁用词
                     found_forbidden = []
                     for word in FORBIDDEN_PROCESS_WORDS:
                         if word in process_name:
                             found_forbidden.append(word)
                     if found_forbidden:
                         errors.append(f"JSON校验不通过，{process_ref} 的名称 '{process_name}' 中包含了禁用词: '{', '.join(found_forbidden)}'。请修改名称，避免使用这些词语。")
                         fb_flag = True
                     # 校验禁用模式 (日志)
                     for pattern in FORBIDDEN_PROCESS_PATTERNS:
                         if re.search(pattern, process_name):
                             errors.append(f"JSON校验不通过，{process_ref} 的名称 '{process_name}' 似乎与日志记录有关，这通常不应作为独立的功能过程。请检查是否应移除或合并。")
                             break # 找到一个匹配就够了


    if fb_flag:
       errors.append(f'功能过程 **禁用词**：{"，".join(FORBIDDEN_PROCESS_WORDS)}')

    # 5. 校验功能过程总数与工作量的关系
    if workload > 0:
        target_processes = workload * PROCESS_COUNT_WORKLOAD_RATIO
        min_expected_processes = round(target_processes * (1 - PROCESS_COUNT_FLUCTUATION))
        max_expected_processes = round(target_processes * (1 + PROCESS_COUNT_FLUCTUATION))
        if not (min_expected_processes <= total_process_count <= max_expected_processes):
            if total_process_count < min_expected_processes:
                diff = min_expected_processes - total_process_count
                errors.append(f"JSON校验不通过，根据工作量 {workload}，预期的功能过程总数量应在 {min_expected_processes}-{max_expected_processes} 个左右 (约为工作量的2/5)。当前总共识别出 {total_process_count} 个功能过程，需要增加 {diff} 个功能过程。请检查功能过程的拆分是否足够细化。")
            else:
                diff = total_process_count - max_expected_processes
                errors.append(f"JSON校验不通过，根据工作量 {workload}，预期的功能过程总数量应在 {min_expected_processes}-{max_expected_processes} 个左右 (约为工作量的2/5)。当前总共识别出 {total_process_count} 个功能过程，需要减少 {diff} 个功能过程。请检查功能过程的合并是否合理。")

            errors.append('**推荐内容**: **多写查询类的功能过程**，少写操作类的功能过程')
    # 5.1 全局校验事件描述相似度
    for i in range(len(all_events)):
        for j in range(i+1, len(all_events)):
            event1 = all_events[i]
            event2 = all_events[j]
            similarity = calculate_levenshtein_similarity(event1["desc"], event2["desc"])
            if similarity > MAX_SIMILARITY:
                errors.append(
                    f"JSON校验不通过，{event1['event_ref']} 的描述 '{event1['desc']}' "
                    f"与 {event2['event_ref']} 的描述 '{event2['desc']}' "
                    f"相似度过高 ({similarity:.2f})。相似度超过{MAX_SIMILARITY}，"
                    "请重新生成更明确区分的、语义不同的触发事件描述。"
                )

    # 返回结果
    return not errors, "\n".join(errors)
