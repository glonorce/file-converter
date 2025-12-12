from typing import List, Dict, Any, Optional, Union, Literal
from pydantic import BaseModel, Field

# Enums
BlockType = Literal["text", "header", "table", "image", "raw_data"]

class BaseBlock(BaseModel):
    type: BlockType
    page_number: int
    detected_lang: Optional[str] = None

class TextBlock(BaseBlock):
    type: Literal["text", "header", "raw_data"]
    content: Union[str, List[str]] # raw_data can be list of strings
    level: Optional[int] = None # For headers

class TableBlock(BaseBlock):
    type: Literal["table"]
    rows: List[List[str]]
    bbox: Optional[List[float]] = None # [x0, y0, x1, y1] for zone exclusion

class ImageBlock(BaseBlock):
    type: Literal["image"]
    path: str # Relative path to assets folder
    caption: Optional[str] = None

# Union Type for Content List
ContentItem = Union[TextBlock, TableBlock, ImageBlock]

class PageData(BaseModel):
    page_number: int
    detected_lang: str = "tr"
    width: Optional[float] = None
    height: Optional[float] = None
    content: List[ContentItem] = Field(default_factory=list)
