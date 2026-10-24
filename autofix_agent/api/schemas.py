# api/schemas.py
from pydantic import BaseModel, Field

class FixRequest(BaseModel):
    file_name: str = Field(..., description="原始文件名，如 demo.py")
    file_content: str = Field(..., description="待修复的原始代码内容")

class FixResponse(BaseModel):
    success: bool
    message: str
    fixed_code: str = ""
    file_name: str = ""