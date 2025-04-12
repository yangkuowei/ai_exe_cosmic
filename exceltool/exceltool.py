import openpyxl
import os
import re # Import regex for parsing
from pathlib import Path # Use pathlib for path handling
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font # Import style classes
import logging # Import logging

# Setup logger
logger = logging.getLogger(__name__)

# --- Default Style Configuration ---
DEFAULT_TARGET_FONT = Font(name='宋体', size=14)
DEFAULT_TARGET_ALIGNMENT = Alignment(horizontal='center', vertical='center', wrap_text=True)
DEFAULT_TARGET_START_ROW = 5 # Target sheet starts filling from this row
DEFAULT_SOURCE_START_ROW = 2 # Source sheet starts reading from this row (assuming header is row 1)

def parse_initiator_receiver(text: str, key: str) -> str:
    """Helper function to parse '发起者:' or '接收者:' content"""
    if not isinstance(text, str):
        return "" # Return empty if input is not string
    # Use regex to find the key followed by colon and capture the rest
    # Handles potential whitespace after colon
    match = re.search(rf"{key}\s*[:：]\s*(.*)", text, re.IGNORECASE)
    return match.group(1).strip() if match else ""

def map_source_col_to_target_col_for_merge(source_col_index):
    """Maps source column index to target column index specifically for MERGE logic."""
    # Based on the new data mapping rules:
    # Source Col 1 (Req Name, Initiator, Receiver) -> Target Col 1, 2, 3, 5. Merge based on Target Col 5?
    if source_col_index == 1:
        return 5 # Merge Target Col 5 based on Source Col 1 merges
    # Source Col 2 -> Target Col 4
    elif source_col_index == 2:
        return 4 # Merge Target Col 4 based on Source Col 2 merges
    # Source Col 3 -> Target Col 6
    elif source_col_index == 3:
        return 6 # Merge Target Col 6 based on Source Col 3 merges
    # Source Col 4 -> Target Col 7
    elif source_col_index == 4:
        return 7 # Merge Target Col 7 based on Source Col 4 merges
    # Source Col 5 -> Target Col 8
    elif source_col_index == 5:
        return 8 # Merge Target Col 8 based on Source Col 5 merges
    # Source Col 6 -> Target Col 9
    elif source_col_index == 6:
        return 9 # Merge Target Col 9 based on Source Col 6 merges
    # Source Col 7 -> Target Col 10
    elif source_col_index == 7:
        return 10 # Merge Target Col 10 based on Source Col 7 merges
    # Source Col 8 -> Target Col 11
    elif source_col_index == 8:
        return 11 # Merge Target Col 11 based on Source Col 8 merges
    else:
        # Source columns beyond 8 are not mapped for data transfer
        return None

def process_excel_files(
    source_excel_path: Path,
    template_excel_path: Path,
    output_excel_path: Path,
    requirement_file_name: str, # Original requirement doc name (e.g., "需求规格说明书_....doc")
    targets: str,
    necessity: str,
    source_sheet_name: str = 'Sheet1', # Default source sheet name
    target_sheet_name: str = '2、功能点拆分表', # Default target sheet name
    target_start_row: int = DEFAULT_TARGET_START_ROW,
    source_start_row: int = DEFAULT_SOURCE_START_ROW,
    target_font: Font = DEFAULT_TARGET_FONT,
    target_alignment: Alignment = DEFAULT_TARGET_ALIGNMENT
):
    """
    Reads data from source_excel_path, fills it into template_excel_path's specified sheet
    according to defined rules, applies formatting, replicates merges, adds targets/necessity
    to another sheet, and saves to output_excel_path.

    Args:
        source_excel_path (Path): Path to the source Excel file (e.g., {req_base}.xlsx).
        template_excel_path (Path): Path to the template Excel file.
        output_excel_path (Path): Path to save the final output Excel file.
        requirement_file_name (str): The original name of the requirement document file.
        targets (str): Text for the 'targets' section.
        necessity (str): Text for the 'necessity' section.
        source_sheet_name (str): Name of the sheet to read from in the source file.
        target_sheet_name (str): Name of the sheet to write to in the template file.
        target_start_row (int): Row number to start writing in the target sheet.
        source_start_row (int): Row number to start reading from in the source sheet.
        target_font (Font): Font style to apply to target cells.
        target_alignment (Alignment): Alignment style to apply to target cells.
    """
    logger.info(f"开始处理 Excel 文件...")
    logger.info(f"源文件: {source_excel_path}")
    logger.info(f"模板文件: {template_excel_path}")
    logger.info(f"输出文件: {output_excel_path}")

    if not source_excel_path.exists():
        logger.error(f"错误：源文件 '{source_excel_path}' 不存在。")
        return False
    if not template_excel_path.exists():
        logger.error(f"错误：模板文件 '{template_excel_path}' 不存在。")
        return False

    source_wb = None
    template_wb = None

    try:
        logger.info("正在加载工作簿...")
        source_wb = openpyxl.load_workbook(source_excel_path)
        template_wb = openpyxl.load_workbook(template_excel_path)
        logger.info("工作簿加载完成。")

        logger.info(f"正在选择工作表...")
        if source_sheet_name not in source_wb.sheetnames:
             logger.error(f"错误：源文件 '{source_excel_path}' 中找不到名为 '{source_sheet_name}' 的工作表。")
             return False
        source_ws = source_wb[source_sheet_name]

        try:
            target_ws = template_wb[target_sheet_name]
        except KeyError:
            sheet_names = template_wb.sheetnames
            if len(sheet_names) >= 3:
                target_sheet_index = 2 # Index 2 corresponds to the 3rd sheet
                actual_target_sheet_name = sheet_names[target_sheet_index]
                logger.warning(f"警告：在模板文件 '{template_excel_path}' 中找不到名为 '{target_sheet_name}' 的工作表。")
                logger.warning(f"将使用第三个工作表：'{actual_target_sheet_name}' (索引 {target_sheet_index})。")
                target_ws = template_wb.worksheets[target_sheet_index]
            else:
                logger.error(f"错误：模板文件 '{template_excel_path}' 中找不到名为 '{target_sheet_name}' 的工作表，且工作表总数少于3个。")
                return False

        logger.info(f"源工作表: '{source_ws.title}'")
        logger.info(f"目标工作表: '{target_ws.title}'")

        logger.info(f"开始从源文件第 {source_start_row} 行读取数据，填充到目标文件第 {target_start_row} 行...")
        current_target_row = target_start_row
        processed_rows_count = 0
        max_source_row = source_ws.max_row

        # Define target columns to format (1 to 13)
        target_columns_to_format = list(range(1, 14))

        # Prepare requirement name for Target Col 1
        req_name_cleaned = requirement_file_name.replace("需求规格说明书_", "").split('.')[0] # Remove prefix and extension

        for s_row_index in range(source_start_row, max_source_row + 1):
            # --- 1. Data Extraction and Parsing ---
            source_col1_val = source_ws.cell(row=s_row_index, column=1).value
            source_col2_val = source_ws.cell(row=s_row_index, column=2).value
            source_col3_val = source_ws.cell(row=s_row_index, column=3).value
            # Read source columns 4 to 8 for target columns 6 to 11
            source_cols_4_to_8 = [source_ws.cell(row=s_row_index, column=c).value for c in range(4, 9)] # Cols D to H

            initiator = parse_initiator_receiver(source_col1_val, "发起者")
            receiver = parse_initiator_receiver(source_col1_val, "接收者")

            # --- 2. Data Filling ---
            # Target Col 1: Cleaned requirement name
            target_ws.cell(row=current_target_row, column=1, value=req_name_cleaned)
            # Target Col 2: Initiator
            target_ws.cell(row=current_target_row, column=2, value=initiator)
            # Target Col 3: Receiver
            target_ws.cell(row=current_target_row, column=3, value=receiver)
            # Target Col 4: Source Col 2
            target_ws.cell(row=current_target_row, column=4, value=source_col2_val)
            # Target Col 5: Source Col 1 (original value)
            target_ws.cell(row=current_target_row, column=5, value=source_col1_val)
            # Target Col 6-11: Source Col 3-8
            for i, val in enumerate(source_cols_4_to_8):
                 target_ws.cell(row=current_target_row, column=6 + i, value=val) # 6+0=6, 6+1=7,... 6+4=10
            # Need one more column from source (Col 8 -> Target Col 11)
            source_col8_val = source_ws.cell(row=s_row_index, column=8).value # Read source col 8 explicitly if needed above loop missed it
            target_ws.cell(row=current_target_row, column=11, value=source_col8_val) # Fill target col 11

            # Target Col 12: Fixed "新增"
            target_ws.cell(row=current_target_row, column=12, value="新增")
            # Target Col 13: Fixed "1"
            target_ws.cell(row=current_target_row, column=13, value="1") # Store as string or number? Let's use string for consistency

            # --- 3. Apply Formatting ---
            for col_idx in target_columns_to_format:
                try:
                    cell = target_ws.cell(row=current_target_row, column=col_idx)
                    cell.font = target_font
                    cell.alignment = target_alignment
                except Exception as format_error:
                    logger.warning(f"警告：无法应用格式到单元格 {get_column_letter(col_idx)}{current_target_row}。错误: {format_error}")

            current_target_row += 1
            processed_rows_count += 1

        logger.info(f"数据填充和格式应用完成，共处理了 {processed_rows_count} 行数据。")

        # --- 4a. Apply Specific Target Merges ---
        last_filled_row = current_target_row - 1
        if processed_rows_count > 1 and last_filled_row >= target_start_row:
            # Merge Target Column A (Col 1)
            try:
                col_a_range = f"A{target_start_row}:A{last_filled_row}"
                logger.info(f"  应用特定合并: 目标列 A ({col_a_range})")
                target_ws.merge_cells(start_row=target_start_row, start_column=1, end_row=last_filled_row, end_column=1)
                # Apply format to top-left cell of merge
                top_left_cell_a = target_ws.cell(row=target_start_row, column=1)
                top_left_cell_a.font = target_font
                top_left_cell_a.alignment = target_alignment
            except Exception as merge_a_error:
                logger.warning(f"  警告：无法合并目标列 A ({col_a_range})。错误：{merge_a_error}")

        # --- 4b. Handle Merged Cells (Replicated from Source and Extended) ---
        logger.info("开始处理从源文件复制并扩展的合并单元格...")
        merged_cells_copied = 0
        # Ensure we get a list copy, as modifying merges while iterating can cause issues
        source_merged_ranges = list(source_ws.merged_cells.ranges)

        for merged_range in source_merged_ranges:
            # Check if the merged range starts within the rows we processed
            if merged_range.min_row >= source_start_row:
                # Calculate corresponding target row range
                target_min_r = merged_range.min_row - source_start_row + target_start_row
                target_max_r = merged_range.max_row - source_start_row + target_start_row

                # Determine the target column range based on the mapping
                target_min_c = float('inf')
                target_max_c = float('-inf')
                valid_map_found = False

                for s_col in range(merged_range.min_col, merged_range.max_col + 1):
                    t_col = map_source_col_to_target_col_for_merge(s_col)
                    if t_col is not None:
                        target_min_c = min(target_min_c, t_col)
                        target_max_c = max(target_max_c, t_col)
                        valid_map_found = True

                # Apply merge in target sheet if a valid mapping was found and it's not a single cell
                if valid_map_found and target_min_c <= target_max_c and target_min_r <= target_max_r:
                    if not (target_min_r == target_max_r and target_min_c == target_max_c):
                        try:
                            target_range_str = f"{get_column_letter(target_min_c)}{target_min_r}:{get_column_letter(target_max_c)}{target_max_r}"
                            logger.info(f"  应用合并: 源 {merged_range.coord} -> 目标 {target_range_str}")
                            # Important: Unmerge first if the target range overlaps existing merges
                            # This is complex; a simpler approach is to just try merging. openpyxl might handle some overlaps.
                            # For robust handling, you'd need to check overlaps with target_ws.merged_cells
                            target_ws.merge_cells(start_row=target_min_r, start_column=target_min_c,
                                                  end_row=target_max_r, end_column=target_max_c)
                            merged_cells_copied += 1
                            # Apply format to the top-left cell of the primary merged range
                            top_left_cell = target_ws.cell(row=target_min_r, column=target_min_c)
                            top_left_cell.font = target_font
                            top_left_cell.alignment = target_alignment

                            # --- Apply conditional merges for Columns B and C based on Column E merge ---
                            # Check if the primary merge was applied to Column E (target_min_c == 5 and target_max_c == 5)
                            if target_min_c == 5 and target_max_c == 5:
                                # Merge Column B (Col 2) with the same row range
                                try:
                                    col_b_range = f"B{target_min_r}:B{target_max_r}"
                                    logger.info(f"    扩展合并: 目标列 B ({col_b_range}) 基于 E 列合并")
                                    target_ws.merge_cells(start_row=target_min_r, start_column=2, end_row=target_max_r, end_column=2)
                                    top_left_cell_b = target_ws.cell(row=target_min_r, column=2)
                                    top_left_cell_b.font = target_font
                                    top_left_cell_b.alignment = target_alignment
                                except Exception as merge_b_error:
                                    logger.warning(f"    警告：无法合并目标列 B ({col_b_range})。错误：{merge_b_error}")

                                # Merge Column C (Col 3) with the same row range
                                try:
                                    col_c_range = f"C{target_min_r}:C{target_max_r}"
                                    logger.info(f"    扩展合并: 目标列 C ({col_c_range}) 基于 E 列合并")
                                    target_ws.merge_cells(start_row=target_min_r, start_column=3, end_row=target_max_r, end_column=3)
                                    top_left_cell_c = target_ws.cell(row=target_min_r, column=3)
                                    top_left_cell_c.font = target_font
                                    top_left_cell_c.alignment = target_alignment
                                except Exception as merge_c_error:
                                    logger.warning(f"    警告：无法合并目标列 C ({col_c_range})。错误：{merge_c_error}")

                        except Exception as merge_error:
                            # Log errors, e.g., due to overlapping merges
                            logger.warning(f"  警告：无法合并主要目标范围 {target_range_str}。可能与其他合并冲突。错误：{merge_error}")

        logger.info(f"合并单元格处理完成，尝试应用了 {merged_cells_copied} 个主要合并范围（并可能扩展了 B/C 列）。")

        # --- 5. Handle Second Sheet (Targets & Necessity) ---
        if len(template_wb.sheetnames) >= 2:
            # Assume the second sheet (index 1) is the target
            env_sheet = template_wb.worksheets[1]
            env_sheet_title = env_sheet.title
            logger.info(f"正在处理第二个工作表: '{env_sheet_title}' 用于写入建设目标和必要性。")

            # Write targets to A2, merge A2:J3
            env_sheet.cell(row=2, column=1, value=targets)
            env_sheet.merge_cells(start_row=2, start_column=1, end_row=3, end_column=10)
            cell_a2 = env_sheet.cell(row=2, column=1)
            cell_a2.font = target_font
            cell_a2.alignment = target_alignment
            logger.info(f"已将建设目标写入 '{env_sheet_title}'!A2 并合并 A2:J3。")

            # Write necessity to A5, merge A5:J6
            env_sheet.cell(row=5, column=1, value=necessity)
            env_sheet.merge_cells(start_row=5, start_column=1, end_row=6, end_column=10)
            cell_a5 = env_sheet.cell(row=5, column=1)
            cell_a5.font = target_font
            cell_a5.alignment = target_alignment
            logger.info(f"已将建设必要性写入 '{env_sheet_title}'!A5 并合并 A5:J6。")
        else:
            logger.warning("警告：模板文件工作表少于2个，跳过建设目标和必要性写入。")

        # --- 6. Save Output ---
        logger.info(f"正在保存结果到 '{output_excel_path}'...")
        template_wb.save(output_excel_path)
        logger.info("文件保存成功！")
        return True # Indicate success

    except FileNotFoundError as e:
        logger.error(f"错误：文件未找到 - {e}")
        return False
    except KeyError as e:
         logger.error(f"错误：找不到工作表 - {e}。请检查工作表名称。")
         return False
    except Exception as e:
        logger.error(f"处理 Excel 文件过程中发生未知错误：{e}", exc_info=True) # Log traceback
        # import traceback
        # traceback.print_exc()
        return False
    finally:
        # Ensure workbooks are closed
        if source_wb:
            try:
                source_wb.close()
            except Exception as close_err:
                 logger.warning(f"关闭源工作簿时出错: {close_err}")
        if template_wb:
            try:
                template_wb.close()
            except Exception as close_err:
                 logger.warning(f"关闭模板工作簿时出错: {close_err}")
        logger.info("工作簿关闭操作完成。")

