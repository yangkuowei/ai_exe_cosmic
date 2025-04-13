"""需求分析模块 - 读取需求文档并调用AI进行分析"""
import json
from pathlib import Path
import logging
from typing import Tuple, Any, List, Optional
import subprocess
import os

from ai_common import load_model_config
# from create_req_word import generate_word_document # 移至 post_processor
from langchain_openai_client_v1 import call_ai
from read_file_content import read_file_content, save_content_to_file, read_word_document
from requirement_extraction import empty_validator
from validate_cosmic_table import extract_json_from_text
from project_paths import ProjectPaths
# 如果辅助函数中使用了其他模块的功能，在此导入
from preprocessor import process_json_file
from splitter import split_json_file


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# --- 上下文管理 ---

class AnalysisContext:
    """管理单个需求文档分析流程的状态和产物"""
    def __init__(self, request_file: Path, config: ProjectPaths, model_config: dict):
        self.request_file = request_file
        self.config = config
        self.model_config = model_config

        if "/" not in request_file.parent.name and request_file.parent.name != config.requirements.name:
             # Assuming parent dir is dev_name if it's directly under requirements
             self.dev_name = request_file.parent.name
        elif request_file.parent.parent == config.requirements:
             # Handles cases like requirements/dev_name/file.docx
             self.dev_name = request_file.parent.name
        else:
             # Fallback or default if structure is different
             # This might need adjustment based on actual expected structures
             logger.warning(f"无法明确解析开发者名称，将使用 'unknown' : {request_file}")
             self.dev_name = "unknown" # Or handle error

        self.request_stem = request_file.stem
        self.output_path = self.config.output / self.dev_name / self.request_stem
        self.output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"为需求 '{self.request_stem}' 设置输出目录: {self.output_path}")

        self.original_content: Optional[str] = None
        self.raw_analysis_file: Optional[Path] = None
        self.business_text_file: Optional[Path] = None
        self.processed_json_file: Optional[Path] = None
        self.split_json_files: List[Path] = []
        self.description_json_file: Optional[Path] = None
        self.architecture_diagram_file: Optional[Path] = None
        self.final_word_file: Optional[Path] = None
        self.analysis_prompt: Optional[str] = None # Store prompt used

        self._read_original_content()
        self._load_analysis_prompt()

    def _read_original_content(self):
        """读取原始需求文档内容"""
        try:
            # Ensure read_word_document handles potential errors gracefully
            self.original_content = read_word_document(str(self.request_file))
            if self.original_content is None or not self.original_content.strip():
                 logger.warning(f"读取到的原始需求文件内容为空或读取失败: {self.request_file.name}")
                 # Decide handling: raise error, or allow process to continue/fail later?
                 # For now, log warning and content remains None or empty
            else:
                 logger.info(f"成功读取原始需求文件内容: {self.request_file.name}")
        except Exception as e:
            logger.error(f"读取原始需求文件时发生严重错误 {self.request_file}: {e}", exc_info=True)
            self.original_content = None # Ensure it's None on error
            # Optionally re-raise or handle differently

    def _load_analysis_prompt(self):
        """加载主分析提示词"""
        try:
            # Use constant for prompt filename
            prompt_path = self.config.ai_promote / self.config.REQ_ANALYSIS_PROMPT_FILENAME
            self.analysis_prompt = read_file_content(str(prompt_path))
            logger.debug("主分析提示词加载成功。")
        except Exception as e:
            logger.error(f"加载主分析提示词失败 {prompt_path}: {e}", exc_info=True)
            self.analysis_prompt = None # Ensure None on error

    # --- 产物路径获取方法 (Using constants from config) ---
    # Removed get_path as specific methods are clearer now

    def get_raw_analysis_path(self) -> Path:
        """获取原始分析JSON文件的预期路径"""
        return self.output_path / f"{self.config.RAW_ANALYSIS_PREFIX}{self.request_stem}{self.config.RAW_ANALYSIS_SUFFIX}"

    def get_business_text_path(self) -> Path:
        """获取业务需求文本文件的预期路径"""
        # Construct name based on prefix and stem, then replace suffix
        raw_name_part = f"{self.config.RAW_ANALYSIS_PREFIX}{self.request_stem}" # Reconstruct the part without suffix
        return self.output_path / f"{self.config.BUSINESS_TEXT_PREFIX}{raw_name_part}{self.config.BUSINESS_TEXT_SUFFIX}"

    def get_processed_json_path(self) -> Path:
        """获取预处理后JSON文件的预期路径"""
        raw_filename = self.get_raw_analysis_path().name
        return self.output_path / f"{self.config.PROCESSED_JSON_PREFIX}{raw_filename}"

    def get_description_json_path(self) -> Path:
        """获取需求描述JSON文件的预期路径"""
        return self.output_path / f"{self.config.REQ_DESC_PREFIX}{self.request_stem}{self.config.REQ_DESC_SUFFIX}"

    def get_architecture_diagram_path(self) -> Path:
        """获取架构图PNG文件的预期路径"""
        return self.output_path / f"{self.request_stem}{self.config.ARCH_DIAGRAM_SUFFIX}"

    def get_final_word_path(self) -> Path:
        """获取最终Word文档的预期路径"""
        return self.output_path / f"{self.request_stem}{self.config.FINAL_WORD_SUFFIX}"

    def get_word_template_path(self) -> Path:
        """获取Word模板文件的路径"""
        return self.config.template_dir / self.config.WORD_TEMPLATE_FILENAME

    def check_if_processed(self) -> bool:
        """检查是否已处理过（基于原始分析文件是否存在） - Retained for potential use but not used in main loop"""
        path_to_check = self.get_raw_analysis_path()
        exists = path_to_check.exists()
        logger.debug(f"检查文件是否存在 '{path_to_check}': {exists}")
        return exists


# --- 辅助函数 (通用工具) ---

def extract_markdown_from_text(text: str) -> str:
    """从文本中提取markdown格式内容 (保持不变)"""
    # 查找markdown代码块
    start = text.find('```markdown')
    # ... (rest of the function remains the same) ...
    if start == -1:
        start = text.find('```')
        if start == -1:
            return text.strip()

    start = text.find('\n', start) + 1
    end = text.find('```', start)
    if end == -1:
        return text[start:].strip()

    return text[start:end].strip()

def requirement_analysis_validator(data: Any) -> Tuple[bool, str]:
    """校验需求分析结果 (保持不变)"""
    # ... (function remains the same) ...
    try:
        if isinstance(data, str):
            data = json.loads(data)
        if 'functionalPoints' in data:
            for fp in data['functionalPoints']:
                if 'initiator' in fp and 'receiver' in fp:
                    if fp['initiator'] == fp['receiver']:
                        return False, f"功能用户发起者和接收者不能相同: {fp['initiator']}"
        return True, ""
    except Exception as e:
        return False, f"校验失败: {str(e)}"

def _find_requirement_files(config: ProjectPaths, req_name: Optional[str] = None) -> List[Path]:
    """查找需求文档文件 (.doc, .docx) (保持不变)"""
    # ... (function remains the same) ...
    doc_files = []
    if req_name is None:
        dev_dirs = [d for d in config.requirements.iterdir() if d.is_dir() and d.name != 'template']
        for dev_dir in dev_dirs:
            logger.debug(f"扫描目录查找需求文件: {dev_dir}")
            doc_files.extend(list(dev_dir.glob("*.doc")) + list(dev_dir.glob("*.docx")))
    else:
        if "/" not in req_name:
             # Try to find based on stem only if no slash
             found = list(config.requirements.rglob(f"{req_name}.doc")) + \
                     list(config.requirements.rglob(f"{req_name}.docx"))
             if not found:
                 raise ValueError("req_name 如果不包含'/'，则必须是项目中唯一的需求文件名（不含扩展名）")
             elif len(found) > 1:
                 logger.warning(f"找到多个同名需求文件，将使用第一个: {found}")
             doc_files = [found[0]] # Take the first one found
        else:
             dev_name, req_base = req_name.split("/", 1)
             dev_dir = config.requirements / dev_name
             potential_files = [dev_dir / f"{req_base}.doc", dev_dir / f"{req_base}.docx"]
             doc_files = [f for f in potential_files if f.exists()]

    if not doc_files:
        if req_name:
            raise FileNotFoundError(f"未找到指定需求文件或匹配模式: {req_name}")
        else:
            raise FileNotFoundError(f"需求目录中未找到.doc或.docx文件: {config.requirements}")
    logger.info(f"找到 {len(doc_files)} 个待处理的需求文件。")
    return doc_files


# --- 处理步骤函数 (使用 Context) ---

def _run_and_save_initial_analysis(context: AnalysisContext) -> bool:
    """步骤 1: 运行初步AI分析并将结果保存到原始JSON文件。如果文件已存在则跳过。"""
    expected_path = context.get_raw_analysis_path()
    if expected_path.exists():
        logger.info(f"步骤 1 跳过：原始分析文件已存在: {expected_path.name}")
        context.raw_analysis_file = expected_path # 确保上下文有路径
        return True

    if not context.original_content or not context.analysis_prompt:
        logger.error(f"步骤 1 失败：无法进行初步分析，缺少原始文档内容或分析提示词 for {context.request_stem}")
        return False

    logger.info(f"步骤 1: 开始对 '{context.request_stem}' 进行初步AI分析...")
    try:
        json_data = call_ai(
            ai_prompt=context.analysis_prompt,
            requirement_content=context.original_content,
            extractor=extract_json_from_text,
            validator=requirement_analysis_validator,
            max_chat_count=3,
            config=context.model_config
        )
        if not json_data:
             logger.error(f"步骤 1 失败：初步AI分析未能返回有效JSON数据 for {context.request_stem}")
             return False

        logger.info(f"初步AI分析完成 for {context.request_stem}。")

        # 保存原始分析结果
        # expected_path 已在函数开始处获取
        save_content_to_file(
            file_name=expected_path.name,
            output_dir=str(context.output_path),
            content=json_data,
            content_type="json"
        )
        logger.info(f"原始分析结果已保存: {expected_path}")
        context.raw_analysis_file = expected_path # 更新上下文
        return True

    except Exception as e:
        logger.error(f"步骤 1 (初步AI分析或保存) 出错 for {context.request_stem}: {e}", exc_info=True)
        return False

def _convert_and_save_business_text(context: AnalysisContext) -> bool:
    """步骤 2: 读取原始分析JSON，调用AI生成业务文本，并保存结果。如果文件已存在则跳过。"""
    expected_path = context.get_business_text_path()
    if expected_path.exists():
        logger.info(f"步骤 2 跳过：业务需求文本文件已存在: {expected_path.name}")
        context.business_text_file = expected_path # 确保上下文有路径
        return True

    # 检查输入依赖（原始分析文件）
    if not context.raw_analysis_file or not context.raw_analysis_file.exists():
        # 这个检查现在很重要，因为步骤1可能被跳过但设置了context.raw_analysis_file
        logger.error(f"步骤 2 失败：无法生成业务文本，依赖的原始分析文件不存在或未在上下文中设置: {context.get_raw_analysis_path()}")
        return False

    logger.info(f"步骤 2: 开始将JSON文件 {context.raw_analysis_file.name} 转换为业务需求文本...")
    try:
        with open(context.raw_analysis_file, 'r', encoding='utf-8') as f:
            json_content = f.read()
    except Exception as e:
        logger.error(f"步骤 2 失败：读取原始JSON文件失败 {context.raw_analysis_file}: {e}")
        return False

    try:
        # Use constant for prompt filename
        converter_prompt_path = context.config.ai_promote / context.config.JSON_CONVERTER_PROMPT_FILENAME
        converter_prompt = read_file_content(str(converter_prompt_path))
        if not converter_prompt:
             logger.error(f"步骤 2 失败：无法加载转换提示词 {converter_prompt_path}")
             return False

        business_text = call_ai(
            ai_prompt=converter_prompt,
            requirement_content=json_content,
            extractor=extract_markdown_from_text,
            validator=empty_validator,
            max_chat_count=1,
            config=context.model_config
        )
        if not business_text:
             logger.warning(f"步骤 2: AI未能生成业务文本 for {context.request_stem}。将保存空文件。")
             business_text = "" # Ensure empty string is saved if AI returns None/empty

        logger.info(f"业务需求文本转换完成 for {context.request_stem}。")

        # 构建保存路径并保存
        # expected_path 已在函数开始处获取
        save_content_to_file(
            file_name=expected_path.name,
            output_dir=str(context.output_path),
            content=business_text,
            content_type="text"
        )
        logger.info(f"业务需求文本已保存: {expected_path}")

        # 更新上下文
        context.business_text_file = expected_path
        return True

    except Exception as e:
        logger.error(f"步骤 2 (生成或保存业务文本) 时出错 for {context.request_stem}: {e}", exc_info=True)
        return False

def _preprocess_and_split_json(context: AnalysisContext) -> bool:
    """步骤 3: 预处理（添加tableRows）并拆分原始分析JSON文件。如果预处理文件已存在则跳过。"""
    expected_processed_path = context.get_processed_json_path()
    # Check if the *processed* file exists as the primary indicator for skipping
    if expected_processed_path.exists():
        logger.info(f"步骤 3 跳过：预处理后的JSON文件已存在: {expected_processed_path.name}")
        context.processed_json_file = expected_processed_path # Update context with existing processed file
        # Attempt to find existing split files based on pattern, or mark as empty
        # This part depends on how critical split files are downstream
        # For now, let's just log and not populate split_files if skipped
        logger.warning(f"步骤 3: 预处理文件已存在，拆分步骤也将跳过。如果需要拆分文件，请手动删除 {expected_processed_path.name}")
        context.split_json_files = [] # Mark as empty since we skipped splitting
        return True

    # Check input dependency
    if not context.raw_analysis_file or not context.raw_analysis_file.exists():
        logger.error(f"步骤 3 失败：无法预处理和拆分，依赖的原始分析文件不存在: {context.get_raw_analysis_path()}")
        return False

    logger.info(f"步骤 3: 开始预处理和拆分JSON文件 {context.raw_analysis_file.name}...")
    try:
        # 预处理
        # expected_processed_path is already defined
        process_json_file(context.raw_analysis_file, expected_processed_path)
        logger.debug(f"JSON预处理完成: {expected_processed_path}")
        context.processed_json_file = expected_processed_path # Update context

        # 拆分
        split_files = split_json_file(expected_processed_path, context.output_path)
        logger.info(f"JSON拆分完成，生成{len(split_files)}个子文件。")
        context.split_json_files = split_files # Update context
        return True

    except Exception as e:
        logger.error(f"步骤 3 (预处理或拆分JSON) 时出错 for {context.request_stem}: {e}", exc_info=True)
        return False


def _generate_and_save_requirement_description(context: AnalysisContext) -> bool:
    """步骤 4: 使用AI根据原始文档内容生成需求描述JSON并保存。如果文件已存在则跳过。"""
    expected_path = context.get_description_json_path()
    if expected_path.exists():
        logger.info(f"步骤 4 跳过：需求描述JSON文件已存在: {expected_path.name}")
        context.description_json_file = expected_path # 确保上下文有路径
        return True

    if not context.original_content:
        logger.error(f"步骤 4 失败：无法生成需求描述，缺少原始文档内容 for {context.request_stem}")
        return False

    logger.info(f"步骤 4: 开始为 '{context.request_stem}' 生成需求描述...")
    try:
        # Use constant for prompt filename
        desc_prompt_path = context.config.ai_promote / context.config.REQ_DESC_PROMPT_FILENAME
        desc_prompt = read_file_content(str(desc_prompt_path))
        if not desc_prompt:
             logger.error(f"步骤 4 失败：无法加载需求描述提示词 {desc_prompt_path}")
             return False

        req_description_json = call_ai(
            ai_prompt=desc_prompt,
            requirement_content=context.original_content,
            extractor=extract_json_from_text,
            validator=empty_validator, # Consider if a specific validator is needed
            max_chat_count=3,
            config=context.model_config
        )
        if not req_description_json:
             logger.error(f"步骤 4 失败：AI未能生成需求描述JSON for {context.request_stem}")
             return False

        logger.info(f"需求描述生成成功 for {context.request_stem}。")

        # 保存需求描述
        # expected_path 已在函数开始处获取
        save_content_to_file(
            file_name=expected_path.name,
            output_dir=str(context.output_path),
            content=req_description_json,
            content_type="json"
        )
        logger.info(f"需求描述文件已保存: {expected_path}")
        context.description_json_file = expected_path # 更新上下文
        return True

    except FileNotFoundError as fnf_err:
        # Use constant in error message
        logger.error(f"步骤 4 失败：生成需求描述失败，无法找到提示词文件 {context.config.ai_promote / context.config.REQ_DESC_PROMPT_FILENAME} - {fnf_err}")
        return False
    except Exception as desc_err:
        logger.error(f"步骤 4 (生成或保存需求描述) 过程中出错 for {context.request_stem}: {desc_err}", exc_info=True)
        return False


def _generate_architecture_diagram(context: AnalysisContext) -> bool:
    """步骤 5: 从需求描述JSON中的Mermaid脚本生成架构图PNG。如果文件已存在则跳过。"""
    expected_path = context.get_architecture_diagram_path()
    if expected_path.exists():
        logger.info(f"步骤 5 跳过：架构图文件已存在: {expected_path.name}")
        context.architecture_diagram_file = expected_path # 确保上下文有路径
        return True

    # 检查输入依赖（需求描述文件）
    if not context.description_json_file or not context.description_json_file.exists():
        logger.warning(f"步骤 5 跳过：无法生成架构图，依赖的需求描述文件不存在: {context.get_description_json_path()}")
        # This is not necessarily a failure of the overall process if description generation failed/skipped
        return True # Allow process to continue

    logger.info(f"步骤 5: 开始为 '{context.request_stem}' 生成系统架构图...")
    mermaid_script = None

    # 1. 提取Mermaid脚本
    # (Extraction logic remains the same)
    try:
        with open(context.description_json_file, 'r', encoding='utf-8') as f:
            desc_data = json.load(f)
        diagram_info = desc_data.get('functional_architecture_diagram', {})
        mermaid_script = diagram_info.get('sequence_diagram_mermaid') if diagram_info else None

        if not mermaid_script:
            logger.warning(f"步骤 5: 在 {context.description_json_file.name} 中未找到有效的 Mermaid 脚本。跳过图表生成。")
            return True

    except json.JSONDecodeError as json_err:
        logger.error(f"步骤 5 失败：解析需求描述 JSON 文件失败 {context.description_json_file}: {json_err}")
        return False
    except Exception as read_err:
        logger.error(f"步骤 5 失败：读取或解析需求描述 JSON 文件时出错 {context.description_json_file}: {read_err}", exc_info=True)
        return False

    # 2. 准备并运行 mmdc 命令
    # Use constant for temp mermaid filename
    mmd_file_path = context.output_path / context.config.TEMP_MERMAID_FILENAME
    # expected_path is already defined
    png_file_path = expected_path

    try:
        # 清理脚本
        # (Cleaning logic remains the same)
        cleaned_script = mermaid_script.strip()
        if cleaned_script.startswith("```mermaid"):
            cleaned_script = cleaned_script[len("```mermaid"):].strip()
        if cleaned_script.endswith("```"):
            cleaned_script = cleaned_script[:-len("```")].strip()

        if not cleaned_script:
             logger.warning(f"步骤 5: Mermaid 脚本在清理后为空 for {context.request_stem}。跳过图表生成。")
             return True

        # 保存清理后的脚本
        # (Saving logic remains the same)
        with open(mmd_file_path, 'w', encoding='utf-8') as f_mmd:
            f_mmd.write(cleaned_script)
        logger.debug(f"清理后的 Mermaid 脚本已保存到: {mmd_file_path}")

        # 执行 mmdc
        # (Execution logic remains the same)
        command = f'cd "{context.output_path.resolve()}" && mmdc -i "{mmd_file_path.name}" -o "{png_file_path.name}" -s 3'
        logger.info(f"执行命令: {command}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', check=False)

        if result.returncode == 0:
            logger.info(f"系统架构图已成功生成: {png_file_path}")
            context.architecture_diagram_file = png_file_path # 更新上下文
            return True
        else:
            logger.error(f"步骤 5 失败：执行 mmdc 命令失败 (返回码: {result.returncode}) for {context.request_stem}")
            logger.error(f"mmdc stderr: {result.stderr}")
            logger.error(f"mmdc stdout: {result.stdout}")
            return False

    except FileNotFoundError:
        logger.error("步骤 5 失败：执行 mmdc 命令失败: 'mmdc' 命令未找到。请确保 Mermaid CLI 已安装并添加到系统 PATH。")
        return False
    except Exception as cmd_err:
        logger.error(f"步骤 5 (生成架构图) 过程中出错 for {context.request_stem}: {cmd_err}", exc_info=True)
        return False
    finally:
        # 清理临时 .mmd 文件
        # (Cleanup logic remains the same)
        if mmd_file_path.exists():
            try:
                os.remove(mmd_file_path)
                logger.debug(f"已删除临时文件: {mmd_file_path}")
            except OSError as del_err:
                 logger.warning(f"删除临时文件失败 {mmd_file_path}: {del_err}")


# --- 主流程编排函数 (使用 Context) ---

def analyze_requirements(req_name: Optional[str] = None):
    """主分析流程编排器。使用 AnalysisContext 管理每个文档的处理流程，并独立检查各步骤产物。"""
    # (Initialization logic remains similar)
    logger.info("--- 开始需求分析流程 ---")
    processed_count = 0
    failed_count = 0
    skipped_files = 0 # Renamed for clarity
    step_skips = {} # To count skips per step

    try:
        config = ProjectPaths()
        model_config = load_model_config()
        doc_files = _find_requirement_files(config, req_name)
        logger.info(f"共找到 {len(doc_files)} 个需求文件待处理。")
    except FileNotFoundError as e:
         logger.error(f"初始化错误：无法找到需求文件或目录: {e}")
         return
    except Exception as e:
        logger.error(f"初始化过程中发生严重错误: {e}", exc_info=True)
        return

    # --- 处理每个文件 ---
    for request_file in doc_files:
        logger.info(f"\n--- 开始处理文件: {request_file.relative_to(config.requirements)} ---")
        context = None
        file_failed = False # Track if any step failed for this file
        try:
            # 1. 创建并初始化上下文
            context = AnalysisContext(request_file, config, model_config)

            # 2. 检查初始必要输入 (原始内容和主提示词)
            if context.original_content is None:
                 logger.error(f"处理失败，无法读取原始文件内容: {request_file.name}")
                 failed_count += 1
                 continue
            if context.analysis_prompt is None:
                 logger.error(f"处理失败，无法加载主分析提示词 for {request_file.name}")
                 failed_count += 1
                 continue

            # 3. 按顺序执行步骤，现在每个步骤内部处理跳过逻辑
            # We check the return value to see if a step *failed*, not if it was skipped.
            # Skipped steps return True.
            steps_to_run = [
                _run_and_save_initial_analysis,
                _convert_and_save_business_text,
                _preprocess_and_split_json, # Note: Failure here might not be critical
                _generate_and_save_requirement_description,
                _generate_architecture_diagram # Note: Failure here might not be critical
                # _generate_final_word_document # 移至 post_processor
            ]

            for i, step_func in enumerate(steps_to_run, 1):
                step_name = step_func.__name__ # Get function name for logging
                logger.debug(f"--- Executing Step {i}: {step_name} ---")
                step_success = step_func(context)

                if not step_success:
                    logger.error(f"步骤 {i} ({step_name}) 执行失败 for {context.request_stem}。")
                    # Decide if failure is critical for the *entire file*
                    # For now, let's consider any step failure as a file failure,
                    # except maybe optional ones like diagram generation if needed.
                    # Let's make all steps critical for now.
                    file_failed = True
                    break # Stop processing this file if a critical step fails

            # 4. 记录文件处理结果
            if file_failed:
                logger.error(f"--- 文件处理因步骤失败而中止: {request_file.name} ---")
                failed_count += 1
            else:
                logger.info(f"--- 文件处理完成 (可能部分步骤被跳过): {request_file.name} ---")
                processed_count += 1 # Count as processed even if steps were skipped

        except Exception as file_proc_err:
            logger.error(f"处理文件 {request_file.name} 时发生未捕获的严重错误: {file_proc_err}", exc_info=True)
            failed_count += 1
            # Continue to the next file

    logger.info(f"\n--- 需求分析流程结束 ---")
    # TODO: Add detailed skip counts per step if needed by iterating through step_skips
    logger.info(f"处理总结: 完成 {processed_count}, 失败 {failed_count}") # Removed skipped_files as it's less meaningful now


# --- 运行入口 ---
# (Entry point remains the same)
if __name__ == "__main__":
    #analyze_requirements() # 处理所有
    # Example: Process a specific requirement
    analyze_requirements("梁海祥/需求规格说明书_202405111579786_关于实体卡工作号绑定、解绑结果通知优化的需求")
