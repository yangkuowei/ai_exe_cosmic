import os
from typing import Union
from pathlib import Path

def read_word_document(file_path: str) -> str:
    """读取Word文档内容"""
    from read_file_content import read_word_document as read_doc
    return read_doc(file_path)

def save_content_to_file(
    file_name: str,
    output_dir: str,
    content: Union[str, dict],
    content_type: str = "text"
) -> None:
    """保存内容到文件"""
    from read_file_content import save_content_to_file as save_file
    save_file(file_name, output_dir, content, content_type)
