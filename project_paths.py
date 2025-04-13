"""项目路径配置公共模块"""
from pathlib import Path

class ProjectPaths:
    """项目路径配置"""
    # --- Base Directories ---
    base_dir: Path = Path(__file__).parent.resolve()
    ai_promote: Path = base_dir / "ai_promote"
    requirements: Path = base_dir / "requirements"
    output: Path = base_dir / "out_put_files"
    template_dir: Path = base_dir / "out_template"

    # --- AI Prompt Filenames ---
    REQ_ANALYSIS_PROMPT_FILENAME = "requirement_analysis.md"
    JSON_CONVERTER_PROMPT_FILENAME = "json_onverter_requirements.md" # Note: Original had typo 'onverter'
    REQ_DESC_PROMPT_FILENAME = "create_requirement_description.md"

    # --- Output File Prefixes/Suffixes/Patterns ---
    # Step 1: Raw Analysis
    RAW_ANALYSIS_PREFIX = "req_analysis_"
    RAW_ANALYSIS_SUFFIX = ".json"

    # Step 2: Business Text
    BUSINESS_TEXT_PREFIX = "business_"
    BUSINESS_TEXT_SUFFIX = ".txt"

    # Step 3: Processed JSON
    PROCESSED_JSON_PREFIX = "processed_"
    # Suffix is same as raw analysis (.json)

    # Step 4: Requirement Description JSON
    REQ_DESC_PREFIX = "req_description_"
    REQ_DESC_SUFFIX = ".json"

    # Step 5: Architecture Diagram
    ARCH_DIAGRAM_SUFFIX = "_architecture_diagram.png" # Appended to stem
    TEMP_MERMAID_FILENAME = "diagram.mmd" # Temporary file for mmdc

    # Step 6: Final Word Document
    FINAL_WORD_SUFFIX = "-需求说明书.docx" # Appended to stem
    WORD_TEMPLATE_FILENAME = "template.docx"
    WORD_IMAGE_PLACEHOLDER = "sequence_diagram_mermaid" # Placeholder in template

    # --- Other Prefixes (If used elsewhere) ---
    TRIGGER_EVENT_PREFIX = "trigger_events_"
