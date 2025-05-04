import re
import json # 虽然我们是手动构建字符串，但导入json可能有助于未来扩展

def split_prompt_for_finetuning(prompt_text, max_length=3900, description="AI系统提示词"):
    """
    Splits a long prompt text into smaller chunks suitable for fine-tuning,
    formatted as JSON strings per line.

    Args:
        prompt_text (str): The original prompt text.
        max_length (int): Maximum character length for the entire JSON string line.
        description (str): The descriptive text to use in the JSON structure.

    Returns:
        list[str]: A list of formatted JSON strings, each representing a chunk.
    """
    # Define the template parts and calculate overhead
    prefix = f'{{"text": "{description}<|cosmic_requirement_analysis|>'
    suffix = '"}'
    # Need to escape special characters in the prompt text for JSON string compatibility?
    # No, the prompt text itself doesn't need JSON escaping *within* the <|input|>...<|output|> part
    # as it's treated as raw text payload for the model. The outer structure is JSON.
    # However, if the description itself contained quotes, it would need escaping.
    # Let's assume the description is safe.

    overhead = len(prefix) + len(suffix)
    max_content_length = max_length - overhead

    if max_content_length <= 0:
        raise ValueError(f"max_length ({max_length}) is too small to fit the template overhead ({overhead}).")

    chunks = []
    current_chunk = ""
    # Split by paragraphs (one or more blank lines) while keeping separators
    # This helps maintain logical structure better than just splitting by lines
    blocks = re.split(r'(\n\s*\n)', prompt_text)

    # Process blocks and separators
    processed_blocks = []
    i = 0
    while i < len(blocks):
        block_content = blocks[i]
        if i + 1 < len(blocks):
            separator = blocks[i+1]
            processed_blocks.append(block_content + separator) # Add block and its trailing separator
            i += 2
        else:
            if block_content: # Add the last block if it's not empty
                 processed_blocks.append(block_content)
            i += 1

    current_chunk_content = ""
    for block in processed_blocks:
        block_len = len(block)

        if block_len > max_content_length:
            # --- Block is too long, needs internal splitting ---
            # 1. Finalize the current chunk if it has content
            if current_chunk_content:
                chunks.append(f"{prefix}{current_chunk_content}{suffix}")
                current_chunk_content = ""

            # 2. Split the long block itself (e.g., by lines, then by length)
            lines = block.splitlines(keepends=True)
            temp_line_chunk = ""
            for line in lines:
                line_len = len(line)
                if line_len > max_content_length:
                    # -- Single line is too long --
                    # a. Add any accumulated lines before this super long line
                    if temp_line_chunk:
                        chunks.append(f"{prefix}{temp_line_chunk}{suffix}")
                        temp_line_chunk = ""
                    # b. Split the super long line itself character by character
                    start = 0
                    while start < line_len:
                        end = start + max_content_length
                        line_piece = line[start:end]
                        chunks.append(f"{prefix}{line_piece}{suffix}")
                        start = end
                elif len(temp_line_chunk) + line_len <= max_content_length:
                    # Line fits in the current temporary line chunk
                    temp_line_chunk += line
                else:
                    # Line doesn't fit, finalize the temp line chunk
                    if temp_line_chunk:
                         chunks.append(f"{prefix}{temp_line_chunk}{suffix}")
                    # Start new temp line chunk with the current line
                    temp_line_chunk = line
            # Add any remaining lines from the long block processing
            if temp_line_chunk:
                chunks.append(f"{prefix}{temp_line_chunk}{suffix}")
            # Reset current_chunk_content as it was handled within this block
            current_chunk_content = ""

        elif len(current_chunk_content) + block_len <= max_content_length:
            # --- Block fits in the current chunk ---
            current_chunk_content += block
        else:
            # --- Block doesn't fit, finalize current chunk and start new one ---
            if current_chunk_content:
                chunks.append(f"{prefix}{current_chunk_content}{suffix}")
            # Start the new chunk with the current block
            current_chunk_content = block

    # Add the last remaining chunk if it exists
    if current_chunk_content:
        chunks.append(f"{prefix}{current_chunk_content}{suffix}")

    # Verification step (optional but recommended)
    for i, chunk_str in enumerate(chunks):
        if len(chunk_str) > max_length:
            print(f"Warning: Chunk {i} exceeds max length ({len(chunk_str)} > {max_length})")
            # This indicates a potential issue in the splitting logic, especially around very long lines/blocks.

    return chunks

# --- Load the prompt text from the provided file content ---
prompt_text = """# 角色

你是一位精通COSMIC功能点度量方法的专家分析师。你的核心任务是根据用户提供的软件需求原始描述（可能包含需求名称、需求背景、详细解决方案等），严格遵循COSMIC方法论的核心原则和用户指定的规则，进行细致的分析和拆分，最终以**精确的JSON格式**输出分析结果。

# 核心目标

接收用户输入的原始需求文档内容，输出一个结构化JSON，该JSON包含对需求的COSMIC元素分析，具体包括：客户需求、客户需求工作量、功能用户需求、触发事件、参与者（发起者和接收者）以及功能过程。**输出必须严格遵守下述所有规则和约束。**

# 核心原则与规则（必须严格遵守）

1.  **COSMIC基础**:
    *   度量基于识别“数据移动”（输入E、输出X、读取R、写入W）。虽然最终JSON不直接列出数据移动，但识别功能过程时需以此为基础。
    *   聚焦用户所需的核心功能数据移动，避免技术实现细节、通用组件（如日志、通用上传/下载）的干扰，除非它们是特定FUR的核心处理步骤。
    *   使用用户能理解的业务语言描述功能。

2.  **JSON输出结构**: 必须严格按照以下结构输出，字段名使用英文，字段值使用中文（`customerRequirementWorkload` 的值为整数）：
    ```json
    {
      "requirementAnalysis": {
        "customerRequirement": "客户需求名称或标题",
        "customerRequirementWorkload": 100, // 示例：客户需求工作量，整数
        "functionalUserRequirements": [
          {
            "description": "功能用户需求1的描述 (10-40字)",
            "triggeringEvents": [
              {
                "eventDescription": "触发事件1的描述 (10-40字, 动词+对象/对象+动词)",
                "participants": "发起者: 类型A\\n接收者：类型B", // 必须是多行字符串格式, 类型需符合规则
                "functionalProcesses": [
                  {
                    "processName": "功能过程1的名称 (10-40字, 业务语言, 避免禁用词)"
                  }
                  // 可能有更多功能过程
                ]
              }
              // 可能有更多触发事件
            ]
          }
          // 可能有更多功能用户需求
        ]
      }
    }
    ```

3.  **字段提取与定义 - 详细规则**:

    *   **`customerRequirement`**:
        *   从输入内容中提取明确标识的**最高层级需求名称或文档标题**。

    *   **`customerRequirementWorkload`**:
        *   **优先规则**: 在输入文本中查找是否包含明确表示总工作量或规模的短语，如“需求总工作量”、“cosmic总行数”、“总规模”、“总点数”等，并提取其对应的**整数值**。例如，如果文本中有“cosmic编写总行数：150”，则此字段值为 `150`。
        *   **备选规则**: 如果在输入文本中**找不到**明确的工作量或规模数值，则你需要根据对需求的整体理解，**估算一个工作量值**，该值必须是一个**介于10到300之间（包含10和300）的整数**。

    *   **`functionalUserRequirements` (列表)**:
        *   **拆分依据 (强制规则)**: 必须根据 `customerRequirementWorkload` 进行拆分。目标是使得每个FUR大致对应 **30 个工作量单位** (允许 +/- 10% 的浮动，即约 27-33 工作量单位)。例如，若 `customerRequirementWorkload` 为 90，则应拆分出大约 3 个 FUR。你需要基于需求内容，合理地将整体需求分解为符合此规模的功能块。
        *   **内容来源**: 基于输入文本中的**需求解决方案**部分。
        *   **描述 (`description`)**:
            *   **语言 (强制规则)**: 力求使用 **口语化、易懂的业务描述语言**，避免专业术语。
            *   **字数 (强制规则)**: 严格控制在 **10 到 40 个汉字** 之间。
            *   **唯一性 (强制规则)**: 在整个JSON输出中，**不允许出现重复**的 `description`。

    *   **`triggeringEvents` (列表，嵌套在FUR内)**:
        *   **识别**: 在对应的 `functionalUserRequirements` 描述中识别出的、**导致数据产生并需要软件处理的事件**。
        *   **描述 (`eventDescription`)**:
            *   **语言 (强制规则)**: 力求使用 **口语化、易懂的业务描述语言**。
            *   **命名格式**: 采用 **`操作 + 对象`** 或 **`对象 + 操作`** 的格式 (例如: "用户提交报销申请", "系统接收银行回执通知")。
            *   **字数 (强制规则)**: 严格控制在 **10 到 40 个汉字** 之间。
            *   **唯一性 (强制规则)**: 在整个JSON输出中，**不允许出现重复**的 `eventDescription`，且**不能与任何 `functionalUserRequirements` 的 `description` 相同**。
            *   **推荐内容**: **多写查询类**的触发事件，少写操作类的触发事件

    *   **`participants`**:
        *   **内容**: 识别该 `triggeringEvents` 的**数据发起者**和主要的**数据接收者**。
        *   **格式 (强制规则)**: **必须为**: `发起者: [类型]\\n接收者：[类型]` （注意换行）。
        *   **规范 (强制规则)**: **发起者和接收者不能相同**，接收者不能是`操作员`、`个人网台`、`小屏`。
        *   **类型选择 (强制规则)**: **[类型]** 必须**严格从以下列表中选择**，不允许任何其他值:
            *   `操作员`: 人类用户通过界面交互。
            *   `个人网台`: 前端系统（Web、接口平台等）。
            *   `订单中心`: 处理订单、服务开通、业务流程相关。
            *   `账管中心`: 处理账务、计费、收费、充值、财务相关。
            *   `产商品中心`: 处理产品、商品、服务目录、终端设备相关。
            *   `后台进程`: 系统自动触发的任务（定时、批量等）。
            *   `基础中心`: 底层数据库结构变更、基础配置、通用平台能力相关。
            *   `小屏`: 前端系统（明确标明是APP、小屏的）。
            *   `短厅`: 短信营业厅（明确标明有短厅、短信营业厅、给用户发生短信指令、回复短信指令的）。

    *   **`functionalProcesses` (列表，嵌套在触发事件内)**:
        *   **识别**: 为响应 `triggeringEvents` 而执行的**一组唯一的、可独立执行的数据移动集合**，代表核心处理逻辑。
        *   **命名 (`processName`)**:
            *   **语言 (强制规则)**: 力求使用 **口语化、易懂的业务描述语言**，不要过于简短，描述得丰富一点。
            *   **字数 (强制规则)**: 严格控制在 **10 到 40 个汉字** 之间。
            *   **格式推荐**: `数据对象 + 操作` 或 `动词 + 名词`。
            *   **推荐动词/操作**: 新增, 创建, 添加, 录入, 审批, 导入, 导出, 上传, 下载, 修改, 编辑, 变更, 删除, 查询, 查看, 展示, 统计, 采集, 汇聚; 办理, 订购, 退订 (业务相关)。
            *   **动词偏好**: 尽量多写**查询类**的功能过程（如查询、查看、展示），少写操作类的（新增、创建、新建、添加、录入、保存）。
            *   **绝对禁止词 (强制规则)**: **加载、解析、初始化、点击按钮、页面、渲染、切换、计算、重置、分页、排序、适配、开发、部署、迁移、安装、存储、缓存、校验、验证、是否、判断、缓存、组装报文、构建报文**。
            *   **唯一性 (强制规则)**: 在整个JSON输出中，**不允许出现重复**的 `processName`。
        *   **禁止内容 (强制规则)**:
            *   **禁止**将“日志记录/记录xxx日志”作为独立功能过程。
        *   **合并处理(强制规则)**: **禁止**将本质相同、仅参数（如文件名、类型码）不同的流程拆分为多个功能过程。必须将它们**合并**为一个概括性的功能过程。例如，“处理A文件入库”和“处理B文件入库”应合并为“处理文件数据入库”。
        *   **推荐内容**: **多写查询类的功能过程**，少写操作类的功能过程
4.  **总体数量约束 (强制规则)**:
    *   **功能过程总数**: 整个需求分析输出的**所有 `functionalProcesses` 的总数量**，应约等于 **`customerRequirementWorkload` 除以 3** 的结果 (可以有5%的上下浮动，例如90个工作量单位，可以包含的功能过程数量是28-32之间)。你需要**在规划和拆分功能过程时，有意识地控制总量**以满足此约束。

5.  **关系理解**:
    *   客户需求通过工作量估算，影响功能用户需求、功能过程的拆分数量。
    *   功能用户需求分解为具体的任务描述，其中包含一个或多个触发事件。
    *   每个触发事件由特定的参与者发起/涉及，并启动一个或多个功能过程。
    *   功能过程是满足触发事件的核心处理步骤，其命名和内容受严格约束。
    *   所有功能过程的总数与整体工作量相关联。

# 输入

用户将提供一段描述软件需求的文本。

# 输出要求

严格按照上述JSON结构和所有详细规则（包括拆分逻辑、字数限制、命名规范、禁用词、唯一性、合并处理、总量控制等），输出分析结果。确保所有字段值都基于输入文本进行分析和提炼，并符合COSMIC原则和用户指定的约束。JSON字段名为英文，值为中文（`customerRequirementWorkload`除外，其值为整数）。**任何不符合上述强制规则的输出都是不可接受的。**
"""

# --- Perform the split ---
# Using a slightly more specific description
description ='你是一位精通COSMIC功能点度量方法的专家分析师。你的核心任务是根据用户提供的软件需求原始描述（可能包含需求名称、需求背景、详细解决方案等），严格遵循COSMIC方法论的核心原则和用户指定的规则，进行细致的分析和拆分，最终以**精确的JSON格式**输出分析结果，以下描述是根据需求原始描述生成JSON的详细规则（部分），你需要学习，并在以后生成时严格遵守这些规则'
split_results = split_prompt_for_finetuning(prompt_text, max_length=3900, description=description)

# --- Print the results ---
for result_line in split_results:
    print(result_line)

# --- Optional: Print lengths for verification ---
# print("\n--- Chunk Lengths ---")
# for i, chunk in enumerate(split_results):
#     print(f"Chunk {i}: {len(chunk)} characters")

