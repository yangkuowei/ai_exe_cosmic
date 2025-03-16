from typing import Callable, Any, Tuple, Dict, List
from openai import OpenAI  # Assuming you're using the OpenAI library
import os


# api_key = os.getenv("DEEP_SEEK_API_KEY"), DEEP_SEEK
# base_url = "https://api.deepseek.com/v1"
# model_name = "deepseek-reasoner"

# api_key = os.getenv("API_302_KEY"), api.302
base_url = "https://api.302.ai/v1/chat/completions"
model_name = "gemini-2.0-pro-exp-02-05"

# api_key = os.getenv("DASHSCOPE_API_KEY"), 阿里
# base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# model_name = "qwq-32b"

# api_key = os.getenv("NVIDIA_API_KEY"), #英伟达
# base_url = "https://integrate.api.nvidia.com/v1"
# model_name = "deepseek-ai/deepseek-r1"


client = OpenAI(
    # 如果没有配置环境变量，请用百炼API Key替换：api_key="sk-xxx"
    api_key=os.getenv("API_302_KEY"),
    base_url=base_url
)

def call_ai(
    ai_prompt: str,
    requirement_content: str,
    extractor: Callable[[str], Any],
    validator: Callable[[Any], Tuple[bool, str]],
    max_iterations: int = 5,
) -> str:
    """
    Calls an AI model and refines the response based on extraction and validation.

    Args:
        ai_prompt: The system prompt for the AI.
        requirement_content: The user's requirement.
        extractor: A function that extracts relevant data (e.g., table, JSON) from the AI's response.
        validator: A function that validates the extracted data and returns (is_valid, error_message).
        max_iterations: Maximum number of conversation turns.

    Returns:
        The final answer content from the AI.
    """

    answer_content = ""
    messages: List[Dict[str, str]] = []
    conversation_idx = 0

    sys_msg = {"role": "system", "content": ai_prompt}
    messages.append(sys_msg)
    user_msg = {"role": "user", "content": requirement_content}
    messages.append(user_msg)

    while True:
        print("=" * 20 + f"第{conversation_idx+1}轮对话" + "=" * 20)
        conversation_idx += 1

        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=True,
            # stream_options={"include_usage": True}  # Uncomment if needed
        )

        current_reasoning_content, current_answer_content = get_open_ai_response(
            completion
        )
        answer_content += current_answer_content
        messages.append({"role": "assistant", "content": current_answer_content})
        print("\n")

        extracted_data = extractor(current_answer_content)
        is_valid, error = validator(extracted_data)

        if is_valid:
            print("校验通过")
            break
        else:
            print(f"校验失败：{error}")
            user_msg = {"role": "user", "content": f"{error}"}
            messages.append(user_msg)

        if conversation_idx > max_iterations:
            #raise ValueError(f'AI生成内容失败，超过最大尝试次数')
            break

    return extracted_data



def get_open_ai_response(completion):
    reasoning_content = ''  # 推理过程
    answer_content = ''  # 正文回复
    for chunk in completion:
        # 如果chunk.choices为空，则打印usage
        if not chunk.choices:
            print("\nUsage:")
            print(chunk.usage)
        else:
            delta = chunk.choices[0].delta
            # 打印思考过程
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content != None:
                print(delta.reasoning_content, end='', flush=True)
                reasoning_content += delta.reasoning_content
            else:
                # 打印回复过程
                print(delta.content, end='', flush=True)
                if delta.content is not None:  # 过滤 None
                    answer_content += delta.content
    return reasoning_content, answer_content



# --- Example Calls ---

# Example 3:  Show how to change max_iterations
# ai_prompt_json = "You are a helpful assistant that generates JSON objects."
# requirement_json = "Create a JSON object with a field 'required_field'."
# final_answer_json = call_ai(
#     ai_prompt_json,
#     requirement_json,
#     extract_json_from_text,
#     validate_json_schema,
#     max_iterations=5,  # Override the default
# )
# print(f"Final Answer (JSON, with max_iterations=5):\n{final_answer_json}")
