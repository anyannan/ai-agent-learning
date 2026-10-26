from pydantic import BaseModel, Field

class FixRequest(BaseModel):
    source_name: str = Field(default="source.py", description="源码文件名")
    source_code: str = Field(..., description="待修复的原始代码")
    test_name: str = Field(default="test_source.py", description="测试脚本文件名")
    test_code: str = Field(..., description="测试脚本内容")

class FixResponse(BaseModel):
    success: bool
    message: str
    fixed_code: str = ""
    logs: str = ""