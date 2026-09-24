# AI Agent 开发实战：从 Function Calling 到防御性工程

这是一个为期 6 周的 AI Agent 开发学习实战仓库。第一周重点攻克了 LLM API 调用、Function Calling、Prompt Engineering 以及 Pydantic 结构化输出。

## 📖 当前进度
- [x] Day 1-2: Python异步编程 & OpenAI SDK 基础
- [x] Day 3: Function Calling 实战 (计算器/天气/汇率工具)
- [x] Day 4: Prompt Engineering (CoT, Few-shot, 意图路由Router, 语气解耦)
- [x] Day 5: Pydantic 结构化输出 & 自我修正重试机制 (幻觉治理)
- [x] Day 6: 工程化进阶 (Logging、Git分支管理、递归熔断、本地兜底计算)

## 🏗️ 项目架构亮点
- **Router 意图路由**：每次请求前动态注入专属 System Prompt，彻底隔离上下文污染。
- **Pydantic 强类型校验**：拒绝模型随意输出，通过 `model_validate_json` 强约束 JSON 结构。
- **自我修正重试 (Self-Correction)**：自动捕获 `ValidationError` 并把报错喂回给模型，进行反思重试。
- **递归熔断与本地兜底**：7B 小模型“偷懒”不调用工具时，系统自动触发本地正则兜底计算，保证100%返回结果。

## 📂 文件说明
- `03.py`: 主程序入口，命令行交互循环。
- `tools_func.py`: 工具定义 (Schema)、本地函数执行、Agent 核心编排逻辑。
- `models.py`: 定义了 MathReport, WeatherReport, SecurityReport 等 Pydantic 模型。
- `prompts.py` & `router.py`: 提示词模板与意图路由逻辑。
- `logger.py`: 标准化日志系统（控制台+文件分离）。
- `知识总结.md`: Day 1-6 学习笔记与面试话术整理。

## 🚀 快速开始
1. 克隆项目: `git clone https://github.com/anyannan/ai-agent-learning.git`
2. 安装依赖: `pip install -r requirements.txt`
3. 在根目录创建 `.env` 文件并填入 API Key:
   ```env
   SILICONFLOW_API_KEY=你的Key
   SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1