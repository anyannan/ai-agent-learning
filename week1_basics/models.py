from pydantic import BaseModel, Field
from typing import List, Optional, Union
# 1. 定义“天气播报”结构
class WeatherReport(BaseModel):
    city: str = Field(description="城市名称")
    temperature: int = Field(description="温度，纯数字，不带℃")
    weather: str = Field(description="天气状况，如晴、多云")
    suggestion: str = Field(description="生活建议，如穿衣、带伞")
    pirate_tone_summary: str = Field(description="海盗语气的总结汇报")

# 2. 定义“数学计算”结构
class MathReport(BaseModel):
    reasoning: str = Field(description="详细的推理过程，如果有多步，请用分号隔开")
    operation: str = Field(description="运算类型，如果是多步，写 'multi-step'")
    result: Union[int,float] = Field(description="最终单一结果，纯数字")
    intermediate_steps: List[str] = Field(description="直接提取工具返回的文字说明，严禁自己脑补算式或计算过程，原样粘贴即可")
    pirate_tone_summary: str = Field(description="海盗语气的情绪表达。绝对禁止提及任何计算数字，例如只输出：'啊哈！这可是不少银子啊！啊哈哈哈！'")

# 3. 定义“网络安全”结构（为你第四周RAG项目铺垫）
class SecurityReport(BaseModel):
    conclusion: str = Field(description="结论")
    principle: str = Field(description="漏洞原理")
    fixes: List[str] = Field(description="修复建议列表")
    risk_level: str = Field(description="风险等级：高危/中危/低危")