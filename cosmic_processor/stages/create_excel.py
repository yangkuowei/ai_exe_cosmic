import os
from pathlib import Path

from exceltool.exceltool import process_excel_files
from ..core.context import ProcessingContext
from project_paths import FILE_NAME, TEMPLATE_PATHS


def process_excel(pipeline, context: ProcessingContext) -> bool:
    """建设必要性分析阶段"""
    try:
        # 构建完整输出路径
        requirement_dir = Path(context.input_path).stem
        output_path = os.path.join(context.stage_data['output_dir'], requirement_dir)
        os.makedirs(output_path, exist_ok=True)


        source_excel_path = os.path.join(output_path,FILE_NAME['temp_excel'])
        template_excel_path =  os.path.join(pipeline.out_template_base_dir, FILE_NAME['template_xlsx'])
        output_excel_path = os.path.join(output_path, context.stem+'-COSMIC.xlsx')
        
        # Read and parse necessity file
        necessity_file = os.path.join(output_path, FILE_NAME['necessity'])
        with open(necessity_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract targets section (between "一、 建设目标" and "二、 建设必要性")
        targets_start = content.find("一、 建设目标") + len("一、 建设目标")
        targets_end = content.find("二、 建设必要性")
        extracted_targets = '\n'.join(
            line.strip() 
            for line in content[targets_start:targets_end].strip().split('\n'))
        
        # Extract necessity section (after "二、 建设必要性")
        necessity_start = content.find("二、 建设必要性") + len("二、 建设必要性")
        extracted_necessity = '\n'.join(
            line.strip()
            for line in content[necessity_start:].strip().split('\n'))

        process_excel_files(
            source_excel_path=Path(source_excel_path),
            template_excel_path=Path(template_excel_path),
            output_excel_path=Path(output_excel_path),
            requirement_file_name=context.stem,  # 原始需求文件名
            targets=extracted_targets,
            necessity=extracted_necessity,
            architecture_diagram_path=None  # Pass the image path
        )
        return True

    except Exception as e:
        pipeline.logger.error(f"xlsx表格生成错误: {str(e)}")
        return False
