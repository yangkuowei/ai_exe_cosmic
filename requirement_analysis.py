"""需求分析模块 - 读取需求文档并调用AI进行分析"""
import json
from pathlib import Path
import logging
from typing import Tuple, Any

from ai_common import load_model_config
from langchain_openai_client_v1 import call_ai
from read_file_content import read_file_content, save_content_to_file, read_word_document
from requirement_extraction import empty_validator
from validate_cosmic_table import extract_json_from_text

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import subprocess # Added for running mmdc
import os # Added for potential cleanup

from project_paths import ProjectPaths

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

def analyze_requirements(req_name: str = None):
    """主分析流程
    Args:
        req_name: 需求名称，用于指定要处理的需求文件
    """
    try:
        config = ProjectPaths()
        
        # 1. 读取AI系统提示词
        prompt_path = config.ai_promote / "requirement_analysis.md"
        prompt = read_file_content(str(prompt_path))
        
        # 2. 读取需求文件
        if req_name is None:
            # 处理所有开发人员目录下的需求文件, 排除 template 目录
            dev_dirs = [d for d in config.requirements.iterdir() if d.is_dir() and d.name != 'template']
            doc_files = []
            for dev_dir in dev_dirs:
                logger.debug(f"Scanning directory for requirements: {dev_dir}")
                doc_files.extend(list(dev_dir.glob("*.doc")) + list(dev_dir.glob("*.docx")))
            if not doc_files:
                raise FileNotFoundError(f"需求目录中未找到.doc或.docx文件: {config.requirements}")
        else:
            # 处理指定需求文件（格式为"开发人员/需求名称"）
            if "/" not in req_name:
                raise ValueError("req_name格式应为'开发人员/需求名称'")
                
            dev_name, req_base = req_name.split("/", 1)
            dev_dir = config.requirements / dev_name
            doc_files = [dev_dir / f"{req_base}.doc", dev_dir / f"{req_base}.docx"]
            doc_files = [f for f in doc_files if f.exists()]
            if not doc_files:
                raise FileNotFoundError(f"未找到指定需求文件: {req_name}")
        
        # 3. 处理需求文件
        for request_file in doc_files:
            dev_name = request_file.parent.name
            output_path = config.output / dev_name / request_file.stem
            raw_file = output_path / f"{ProjectPaths.REQUIREMENT_PREFIX}{request_file.stem}.json"
            
            # 检查是否已处理过
            if raw_file.exists():
                logger.info(f"跳过已处理的需求文件: {request_file.name}")
                continue
                
            logger.info(f"开始处理需求文件: {request_file.name}")
            
            # 读取需求内容
            content = read_word_document(str(request_file))
            
            # 调用AI进行分析
            json_data = call_ai(
                ai_prompt=prompt,
                requirement_content=content,
                extractor=extract_json_from_text,
                validator=requirement_analysis_validator,
                max_chat_count=3,
                config=load_model_config()
            )
            
            # 预处理并保存结果
            output_path = config.output / dev_name / request_file.stem
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 原始文件路径
            raw_file = output_path / f"{ProjectPaths.REQUIREMENT_PREFIX}{request_file.stem}.json"
            
            # 1. 保存原始结果
            save_content_to_file(
                file_name=raw_file.name,
                output_dir=str(output_path),
                content=json_data,
                content_type="json"
            )
            
            # 2. 转换为业务需求文本
            converter_prompt_path = config.ai_promote / "json_onverter_requirements.md"
            converter_prompt = read_file_content(str(converter_prompt_path))
            
            business_text = call_ai(
                ai_prompt=converter_prompt,
                requirement_content=json_data,
                extractor=extract_markdown_from_text,
                validator=empty_validator,
                max_chat_count=1,
                config=load_model_config()
            )
            
            save_content_to_file(
                file_name=f"business_{raw_file.name.replace('.json','.txt')}",
                output_dir=str(output_path),
                content=business_text,
                content_type="text"
            )
            
            # 3. 预处理(添加tableRows)
            from preprocessor import process_json_file
            processed_file = output_path / f"processed_{raw_file.name}"
            process_json_file(raw_file, processed_file)
            
            # 3. 拆分JSON
            from splitter import split_json_file
            split_files = split_json_file(processed_file, output_path)
            
            logger.info(f"需求分析结果已处理完成，生成{len(split_files)}个子文件")

            # --- 4. 生成需求描述 ---
            logger.info(f"开始生成需求描述: {request_file.name}")
            try:
                # 1. 读取AI系统提示词
                desc_prompt_path = config.ai_promote / "create_requirement_description.md"
                desc_prompt = read_file_content(str(desc_prompt_path))

                # 2. 调用AI生成描述 (使用原始文档内容 content)
                # Assuming the AI output for description is JSON
                req_description_json = call_ai(
                    ai_prompt=desc_prompt,
                    requirement_content=content, # Use original document content
                    extractor=extract_json_from_text, # Assuming description is returned as JSON
                    validator=empty_validator, # Use empty validator if no specific checks needed
                    max_chat_count=3, # As per example
                    config=load_model_config()
                )

                # 3. 保存需求描述JSON文件
                desc_file_name = f"req_description_{request_file.stem}.json"
                save_content_to_file(
                    file_name=desc_file_name,
                    output_dir=str(output_path),
                    content=req_description_json,
                    content_type="json"
                )
                logger.info(f"需求描述文件已生成: {output_path / desc_file_name}")

            except FileNotFoundError as fnf_err:
                 logger.error(f"生成需求描述失败: 无法找到提示词文件 {desc_prompt_path} - {fnf_err}")
            except Exception as desc_err:
                logger.error(f"生成需求描述过程中出错: {desc_err}", exc_info=True)
            # --- End 生成需求描述 ---

            # --- 5. 生成系统架构图 ---
            logger.info(f"开始生成系统架构图: {request_file.name}")
            desc_json_path = output_path / desc_file_name # Path to the file saved in step 4
            mermaid_script = None
            if desc_json_path.exists():
                try:
                    with open(desc_json_path, 'r', encoding='utf-8') as f:
                        desc_data = json.load(f)
                    # Safely extract the mermaid script
                    diagram_info = desc_data.get('functional_architecture_diagram', {})
                    if diagram_info: # Check if the key exists and is not None
                         mermaid_script = diagram_info.get('sequence_diagram_mermaid')
                    
                    if not mermaid_script:
                         logger.warning(f"在 {desc_json_path} 中未找到有效的 Mermaid 脚本 (functional_architecture_diagram.sequence_diagram_mermaid)")

                except json.JSONDecodeError as json_err:
                    logger.error(f"解析需求描述 JSON 文件失败 {desc_json_path}: {json_err}")
                except Exception as read_err:
                    logger.error(f"读取或解析需求描述 JSON 文件时出错 {desc_json_path}: {read_err}", exc_info=True)
            else:
                logger.warning(f"无法生成架构图，因为需求描述文件不存在: {desc_json_path}")

            if mermaid_script:
                mmd_file_path = output_path / "diagram.mmd"
                png_file_path = output_path / f"{request_file.stem}_architecture_diagram.png" # Changed output name
                
                try:
                    # Clean the script: remove potential markdown fences
                    cleaned_script = mermaid_script.strip()
                    if cleaned_script.startswith("```mermaid"):
                        cleaned_script = cleaned_script[len("```mermaid"):].strip()
                    if cleaned_script.endswith("```"):
                         cleaned_script = cleaned_script[:-len("```")].strip()

                    # 2. Save cleaned mermaid script to .mmd file
                    with open(mmd_file_path, 'w', encoding='utf-8') as f_mmd:
                        f_mmd.write(cleaned_script)
                    logger.info(f"清理后的 Mermaid 脚本已保存到: {mmd_file_path}")

                    # 3. Execute mmdc command
                    # Use absolute paths for input/output to be safe, or cd into the directory
                    # Using cd approach here
                    command = f'cd "{output_path.resolve()}" && mmdc -i "{mmd_file_path.name}" -o "{png_file_path.name}" -s 3'
                    logger.info(f"执行命令: {command}")
                    
                    # Use shell=True carefully, ensure paths are quoted
                    # Specify encoding='utf-8' to handle potential non-default characters in output
                    result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', check=False) # check=False to handle errors manually

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
                    # Clean up temporary .mmd file
                    if mmd_file_path.exists():
                        try:
                            os.remove(mmd_file_path)
                            logger.debug(f"已删除临时文件: {mmd_file_path}")
                        except OSError as del_err:
                            logger.warning(f"删除临时文件失败 {mmd_file_path}: {del_err}")
            # --- End 生成系统架构图 ---


    except Exception as e:
        logger.error(f"需求分析主流程失败: {str(e)}") # Updated error message scope
        raise
