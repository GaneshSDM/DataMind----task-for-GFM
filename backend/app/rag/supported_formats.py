"""
Supported file extensions for RAG ingestion.
Add new entries here + implement a handler in extractor.py.
"""

# Set of accepted file extensions (lowercase)
SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.csv', '.md', '.xlsx'}

# Human-readable name per extension
EXTENSION_LABELS = {
    '.pdf':  'PDF',
    '.docx': 'Word Document',
    '.txt':  'Plain Text',
    '.csv':  'CSV',
    '.md':   'Markdown',
    '.xlsx': 'Excel Spreadsheet',
}

def is_supported(filename: str) -> bool:
    ext = _ext(filename)
    return ext in SUPPORTED_EXTENSIONS

def get_label(filename: str) -> str:
    return EXTENSION_LABELS.get(_ext(filename), 'Unknown')

def _ext(filename: str) -> str:
    import os
    return os.path.splitext(filename.lower())[1]
