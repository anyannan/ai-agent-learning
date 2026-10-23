from pydantic import BaseModel, Field

class FixRequest(BaseModel):
    file_content: str = Field(..., description="待修复的原始代码内容")
    requirement: str = Field(default="请检查并修复其中的安全漏洞，确保代码能通过测试。", description="修复需求")

class FixResponse(BaseModel):
    success: bool
    message: str
    fixed_code: str = ""
    logs: str = ""