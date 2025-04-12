"""需求处理流程编排器 - 并发处理多个需求，每个需求内部串行"""
import logging
from pathlib import Path
from typing import List
import concurrent.futures # 导入并发库
import os # 导入os模块用于文件删除

from create_cosmic_table import create_cosmic_table
from project_paths import ProjectPaths
from requirement_analysis import analyze_requirements
from create_trigger_events import create_trigger_events
# 导入所需函数
from read_file_content import merge_temp_files, save_content_to_file, read_file_content
# 导入 Excel 处理函数
from exceltool.exceltool import process_excel_files
import re # Import regex for parsing analysis file

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_analysis_file(file_path: Path) -> (str, str):
    """
    Parses the business analysis markdown file to extract targets (需求背景)
    and necessity (需求解决方案) sections, cleaning basic markdown.
    """
    targets = " " # Default value
    necessity = " " # Default value
    logger.debug(f"Attempting to parse analysis file: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # --- Extract Targets (需求背景) ---
        # Find the line starting with '### 需求背景', capture everything after it until the next '---' line (allowing trailing whitespace on separator)
        targets_match = re.search(r"^### 需求背景\s*?\n(.*?)(?=^---\s*$)", content, re.MULTILINE | re.DOTALL)
        if targets_match:
            raw_targets = targets_match.group(1).strip()
            # Clean markdown bold (**text**) -> text
            cleaned_targets = re.sub(r'\*\*(.*?)\*\*', r'\1', raw_targets)
            # Remove potential list markers like '1. ', '* ' etc. at the beginning of lines if needed
            # cleaned_targets = re.sub(r"^\s*[\*\-\d]+\.\s+", "", cleaned_targets, flags=re.MULTILINE) # Optional stricter cleaning
            targets = cleaned_targets.strip()
            logger.debug(f"Extracted Targets: {targets[:100]}...") # Log snippet
        else:
             logger.warning(f"Could not find '### 需求背景' section in {file_path}")


        # --- Extract Necessity (需求解决方案) ---
         # Find the line starting with '### 需求解决方案', capture everything after it until the next '---' line (allowing trailing whitespace on separator)
        necessity_match = re.search(r"^### 需求解决方案\s*?\n(.*?)(?=^---\s*$)", content, re.MULTILINE | re.DOTALL)
        if necessity_match:
            raw_necessity = necessity_match.group(1).strip()
            # Clean markdown bold (**text**) -> text
            cleaned_necessity = re.sub(r'\*\*(.*?)\*\*', r'\1', raw_necessity)
            # cleaned_necessity = re.sub(r"^\s*[\*\-\d]+\.\s+", "", cleaned_necessity, flags=re.MULTILINE) # Optional stricter cleaning
            necessity = cleaned_necessity.strip()
            logger.debug(f"Extracted Necessity: {necessity[:100]}...") # Log snippet
        else:
             logger.warning(f"Could not find '### 需求解决方案' section in {file_path}")


    except FileNotFoundError:
        logger.error(f"Analysis file not found when trying to parse: {file_path}")
    except Exception as e:
        logger.error(f"Error parsing analysis file {file_path}: {e}", exc_info=True)

    return targets, necessity

def get_doc_files(config: ProjectPaths) -> List[Path]:
    """获取所有需求文档文件"""
    doc_files = []
    # 扫描所有开发人员子目录
    for dev_dir in config.requirements.iterdir():
        if dev_dir.is_dir():
            doc_files.extend(list(dev_dir.glob("*.doc")) + list(dev_dir.glob("*.docx")))
    
    if not doc_files:
        raise FileNotFoundError(f"需求目录中未找到.doc或.docx文件: {config.requirements}")
    logger.info(f"发现 {len(doc_files)} 个需求文档待处理。")
    return doc_files

def process_single_requirement(doc_file: Path, config: ProjectPaths):
    """处理单个需求文档"""
    try:
        dev_name = doc_file.parent.name
        req_base = doc_file.stem
        req_name = f"{dev_name}/{req_base}"

        logger.info(f"开始处理需求: {req_name}") # 调整日志位置

        # 1. 需求分析 (串行步骤1)
        logger.info(f"[{req_name}] 阶段 1: 开始需求分析")
        analyze_requirements(req_name)

        # 2. 创建触发事件 (串行步骤2)
        logger.info(f"[{req_name}] 阶段 2: 开始创建触发事件")
        create_trigger_events(req_name)

        # 3. 创建COSMIC表 (串行步骤3)
        logger.info(f"[{req_name}] 阶段 3: 开始创建COSMIC表")
        create_cosmic_table(req_name)

        # 4. 后置处理（串行步骤4） - 合并并删除临时COSMIC表
        logger.info(f"[{req_name}] 阶段 4: 开始后置处理（合并COSMIC表）")
        try:
            # 确定临时文件目录和最终输出文件路径
            # 假设临时文件和最终文件都放在基于 req_name 的输出子目录中
            # 注意：这里的路径结构需要与 create_cosmic_table 和 merge_temp_files 的实际行为匹配
            output_dir_for_req = config.output / dev_name / req_base
            output_dir_for_req.mkdir(parents=True, exist_ok=True) # 确保目录存在
            final_output_file = output_dir_for_req / f"{req_base}_cosmic_merged.md"
            temp_file_pattern = "table_cosmic_*.md"

            merged_content_for_export = None # 用于存储最终要导出的内容

            # 检查最终合并文件是否已存在
            if final_output_file.exists():
                logger.info(f"[{req_name}] 发现已存在的合并文件: {final_output_file}，将直接使用其内容。")
                try:
                    # 读取已存在文件的内容
                    merged_content_for_export = read_file_content(final_output_file)
                    # 可选：清理可能残留的临时文件
                    lingering_temps = list(output_dir_for_req.glob(temp_file_pattern))
                    if lingering_temps:
                        logger.info(f"[{req_name}] 清理残留的临时文件...")
                        deleted_count = 0
                        for temp_file in lingering_temps:
                            try:
                                temp_file.unlink()
                                deleted_count += 1
                            except OSError as e:
                                logger.warning(f"[{req_name}] 删除残留临时文件失败 {temp_file}: {e}")
                        if deleted_count > 0:
                            logger.info(f"[{req_name}] 已清理 {deleted_count} 个残留临时文件。")
                except Exception as read_err:
                    logger.error(f"[{req_name}] 读取已存在的合并文件失败: {read_err}，将尝试重新合并。")
                    # 如果读取失败，merged_content_for_export 保持为 None，会进入下面的合并逻辑

            # 如果最终文件不存在 或 读取失败，则执行合并逻辑
            if merged_content_for_export is None:
                logger.info(f"[{req_name}] 未找到或无法读取合并文件，开始查找并合并临时文件...")
                # 1. 查找所有临时文件
                temp_files_to_merge = sorted(list(output_dir_for_req.glob(temp_file_pattern)))

                if not temp_files_to_merge:
                    logger.warning(f"[{req_name}] 在目录 {output_dir_for_req} 中未找到要合并的临时文件 (匹配模式: {temp_file_pattern})。无法生成合并文件和后续导出。")
                    # merged_content_for_export 保持为 None
                else:
                    logger.info(f"[{req_name}] 找到 {len(temp_files_to_merge)} 个临时文件准备合并。")
                    try:
                        # 2. 调用合并函数 (传入 Path 列表)
                        merged_content_for_export = merge_temp_files(temp_files_to_merge)

                        # 3. 将合并后的内容写入最终文件
                        with open(final_output_file, "w", encoding="utf-8") as f_out:
                            f_out.write(merged_content_for_export)
                        logger.info(f"[{req_name}] COSMIC 表已合并到: {final_output_file}")

                        # 4. 删除临时文件
                        logger.info(f"[{req_name}] 开始删除临时 COSMIC 表文件...")
                        deleted_count = 0
                        for temp_file in temp_files_to_merge: # 使用之前找到的列表
                            try:
                                temp_file.unlink() # 使用 Path.unlink() 删除文件
                                deleted_count += 1
                            except OSError as e:
                                logger.warning(f"[{req_name}] 删除临时文件失败 {temp_file}: {e}")
                        logger.info(f"[{req_name}] 已成功删除 {deleted_count} 个临时文件。")
                    except Exception as merge_err:
                         logger.error(f"[{req_name}] 合并或写入文件过程中出错: {merge_err}")
                         merged_content_for_export = None # 合并失败，无法导出

            # 只有在成功获取到合并内容后才进行导出
            if merged_content_for_export is not None:
                # 5. 使用合并后的 Markdown 内容生成 Excel 文件
                logger.info(f"[{req_name}] 开始将合并后的 Markdown 转换为 Excel 文件...")
                save_content_to_file(
                    file_name=req_base, # 使用需求基础名作为文件名
                    output_dir=output_dir_for_req,
                    content=merged_content_for_export, # 使用获取到的内容
                    content_type="xlsx"
                )
                logger.info(f"[{req_name}] Excel 文件已生成: {output_dir_for_req / (req_base + '.xlsx')}")

                # 6. 使用生成的 Excel 文件生成 Word 文件
                logger.info(f"[{req_name}] 开始将 Excel 文件转换为 Word 文件...")
                save_content_to_file(
                    file_name=req_base, # 使用需求基础名作为文件名
                    output_dir=output_dir_for_req,
                    content=merged_content_for_export, # 使用获取到的内容
                    content_type="docx"
                )
                logger.info(f"[{req_name}] Word 文件已生成: {output_dir_for_req / (req_base + '.docx')}")

                # 7. 使用生成的 Excel 文件填充模板 Excel
                logger.info(f"[{req_name}] 阶段 7: 开始使用生成的 Excel 填充模板...")
                source_excel_for_template = output_dir_for_req / f"{req_base}.xlsx"
                template_excel = config.requirements / "template" / "template.xlsx"
                # final_excel_output = output_dir_for_req / f"{req_base}_final_filled.xlsx" # Original name
                final_excel_output = output_dir_for_req / f"{req_base}_COSMIC.xlsx" # New name as per previous edit

                # --- Parse analysis file for targets and necessity ---
                analysis_file_path = output_dir_for_req / f"business_req_analysis_{req_base}.txt"
                logger.info(f"[{req_name}] 正在解析分析文件以提取建设目标和必要性: {analysis_file_path}")
                extracted_targets, extracted_necessity = parse_analysis_file(analysis_file_path)
                # --- End Parsing ---

                if source_excel_for_template.exists() and template_excel.exists():
                    success = process_excel_files(
                        source_excel_path=source_excel_for_template,
                        template_excel_path=template_excel,
                        output_excel_path=final_excel_output,
                        requirement_file_name=doc_file.name, # Pass the original doc/docx filename
                        targets=extracted_targets, # Use extracted value
                        necessity=extracted_necessity # Use extracted value
                    )
                    if success:
                        logger.info(f"[{req_name}] 最终模板填充 Excel 文件已生成: {final_excel_output}")
                    else:
                        logger.error(f"[{req_name}] 填充模板 Excel 文件失败。")
                else:
                    if not source_excel_for_template.exists():
                        logger.error(f"[{req_name}] 无法填充模板，因为源 Excel 文件不存在: {source_excel_for_template}")
                    if not template_excel.exists():
                         logger.error(f"[{req_name}] 无法填充模板，因为模板 Excel 文件不存在: {template_excel}")

            else:
                 logger.warning(f"[{req_name}] 由于未能获取合并后的内容，跳过 Excel、Word 和最终模板填充文件生成。") # Updated warning

        except Exception as post_process_e:
            logger.error(f"[{req_name}] 阶段 4-7 后置处理失败: {post_process_e}") # Updated error scope
            # 根据需要决定是否将此错误视为整个任务的失败
            # 如果需要，可以在这里重新抛出异常: raise post_process_e


        logger.info(f"需求处理完成: {req_name}")

    except Exception as e:
        # 在并发任务中记录错误，异常会被 Future 捕获
        logger.error(f"处理需求失败 {req_name}: {str(e)}")
        # 不再显式 raise，让 concurrent.futures 处理异常传递

def main():
    """主处理流程 - 使用并发处理"""
    successful_tasks = 0
    failed_tasks = 0
    try:
        config = ProjectPaths()

        # 确保输出目录存在
        config.output.mkdir(parents=True, exist_ok=True)

        # 获取所有需求文档
        doc_files = get_doc_files(config)

        if not doc_files:
            logger.warning("未找到任何需求文档，流程结束。")
            return

        # 使用 ThreadPoolExecutor 实现并发处理
        # max_workers 可以根据需要调整，None 表示由 Python 自动决定
        with concurrent.futures.ThreadPoolExecutor(max_workers=None) as executor:
            # 提交所有任务到线程池
            future_to_doc = {executor.submit(process_single_requirement, doc_file, config): doc_file for doc_file in doc_files}
            logger.info(f"已提交 {len(future_to_doc)} 个需求处理任务到线程池。")

            # 等待任务完成并处理结果/异常
            for future in concurrent.futures.as_completed(future_to_doc):
                doc_file = future_to_doc[future]
                req_name = f"{doc_file.parent.name}/{doc_file.stem}"
                try:
                    # future.result() 会阻塞直到任务完成
                    # 如果任务内部抛出异常，result() 会重新抛出该异常
                    future.result()
                    logger.info(f"任务成功完成: {req_name}")
                    successful_tasks += 1
                except Exception as exc:
                    logger.error(f"任务执行失败 {req_name}: {exc}")
                    failed_tasks += 1

        logger.info(f"所有需求处理任务完成。成功: {successful_tasks}, 失败: {failed_tasks}")

    except FileNotFoundError as e: # 单独处理文件未找到的初始化错误
         logger.error(f"初始化错误: {str(e)}")
    except Exception as e:
        logger.error(f"需求处理主流程发生严重错误: {str(e)}")
        # 在顶层可以选择是否重新抛出，这里选择不抛出，仅记录日志

if __name__ == "__main__":
    main()
