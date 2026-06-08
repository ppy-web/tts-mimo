# 任务计划：根据 MiMo-V2.5-TTS 文档丰富功能

## 目标
基于官方 MiMo-V2.5-TTS 文档，为当前 FastAPI TTS 项目补充可用能力：预置音色、自然语言风格控制、音频标签、文本音色设计、音色复刻，并保持现有功能可用。

## 阶段
| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| 1 | complete | 阅读项目结构与官方文档 |
| 2 | complete | 梳理现有后端、前端、测试实现 |
| 3 | complete | 修改 schema 与 TTS 服务 |
| 4 | complete | 更新 API 路由与静态页面 |
| 5 | complete | 补充测试与文档 |
| 6 | complete | 运行验证并记录结果 |

## 关键决策
- 使用官方 OpenAI 兼容接口 `/v1/chat/completions`。
- 非流式合成默认使用 `wav`；v2.5 低延迟流式尚未上线，因此本轮不新增真正流式播放。
- 文本音色设计使用 `mimo-v2.5-tts-voicedesign`，音色复刻使用 `mimo-v2.5-tts-voiceclone`。

## 错误记录
| 错误 | 处理 |
| --- | --- |
| PowerShell `Get-ChildItem -Filter` 不能传数组 | 改用逐项 `Test-Path` 检查 |
| shell 调用偶发 10s 超时但已有输出 | 后续加长超时时间或缩小命令 |
| 8000 端口已有旧 Python 服务且当前权限无法停止 | 使用 8001 启动当前版本完成页面验证 |
