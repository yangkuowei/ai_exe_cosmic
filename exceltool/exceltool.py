import openpyxl
import os
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font # 导入样式相关的类

# --- 配置 ---
source_file = 'f1.xlsx'
template_file = 'template.xlsx'
output_file = 'output_filled_merged_formatted.xlsx' # 新的输出文件名

source_sheet_name = 'Sheet1'
target_sheet_name = '2、功能点拆分表' # 模板中需要填充的表名

target_start_row = 5 # 目标文件中开始填充的行号
source_start_row = 2 # 源文件中开始读取的行号

# --- 样式配置 ---
target_font = Font(name='宋体', size=14)
target_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True) # wrap_text=True 通常与居中搭配使用较好

# --- 配置结束 ---

def map_source_col_to_target_col(source_col_index):
    """根据规则将源列索引映射到目标列索引"""
    if source_col_index == 1:
        return 1 # 源 A -> 目标 A
    elif source_col_index == 3:
        return 4 # 源 C -> 目标 D
    elif source_col_index == 2:
        return 5 # 源 B -> 目标 E
    elif 4 <= source_col_index <= 11:
        # 源 D(4) -> 目标 F(6), ..., 源 K(11) -> 目标 M(13)
        return source_col_index + 2
    else:
        return None

def process_excel_files(source_path, template_path, output_path,targets,necessity):
    """
    读取 source_path 的数据填充到 template_path 的指定工作表，
    复制合并单元格状态，应用单元格格式，并保存为 output_path。
    targets：建设目标文本
    necessity：建设必要性
    """
    print(f"开始处理 Excel 文件...")
    print(f"源文件: {source_path}")
    print(f"模板文件: {template_path}")
    print(f"输出文件: {output_path}")

    if not os.path.exists(source_path):
        print(f"错误：源文件 '{source_path}' 不存在。")
        return
    if not os.path.exists(template_path):
        print(f"错误：模板文件 '{template_path}' 不存在。")
        return

    try:
        print("正在加载工作簿...")
        source_wb = openpyxl.load_workbook(source_path)
        template_wb = openpyxl.load_workbook(template_path)
        print("工作簿加载完成。")

        print(f"正在选择工作表...")
        if source_sheet_name not in source_wb.sheetnames:
             print(f"错误：源文件 '{source_path}' 中找不到名为 '{source_sheet_name}' 的工作表。")
             source_wb.close()
             template_wb.close()
             return
        source_ws = source_wb[source_sheet_name]

        try:
            target_ws = template_wb[target_sheet_name]
        except KeyError:
            sheet_names = template_wb.sheetnames
            if len(sheet_names) >= 3:
                target_sheet_index = 2
                actual_target_sheet_name = sheet_names[target_sheet_index]
                print(f"警告：在模板文件 '{template_path}' 中找不到名为 '{target_sheet_name}' 的工作表。")
                print(f"将使用第三个工作表：'{actual_target_sheet_name}' (索引 {target_sheet_index})。")
                target_ws = template_wb.worksheets[target_sheet_index]
            else:
                print(f"错误：模板文件 '{template_path}' 中找不到名为 '{target_sheet_name}' 的工作表，且工作表总数少于3个。")
                source_wb.close()
                template_wb.close()
                return

        print(f"源工作表: '{source_ws.title}'")
        print(f"目标工作表: '{target_ws.title}'")

        print(f"开始从源文件第 {source_start_row} 行读取数据，填充到目标文件第 {target_start_row} 行...")
        current_target_row = target_start_row
        processed_rows_count = 0
        max_source_row = source_ws.max_row

        # 定义需要应用格式的目标列范围 (1 到 13)
        target_columns_to_format = list(range(1, 14))

        for s_row_index in range(source_start_row, max_source_row + 1):
            # --- 1. 数据填充 ---
            # (3) template.xlsx 第1列 <- f1.xlsx Sheet1 第1列 (A)
            val_col1_src = source_ws.cell(row=s_row_index, column=1).value
            target_ws.cell(row=current_target_row, column=1, value=val_col1_src)

            # (4) template.xlsx 第2列 <- 固定值 "CRM系统"
            target_ws.cell(row=current_target_row, column=2, value="CRM系统")

            # (5) template.xlsx 第3列 <- 固定值 "订单中心"
            target_ws.cell(row=current_target_row, column=3, value="订单中心")

            # (6) template.xlsx 第4列 <- f1.xlsx Sheet1 第3列 (C)
            val_col3_src = source_ws.cell(row=s_row_index, column=3).value
            target_ws.cell(row=current_target_row, column=4, value=val_col3_src)

            # (7) template.xlsx 第5列 <- f1.xlsx Sheet1 第2列 (B)
            val_col2_src = source_ws.cell(row=s_row_index, column=2).value
            target_ws.cell(row=current_target_row, column=5, value=val_col2_src)

            # (8) template.xlsx 第6至13列 <- f1.xlsx Sheet1 第4至11列 (D to K)
            for i in range(8):
                source_col_index = 4 + i
                target_col_index = 6 + i
                val_src = source_ws.cell(row=s_row_index, column=source_col_index).value
                target_ws.cell(row=current_target_row, column=target_col_index, value=val_src)

            # --- 2. 应用格式 ---
            # 对当前目标行的所有填充列应用字体和对齐方式
            for col_idx in target_columns_to_format:
                try:
                    cell = target_ws.cell(row=current_target_row, column=col_idx)
                    cell.font = target_font
                    cell.alignment = target_alignment
                except Exception as format_error:
                     # 理论上不应出错，但保留以防万一
                    print(f"警告：无法应用格式到单元格 {get_column_letter(col_idx)}{current_target_row}。错误: {format_error}")


            current_target_row += 1
            processed_rows_count += 1

        print(f"数据填充和格式应用完成，共处理了 {processed_rows_count} 行数据。")

        # --- 3. 处理合并单元格 ---
        print("开始处理合并单元格...")
        merged_cells_copied = 0
        source_merged_ranges = list(source_ws.merged_cells.ranges)

        for merged_range in source_merged_ranges:
            min_r, min_c, max_r, max_c = merged_range.min_row, merged_range.min_col, merged_range.max_row, merged_range.max_col

            if min_r >= source_start_row:
                target_min_r = min_r - source_start_row + target_start_row
                target_max_r = max_r - source_start_row + target_start_row

                target_min_c = float('inf')
                target_max_c = float('-inf')
                valid_map_found = False

                for s_col in range(min_c, max_c + 1):
                    t_col = map_source_col_to_target_col(s_col)
                    if t_col is not None:
                        target_min_c = min(target_min_c, t_col)
                        target_max_c = max(target_max_c, t_col)
                        valid_map_found = True

                if valid_map_found:
                    if target_min_c <= target_max_c and target_min_r <= target_max_r:
                        if not (target_min_r == target_max_r and target_min_c == target_max_c):
                            try:
                                target_range_str = f"{get_column_letter(target_min_c)}{target_min_r}:{get_column_letter(target_max_c)}{target_max_r}"
                                print(f"  应用合并: 源 {merged_range.coord} -> 目标 {target_range_str}")
                                target_ws.merge_cells(start_row=target_min_r, start_column=target_min_c,
                                                      end_row=target_max_r, end_column=target_max_c)
                                merged_cells_copied += 1
                                # --- 对合并后的单元格左上角应用格式 (可选，但通常需要) ---
                                # 合并单元格的格式由其左上角单元格决定
                                top_left_cell = target_ws.cell(row=target_min_r, column=target_min_c)
                                top_left_cell.font = target_font
                                top_left_cell.alignment = target_alignment
                            except Exception as merge_error:
                                print(f"  警告：无法合并目标范围 {target_range_str}。可能与其他合并冲突。错误：{merge_error}")

        print(f"合并单元格处理完成，成功应用了 {merged_cells_copied} 个合并范围。")

        # --- 处理第二个Sheet页（环境图）的targets写入 ---
        if len(template_wb.sheetnames) >= 2:
            env_sheet = template_wb.worksheets[1]  # 第二个Sheet页
            if env_sheet.title == "1、环境图":
                # 写入targets内容到A2单元格
                env_sheet.cell(row=2, column=1, value=targets)
                # 合并A2:J3范围的单元格
                env_sheet.merge_cells(start_row=2, start_column=1, end_row=3, end_column=10)
                # 应用格式
                merged_cell = env_sheet.cell(row=2, column=1)
                merged_cell.font = target_font
                merged_cell.alignment = target_alignment
                print(f"已将targets内容写入'{env_sheet.title}'工作表A2单元格并合并A2:J3范围")
                
                # 写入necessity内容到A5单元格
                env_sheet.cell(row=5, column=1, value=necessity)
                # 合并A5:J6范围的单元格
                env_sheet.merge_cells(start_row=5, start_column=1, end_row=6, end_column=10)
                # 应用格式
                merged_cell = env_sheet.cell(row=5, column=1)
                merged_cell.font = target_font
                merged_cell.alignment = target_alignment
                print(f"已将necessity内容写入'{env_sheet.title}'工作表A5单元格并合并A5:J6范围")
            else:
                print(f"警告：第二个工作表名称不是'1、环境图'，而是'{env_sheet.title}'，跳过targets和necessity写入")
        else:
            print("警告：模板文件工作表少于2个，跳过targets和necessity写入")

        # --- 保存修改后的模板文件 ---
        print(f"正在保存结果到 '{output_path}'...")
        template_wb.save(output_path)
        print("文件保存成功！")

    except FileNotFoundError:
        print(f"错误：文件未找到。请确保 '{source_path}' 和 '{template_path}' 存在。")
    except KeyError as e:
         print(f"错误：找不到工作表：{e}。请检查工作表名称是否正确。")
    except Exception as e:
        print(f"处理过程中发生未知错误：{e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'source_wb' in locals() and source_wb:
            source_wb.close()
        if 'template_wb' in locals() and template_wb:
            template_wb.close()
        print("工作簿已关闭。")

# --- 执行主函数 ---
if __name__ == "__main__":
    process_excel_files(source_file, template_file, output_file,'建设目标','建设必要性')
    print("脚本执行完毕。")
