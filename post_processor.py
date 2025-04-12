import logging
from pathlib import Path
import os
import re

# Assuming these functions/classes are defined elsewhere and needed
from project_paths import ProjectPaths
from read_file_content import merge_temp_files, save_content_to_file, read_file_content
from exceltool.exceltool import process_excel_files

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


def run_post_processing(req_name: str, config: ProjectPaths, dev_name: str, req_base: str, doc_file: Path):
    """
    Handles post-processing steps for a single requirement:
    - Merges temporary COSMIC tables.
    - Generates final Markdown, Excel, and Word files.
    - Fills the template Excel file.
    - Cleans up temporary files.
    """
    logger.info(f"[{req_name}] 阶段 4: 开始后置处理")
    try:
        # Determine paths
        output_dir_for_req = config.output / dev_name / req_base
        output_dir_for_req.mkdir(parents=True, exist_ok=True)
        final_output_file = output_dir_for_req / f"{req_base}_cosmic_merged.md"
        temp_file_pattern = "table_cosmic_*.md"

        merged_content_for_export = None

        # Check if merged file exists
        if final_output_file.exists():
            logger.info(f"[{req_name}] 发现已存在的合并文件: {final_output_file}，将直接使用其内容。")
            try:
                merged_content_for_export = read_file_content(final_output_file)
                # Clean up lingering temp files
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
                merged_content_for_export = None

        # Merge if needed
        if merged_content_for_export is None:
            logger.info(f"[{req_name}] 未找到或无法读取合并文件，开始查找并合并临时文件...")
            temp_files_to_merge = sorted(list(output_dir_for_req.glob(temp_file_pattern)))

            if not temp_files_to_merge:
                logger.warning(f"[{req_name}] 在目录 {output_dir_for_req} 中未找到要合并的临时文件 (匹配模式: {temp_file_pattern})。无法生成合并文件和后续导出。")
            else:
                logger.info(f"[{req_name}] 找到 {len(temp_files_to_merge)} 个临时文件准备合并。")
                try:
                    merged_content_for_export = merge_temp_files(temp_files_to_merge)
                    with open(final_output_file, "w", encoding="utf-8") as f_out:
                        f_out.write(merged_content_for_export)
                    logger.info(f"[{req_name}] COSMIC 表已合并到: {final_output_file}")

                    # Delete temp files
                    logger.info(f"[{req_name}] 开始删除临时 COSMIC 表文件...")
                    deleted_count = 0
                    for temp_file in temp_files_to_merge:
                        try:
                            temp_file.unlink()
                            deleted_count += 1
                        except OSError as e:
                            logger.warning(f"[{req_name}] 删除临时文件失败 {temp_file}: {e}")
                    logger.info(f"[{req_name}] 已成功删除 {deleted_count} 个临时文件。")
                except Exception as merge_err:
                     logger.error(f"[{req_name}] 合并或写入文件过程中出错: {merge_err}")
                     merged_content_for_export = None

        # Export if content is available
        if merged_content_for_export is not None:
            # 5. Generate Excel
            logger.info(f"[{req_name}] 开始将合并后的 Markdown 转换为 Excel 文件...")
            save_content_to_file(
                file_name=req_base,
                output_dir=output_dir_for_req,
                content=merged_content_for_export,
                content_type="xlsx"
            )
            logger.info(f"[{req_name}] Excel 文件已生成: {output_dir_for_req / (req_base + '.xlsx')}")

            # 6. Generate Word
            logger.info(f"[{req_name}] 开始将 Excel 文件转换为 Word 文件...")
            save_content_to_file(
                file_name=req_base,
                output_dir=output_dir_for_req,
                content=merged_content_for_export,
                content_type="docx"
            )
            logger.info(f"[{req_name}] Word 文件已生成: {output_dir_for_req / (req_base + '.docx')}")

            # 7. Fill template Excel
            logger.info(f"[{req_name}] 阶段 7: 开始使用生成的 Excel 填充模板...")
            source_excel_for_template = output_dir_for_req / f"{req_base}.xlsx"
            template_excel = config.requirements / "template" / "template.xlsx"
            final_excel_output = output_dir_for_req / f"{req_base}_COSMIC.xlsx"

            # Parse analysis file
            analysis_file_path = output_dir_for_req / f"business_req_analysis_{req_base}.txt"
            logger.info(f"[{req_name}] 正在解析分析文件以提取建设目标和必要性: {analysis_file_path}")
            extracted_targets, extracted_necessity = parse_analysis_file(analysis_file_path)

            if source_excel_for_template.exists() and template_excel.exists():
                success = process_excel_files(
                    source_excel_path=source_excel_for_template,
                    template_excel_path=template_excel,
                    output_excel_path=final_excel_output,
                    requirement_file_name=doc_file.name,
                    targets=extracted_targets,
                    necessity=extracted_necessity
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
             logger.warning(f"[{req_name}] 由于未能获取合并后的内容，跳过 Excel、Word 和最终模板填充文件生成。")

    except Exception as post_process_e:
        logger.error(f"[{req_name}] 阶段 4-7 后置处理失败: {post_process_e}", exc_info=True)
        # Decide if this should halt the entire process for this requirement
        # raise post_process_e # Optionally re-raise
