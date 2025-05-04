import json
import sys

def format_jsonl_content(input_filename="processed_data.jsonl", output_filename="processed_data_new.jsonl"):
    """
    Reads a JSONL file, extracts 'instruction', 'input', and 'output' fields
    from each line's JSON object, formats them into a specific string structure,
    wraps this string under a "text" key in a new JSON object,
    and writes the results to a new JSONL file.

    Args:
        input_filename (str): The path to the input JSONL file.
        output_filename (str): The path to the output JSONL file.
    """
    processed_lines = 0
    error_lines = 0
    print(f"Starting processing: Reading from '{input_filename}', writing to '{output_filename}'...")

    try:
        # Use 'with' statements for automatic file closing
        # Specify encoding='utf-8' for broader compatibility
        with open(input_filename, 'r', encoding='utf-8') as infile, \
             open(output_filename, 'w', encoding='utf-8') as outfile:

            for i, line in enumerate(infile):
                # Remove leading/trailing whitespace (like newline characters)
                line = line.strip()

                # Skip empty lines
                if not line:
                    print(f"Warning: Skipping empty line at line number {i+1}")
                    continue

                try:
                    # Parse the original JSON string into a Python dictionary
                    original_data = json.loads(line)

                    # Extract required fields, handle potential missing keys
                    instruction = original_data.get('instruction', '') # Use .get for default value if key missing
                    input_val = original_data.get('input', '')
                    output_val = original_data.get('output', '')

                    # --- Check if essential keys were present (optional, depends on requirements) ---
                    # You might want to skip lines if certain keys are absolutely required
                    # if 'instruction' not in original_data or 'input' not in original_data or 'output' not in original_data:
                    #     print(f"Warning: Skipping line {i+1} due to missing required keys ('instruction', 'input', or 'output'). Content: '{line}'")
                    #     error_lines += 1
                    #     continue
                    # -----------------------------------------------------------------------------

                    # Format the text string using an f-string
                    formatted_text = f"\n{instruction}。\n\n<|input|>{input_val}\n\n<|output|>{output_val}"

                    # Create the new structure with the "text" key
                    new_data = {"text": formatted_text}

                    # Convert the new Python dictionary back into a JSON string
                    # ensure_ascii=False is important for handling non-ASCII characters correctly
                    output_line = json.dumps(new_data, ensure_ascii=False)
                    if len(output_line) > 3000:
                        continue
                    # Write the new JSON string to the output file, followed by a newline
                    outfile.write(output_line + '\n')
                    processed_lines += 1

                except json.JSONDecodeError as e:
                    error_lines += 1
                    print(f"Error: Could not decode JSON on line {i+1}. Skipping. Content: '{line}'. Details: {e}", file=sys.stderr)
                # Removed KeyError handling as .get() prevents it now, unless you uncomment the check block above
                except Exception as e:
                    error_lines += 1
                    print(f"Error: An unexpected error occurred processing line {i+1}. Skipping. Content: '{line}'. Details: {e}", file=sys.stderr)

        print("\nProcessing finished.")
        print(f"Successfully processed lines: {processed_lines}")
        if error_lines > 0:
            print(f"Skipped lines due to errors or missing keys: {error_lines}")
        print(f"Output written to '{output_filename}'.")

    except FileNotFoundError:
        print(f"Error: Input file '{input_filename}' not found.", file=sys.stderr)
    except IOError as e:
        print(f"Error: Could not read/write file. Input: '{input_filename}', Output: '{output_filename}'. Details: {e}", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

# --- Script Execution ---
if __name__ == "__main__":
    # Define the input and output file names
    input_file = "processed_data.jsonl"
    output_file = "processed_data_new.jsonl"

    # Run the function
    format_jsonl_content(input_file, output_file)
