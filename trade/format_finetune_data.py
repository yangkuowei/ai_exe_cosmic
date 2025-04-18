import json
import os
from pathlib import Path
import sys


def format_for_finetuning(source_dir: str, output_finetune_file: str):
    """
    Reads JSON files from source_dir, formats them for instruction fine-tuning,
    and writes them to a JSONL file.

    Args:
        source_dir: The path to the directory containing the source JSON files.
        output_finetune_file: The path to the output JSONL file for fine-tuning.
    """
    source_path = Path(source_dir)
    output_path = Path(output_finetune_file)

    if not source_path.is_dir():
        print(f"Error: Source directory '{source_dir}' not found or is not a directory.", file=sys.stderr)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    processed_count = 0
    error_count = 0

    print(f"Starting formatting process for fine-tuning...")
    print(f"Source directory: {source_path.resolve()}")
    print(f"Output file: {output_path.resolve()}")

    try:
        with open(output_path, 'w', encoding='utf-8') as outfile:
            for json_file in source_path.glob('*.json'):
                try:
                    with open(json_file, 'r', encoding='utf-8') as infile:
                        data = json.load(infile)

                        # Validate keys
                        if not all(key in data for key in ["title", "description", "solution"]):
                            print(f"Warning: Skipping file {json_file.name}. Missing required keys.")
                            error_count += 1
                            continue

                        # Ensure content is not empty or just whitespace (basic check)
                        if not data["title"].strip() or not data["description"].strip() or not data["solution"].strip():
                            print(
                                f"Warning: Skipping file {json_file.name}. Contains empty title, description, or solution.")
                            error_count += 1
                            continue

                        # Format the data for instruction tuning
                        instruction = "你是一名专业的COSMIC软件需求分析师。请根据以下需求描述（包含背景、解决方案、预估工作量），严格按照定义的规则（包括提取核心信息、基于工作量拆分与合并功能点、详细描述解决方案、确定功能用户、计算工作量占比、分析目标与必要性等），生成结构化的COSMIC软件需求分析JSON。"
                        input_text = f"需求名称：{data['customerRequirement']}\n需求：{data['requirementBackground']}"
                        output_text = data['solution']

                        formatted_record = {
                            "instruction": instruction,
                            "input": input_text,
                            "output": output_text
                        }

                        # Write the formatted record as a JSON line
                        json.dump(formatted_record, outfile, ensure_ascii=False)
                        outfile.write('\n')
                        processed_count += 1
                        if processed_count % 100 == 0:
                            print(f"Formatted {processed_count} records...")

                except json.JSONDecodeError:
                    print(f"Error: Could not decode JSON from file {json_file.name}. Skipping.", file=sys.stderr)
                    error_count += 1
                except Exception as e:
                    print(f"Error processing file {json_file.name}: {e}", file=sys.stderr)
                    error_count += 1

    except IOError as e:
        print(f"Error writing to output file {output_path}: {e}", file=sys.stderr)
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return

    print(f"\nFormatting complete.")
    print(f"Successfully formatted {processed_count} records.")
    if error_count > 0:
        print(f"Skipped {error_count} files due to errors or missing/empty keys.")
    print(f"Fine-tuning data written to: {output_path.resolve()}")


# --- Configuration ---
SOURCE_DIRECTORY = "../requirement_extraction_results"
# Adjust this path as needed
# SOURCE_DIRECTORY = "requirement_extraction_results"

OUTPUT_FINETUNE_JSONL_FILE = "finetuning_dataset.jsonl"  # Formatted data for fine-tuning

# --- Run the script ---
if __name__ == "__main__":
    if not os.path.isdir(SOURCE_DIRECTORY):
        print(f"Error: The specified source directory '{SOURCE_DIRECTORY}' does not exist.", file=sys.stderr)
        print("Please update the SOURCE_DIRECTORY variable in the script.", file=sys.stderr)
    else:
        format_for_finetuning(SOURCE_DIRECTORY, OUTPUT_FINETUNE_JSONL_FILE)
