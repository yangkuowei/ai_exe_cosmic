"""需求分析模块 - 读取需求文档并调用AI进行分析"""
import json
from pathlib import Path
import logging
from typing import Tuple, Any, List, Optional
import subprocess
import os

from ai_common import load_model_config
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


# --- 辅助函数 ---

def extract_markdown_from_text(text: str) -> str:
    """从文本中提取markdown格式内容"""
    # 查找markdown代码块
    start = text.find('```markdown')
    if start == -1:
        start = text.find('```')
        if start == -1:
            return text.strip()  # 如果没有代码块标记，返回整个文本

    start = text.find('\n', start) + 1  # 跳过代码块标记行
    end = text.find('```', start)
    if end == -1:
        return text[start:].strip()  # 如果没有结束标记，返回剩余文本

    return text[start:end].strip()

def requirement_analysis_validator(data: Any) -> Tuple[bool, str]:
    """校验需求分析结果
    校验规则:
    1. 功能用户的发起者和接收者不能相同
    """
    try:
        if isinstance(data, str):
            data = json.loads(data)

        # 检查功能用户
        if 'functionalPoints' in data:
            for fp in data['functionalPoints']:
                if 'initiator' in fp and 'receiver' in fp:
                    if fp['initiator'] == fp['receiver']:
                        return False, f"功能用户发起者和接收者不能相同: {fp['initiator']}"

        return True, ""
    except Exception as e:
        return False, f"校验失败: {str(e)}"

def _find_requirement_files(config: ProjectPaths, req_name: Optional[str] = None) -> List[Path]:
    """查找需求文档文件 (.doc, .docx)"""
    doc_files = []
    if req_name is None:
        # 处理所有开发人员目录下的需求文件, 排除 'template' 目录
        dev_dirs = [d for d in config.requirements.iterdir() if d.is_dir() and d.name != 'template']
        for dev_dir in dev_dirs:
            logger.debug(f"扫描目录查找需求文件: {dev_dir}")
            doc_files.extend(list(dev_dir.glob("*.doc")) + list(dev_dir.glob("*.docx")))
    else:
        # 处理指定的需求文件
        if "/" not in req_name:
            raise ValueError("req_name格式应为'开发人员/需求名称'")

        dev_name, req_base = req_name.split("/", 1)
        dev_dir = config.requirements / dev_name
        potential_files = [dev_dir / f"{req_base}.doc", dev_dir / f"{req_base}.docx"]
        doc_files = [f for f in potential_files if f.exists()]

    if not doc_files:
        if req_name:
            raise FileNotFoundError(f"未找到指定需求文件: {req_name}")
        else:
            raise FileNotFoundError(f"需求目录中未找到.doc或.docx文件: {config.requirements}")

    return doc_files

def _run_initial_ai_analysis(prompt: str, content: str, model_config: dict) -> str:
    """运行初步的AI分析"""
    logger.info("调用AI进行初步分析...")
    json_data = call_ai(
        ai_prompt=prompt,
        requirement_content=content,
        extractor=extract_json_from_text,
        validator=requirement_analysis_validator,
        max_chat_count=3,
        config=model_config
    )
    logger.info("初步AI分析完成。")
    return json_data

def _save_raw_analysis(output_path: Path, request_stem: str, json_data: str) -> Path:
    """保存原始的JSON分析结果"""
    raw_file = output_path / f"{ProjectPaths.REQUIREMENT_PREFIX}{request_stem}.json"
    save_content_to_file(
        file_name=raw_file.name,
        output_dir=str(output_path),
        content=json_data,
        content_type="json"
    )
    logger.info(f"原始分析结果已保存: {raw_file}")
    return raw_file

def _convert_to_business_text(json_data: str, config: ProjectPaths, model_config: dict) -> str:
    """使用AI将JSON分析结果转换为业务文本"""
    logger.info("开始将JSON转换为业务需求文本...")
    converter_prompt_path = config.ai_promote / "json_onverter_requirements.md"
    converter_prompt = read_file_content(str(converter_prompt_path))

    business_text = call_ai(
        ai_prompt=converter_prompt,
        requirement_content=json_data,
        extractor=extract_markdown_from_text,
        validator=empty_validator,
        max_chat_count=1,
        config=model_config
    )
    logger.info("业务需求文本转换完成。")
    return business_text

def _save_business_text(output_path: Path, raw_file_name: str, business_text: str):
    """保存生成的业务文本"""
    business_text_file_name = f"business_{raw_file_name.replace('.json','.txt')}"
    save_content_to_file(
        file_name=business_text_file_name,
        output_dir=str(output_path),
        content=business_text,
        content_type="text"
    )
    logger.info(f"业务需求文本已保存: {output_path / business_text_file_name}")

def _preprocess_and_split_json(raw_file: Path, output_path: Path) -> List[Path]:
    """预处理（添加tableRows）并拆分JSON文件"""
    logger.info("开始预处理和拆分JSON...")
    # 预处理
    processed_file = output_path / f"processed_{raw_file.name}"
    process_json_file(raw_file, processed_file)
    logger.debug(f"JSON预处理完成: {processed_file}")

    # 拆分
    split_files = split_json_file(processed_file, output_path)
    logger.info(f"JSON拆分完成，生成{len(split_files)}个子文件。")
    return split_files

def _generate_requirement_description(content: str, config: ProjectPaths, model_config: dict) -> Optional[str]:
    """使用AI生成需求描述JSON"""
    logger.info("开始生成需求描述...")
    try:
        desc_prompt_path = config.ai_promote / "create_requirement_description.md"
        desc_prompt = read_file_content(str(desc_prompt_path))

        req_description_json = call_ai(
            ai_prompt=desc_prompt,
            requirement_content=content,
            extractor=extract_json_from_text,
            validator=empty_validator,
            max_chat_count=3,
            config=model_config
        )
        logger.info("需求描述生成成功。")
        return req_description_json

    except FileNotFoundError as fnf_err:
        logger.error(f"生成需求描述失败: 无法找到提示词文件 {config.ai_promote / 'create_requirement_description.md'} - {fnf_err}")
        return None
    except Exception as desc_err:
        logger.error(f"生成需求描述过程中出错: {desc_err}", exc_info=True)
        return None

def _save_requirement_description(output_path: Path, request_stem: str, req_description_json: str) -> Path:
    """保存需求描述JSON"""
    desc_file_name = f"req_description_{request_stem}.json"
    desc_file_path = output_path / desc_file_name
    save_content_to_file(
        file_name=desc_file_name,
        output_dir=str(output_path),
        content=req_description_json,
        content_type="json"
    )
    logger.info(f"需求描述文件已保存: {desc_file_path}")
    return desc_file_path

def _generate_architecture_diagram(desc_json_path: Path, output_path: Path, request_stem: str):
    """从描述JSON中的Mermaid脚本生成架构图PNG"""
    logger.info(f"开始生成系统架构图 for {request_stem}...")
    mermaid_script = None

    if not desc_json_path.exists():
        logger.warning(f"无法生成架构图，因为需求描述文件不存在: {desc_json_path}")
        return

    # 1. 提取Mermaid脚本
    try:
        with open(desc_json_path, 'r', encoding='utf-8') as f:
            desc_data = json.load(f)
        diagram_info = desc_data.get('functional_architecture_diagram', {})
        if diagram_info:
            mermaid_script = diagram_info.get('sequence_diagram_mermaid')

        if not mermaid_script:
            logger.warning(f"在 {desc_json_path} 中未找到有效的 Mermaid 脚本 (functional_architecture_diagram.sequence_diagram_mermaid)")
            return # 没有脚本则无法继续

    except json.JSONDecodeError as json_err:
        logger.error(f"解析需求描述 JSON 文件失败 {desc_json_path}: {json_err}")
        return
    except Exception as read_err:
        logger.error(f"读取或解析需求描述 JSON 文件时出错 {desc_json_path}: {read_err}", exc_info=True)
        return

    # 2. 准备并运行 mmdc 命令
    mmd_file_path = output_path / "diagram.mmd"
    png_file_path = output_path / f"{request_stem}_architecture_diagram.png"

    try:
        # 清理脚本：移除潜在的 markdown 代码围栏
        cleaned_script = mermaid_script.strip()
        if cleaned_script.startswith("```mermaid"):
            cleaned_script = cleaned_script[len("```mermaid"):].strip()
        if cleaned_script.endswith("```"):
            cleaned_script = cleaned_script[:-len("```")].strip()

        # 保存清理后的脚本
        with open(mmd_file_path, 'w', encoding='utf-8') as f_mmd:
            f_mmd.write(cleaned_script)
        logger.info(f"清理后的 Mermaid 脚本已保存到: {mmd_file_path}")

        # 执行 mmdc
        command = f'cd "{output_path.resolve()}" && mmdc -i "{mmd_file_path.name}" -o "{png_file_path.name}" -s 3'
        logger.info(f"执行命令: {command}")
        # 明确指定 encoding='utf-8' 来处理可能的非默认字符输出
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', check=False) # check=False 手动处理错误

        if result.returncode == 0:
            logger.info(f"系统架构图已成功生成: {png_file_path}")
        else:
            logger.error(f"执行 mmdc 命令失败 (返回码: {result.returncode})")
            logger.error(f"mmdc stderr: {result.stderr}")
            logger.error(f"mmdc stdout: {result.stdout}")

    except FileNotFoundError:
        logger.error("执行 mmdc 命令失败: 'mmdc' 命令未找到。请确保 Mermaid CLI 已安装并添加到系统 PATH。")
    except Exception as cmd_err:
        logger.error(f"生成架构图过程中出错: {cmd_err}", exc_info=True)
    finally:
        # 清理临时 .mmd 文件
        if mmd_file_path.exists():
            try:
                os.remove(mmd_file_path)
                logger.debug(f"已删除临时文件: {mmd_file_path}")
            except OSError as del_err:
                logger.warning(f"删除临时文件失败 {mmd_file_path}: {del_err}")


# --- 主流程编排函数 ---

def analyze_requirements(req_name: str = None):
    """
    主分析流程编排器。
    读取需求文档，执行AI分析，生成描述、图表和其他产物。
    """
    try:
        config = ProjectPaths()
        model_config = load_model_config() # 加载一次模型配置

        # 加载主分析提示词
        prompt_path = config.ai_promote / "requirement_analysis.md"
        analysis_prompt = read_file_content(str(prompt_path))

        # 查找需求文件
        doc_files = _find_requirement_files(config, req_name)

        # 处理每个文件
        for request_file in doc_files:
            dev_name = request_file.parent.name
            request_stem = request_file.stem
            output_path = config.output / dev_name / request_stem
            output_path.mkdir(parents=True, exist_ok=True) # 确保输出目录存在

            # 检查是否已处理过（使用原始文件作为标记）
            raw_file_check = output_path / f"{ProjectPaths.REQUIREMENT_PREFIX}{request_stem}.json"
            if raw_file_check.exists():
                logger.info(f"跳过已处理的需求文件: {request_file.name}")
                continue

            logger.info(f"开始处理需求文件: {request_file.name}")

            try:
                # 读取内容
                content = read_word_document(str(request_file))

                # 步骤 1: 初步AI分析并保存
                json_data = _run_initial_ai_analysis(analysis_prompt, content, model_config)
                raw_file = _save_raw_analysis(output_path, request_stem, json_data)

                # # 步骤 2: 转换为业务文本并保存
                business_text = _convert_to_business_text(json_data, config, model_config)
                _save_business_text(output_path, raw_file.name, business_text)

                # # 步骤 3: 预处理并拆分JSON
                _preprocess_and_split_json(raw_file, output_path) # split_files 结果目前未在下游使用

                # 步骤 4: 生成并保存需求描述
                req_description_json = _generate_requirement_description(content, config, model_config)
                desc_json_path = None
                if req_description_json:
                    desc_json_path = _save_requirement_description(output_path, request_stem, req_description_json)

                # 步骤 5: 生成架构图（如果描述已保存）
                if desc_json_path:
                    _generate_architecture_diagram(desc_json_path, output_path, request_stem)
                else:
                    logger.warning(f"跳过架构图生成，因为需求描述未能成功生成或保存 for {request_stem}")

                logger.info(f"需求文件处理完成: {request_file.name}")

            except Exception as file_proc_err:
                logger.error(f"处理文件 {request_file.name} 时出错: {file_proc_err}", exc_info=True)
                # 继续处理下一个文件

    except FileNotFoundError as e:
         logger.error(f"初始化错误或文件未找到: {str(e)}")
         # 决定是抛出异常还是仅记录日志
    except Exception as e:
        logger.error(f"需求分析主流程发生严重错误: {str(e)}", exc_info=True)
        # 决定是抛出异常还是仅记录日志

# 运行示例 (如果需要)
if __name__ == "__main__":
    #analyze_requirements() # 处理所有
    analyze_requirements("梁海祥/需求规格说明书_202405111579786_关于实体卡工作号绑定、解绑结果通知优化的需求") # 处理指定需求
