# Xiaomi MiMo 本地语音工作台

这是一个基于 FastAPI 的本地语音服务，提供：

- 本地网页调试界面
- 本地 HTTP API
- 兼容 WebSocket PCM 流式接口
- 对接 Xiaomi MiMo TTS V2.5
- 对接 Xiaomi MiMo ASR V2.5
- 支持预置音色、文本音色设计、音色复刻三种模式
- 支持上传音频或浏览器录音进行语音识别
- 支持自然语言风格描述和音频标签快捷调试

## 功能说明

### TTS 文字转语音

- `preset` 模式使用官方预置音色，调用模型 `mimo-v2.5-tts`
- `voice_design` 模式通过文本描述设计音色，调用模型 `mimo-v2.5-tts-voicedesign`
- `voice_clone` 模式通过音频样本复刻音色，调用模型 `mimo-v2.5-tts-voiceclone`
- 合成文本固定放在上游请求的 `assistant` 消息中
- 风格描述会作为上游请求的 `user` 消息；音频标签应直接写入合成文本，例如 `[笑]你好`、`(四川话)今天聊点轻松的`
- 非流式合成统一返回 `wav` 音频
- 支持流式输出（SSE），前端会逐块播放 PCM16 音频，并在完成后生成可下载 WAV
- 长文本会按标点自动拆成多次上游请求，再合并为一个 `wav` 返回，降低单次请求被上游时长限制截断的概率
- WebSocket 兼容接口会把上游 `wav` 转成 `16kHz / 16-bit / mono PCM` 分片下发

### ASR 语音识别

- 语音识别调用模型 `mimo-v2.5-asr`
- TTS 和 ASR 共用同一个 `MIMO_API_KEY` 与 `MIMO_BASE_URL`
- HTTP API 统一走 `https://api.xiaomimimo.com/v1/chat/completions`
- 支持 `mp3`、`mpeg`、`wav` 音频 data URL 输入
- 支持识别语言 `auto`、`zh`、`en`，默认 `auto`
- 前端工作台可以在顶栏切换到“语音识别模式”，上传文件或直接用浏览器录音
- 识别成功后，结果文本显示在右侧“本次请求摘要”，`usage` 显示在“错误信息”区域作为元信息

## 环境要求

- Python 3.11+

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，至少填入：

```env
MIMO_API_KEY=你的小米接口密钥
```

可选项：

```env
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
MIMO_TIMEOUT_SECONDS=60
APP_HOST=127.0.0.1
APP_PORT=8000
TTS_WS_DEFAULT_MODE=preset
TTS_WS_DEFAULT_VOICE=冰糖
TTS_WS_DEFAULT_STYLE_PROMPT=温柔自然，语速适中。
TTS_WS_DEFAULT_VOICE_DESIGN_PROMPT=
TTS_WS_CHUNK_DURATION_MS=120
TTS_SEGMENT_MAX_CHARS=180
TTS_SEGMENT_PAUSE_MS=250
```

长文本合成建议：

- `TTS_SEGMENT_MAX_CHARS` 控制每段最多字符数，默认 180。语速慢、情绪强或经常被截断时可以调小；想减少上游请求次数可以适当调大。
- `TTS_SEGMENT_PAUSE_MS` 控制合并音频时每段之间插入的静音时长，默认 250ms。

## 启动

```bash
uvicorn app.main:app --reload
```

默认访问：

- 调试页: `http://127.0.0.1:8000/`
- OpenAPI: `http://127.0.0.1:8000/docs`

调试页用法：

- 默认进入 TTS 模式，可以选择合成模式、音色、风格描述、音频标签和流式输出。
- 点击顶栏的 `TTS 模式` 开关可切换到 `语音识别模式`。
- ASR 模式下选择识别语言，上传 `mp3/wav` 音频后点击 `开始识别`。
- 也可以点击 `开始录音`，浏览器授权麦克风后再次点击停止录音，再执行识别。

## Docker 部署 / 群晖 NAS

项目支持 Docker 部署，可以轻松运行在群晖 NAS 等任何支持 Docker 的设备上。

### 快速启动

```bash
# 构建镜像
docker compose build

# 启动服务（后台运行）
MIMO_API_KEY=你的密钥 docker compose up -d

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

### 群晖 NAS 部署步骤

1. **将项目文件复制到群晖**

   通过 File Station 或 SMB 将整个项目文件夹上传到群晖，例如放到 `/volume1/docker/tts-mimo/`。

2. **创建 `.env` 文件**

   在项目目录下创建 `.env` 文件，填入你的 API Key：

   ```env
   MIMO_API_KEY=你的小米MiMo API Key
   ```

3. **SSH 进群晖执行部署**

   开启群晖的 SSH（控制面板 → 终端机和 SNMP → 启用 SSH），然后：

   ```bash
   ssh 你的用户名@群晖IP
   cd /volume1/docker/tts-mimo
   sudo docker compose up -d
   ```

4. **验证服务**

   浏览器访问 `http://群晖IP:8000/` 即可看到调试页面。

### 群晖 Container Manager（图形界面）

如果不想用命令行，也可以在群晖的 **Container Manager** 中操作：

1. 打开 **Container Manager** → **项目**
2. 点击 **新建** → 选择 **从 docker-compose.yml 创建**
3. 设置路径为项目目录，Compose 文件会自动识别
4. 在 **环境** 中设置 `MIMO_API_KEY` 的值
5. 点击 **下一步** → **完成**，等待构建和启动

### 自定义端口

默认映射 `8000` 端口。如果端口冲突，修改 `docker-compose.yml` 中的端口映射：

```yaml
ports:
  - "9000:8000" # 改为 9000 或其他可用端口
```

## API

### `GET /api/v1/health`

检查服务状态和 API Key 是否已配置。

### `GET /api/v1/voices`

获取本地内置预置音色列表和支持模式。
响应中也包含音频标签示例和音色设计模板，供前端工作台生成快捷控件。

### `POST /api/v1/speech/synthesize`

请求示例：

```json
{
  "mode": "preset",
  "text": "你好，欢迎使用本地语音服务。",
  "voice": "冰糖",
  "style_prompt": "温柔自然，语速适中。"
}
```

或：

```json
{
  "mode": "voice_design",
  "text": "你好，欢迎使用本地语音服务。",
  "voice_design_prompt": "年轻女性，清亮、亲切、轻快。"
}
```

或：

```json
{
  "mode": "voice_clone",
  "text": "[笑]你好，欢迎使用本地语音服务。",
  "style_prompt": "自然、清晰，语速适中。",
  "voice_clone_audio": "data:audio/wav;base64,UklGRg..."
}
```

返回值为 `audio/wav` 二进制。

音色复刻样本要求：

- `voice_clone_audio` 必须是 `data:audio/mpeg;base64,...`、`data:audio/mp3;base64,...` 或 `data:audio/wav;base64,...`
- Base64 内容不能超过 10 MB

### `POST /api/v1/speech/recognize`

语音识别接口。请求体：

```json
{
  "audio_data": "data:audio/wav;base64,UklGRg...",
  "language": "auto"
}
```

参数说明：

- `audio_data` 必填，必须是 `data:audio/mpeg;base64,...`、`data:audio/mp3;base64,...` 或 `data:audio/wav;base64,...`
- `language` 可选，默认 `auto`，也可以传 `zh` 或 `en`
- `audio_data` 的 Base64 内容不能超过 25 MB

响应示例：

```json
{
  "text": "你好，欢迎使用本地语音识别服务。",
  "usage": {
    "seconds": 2.4,
    "audio_tokens": 128,
    "input_tokens": null,
    "output_tokens": null,
    "total_tokens": null
  }
}
```

### `WS /virtualhuman/speech/synthesis/1103`

用于兼容 wss 接口服务：

- 连接成功后立即返回字符串 `connect-success`
- 支持客户端发送 `ping`，服务端返回 `{"type":"pong"}`
- 客户端发送纯文本后，服务端会执行 TTS，并持续返回 PCM 二进制分片
- 默认用 `.env` 中的 `TTS_WS_DEFAULT_*` 作为合成参数
- 也支持在连接查询参数中覆盖，例如：
  - `ws://127.0.0.1:8000/virtualhuman/speech/synthesis/1103?mode=preset&voice=冰糖`

如果需要，也可以发送 JSON 文本覆盖参数：

```json
{
  "text": "你好，这是一段本地流式测试语音。",
  "mode": "preset",
  "voice": "冰糖",
  "style_prompt": "温柔、清晰。"
}
```

也可以发送音色复刻 JSON：

```json
{
  "text": "你好，这是一段复刻音色测试。",
  "mode": "voice_clone",
  "style_prompt": "自然清晰。",
  "voice_clone_audio": "data:audio/wav;base64,UklGRg..."
}
```

## curl 示例

TTS 合成：

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/speech/synthesize" ^
  -H "Content-Type: application/json" ^
  -o output.wav ^
  -d "{\"mode\":\"preset\",\"text\":\"你好，这是一段测试语音。\",\"voice\":\"冰糖\",\"style_prompt\":\"温柔、清晰。\"}"
```

ASR 识别：

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/speech/recognize" ^
  -H "Content-Type: application/json" ^
  -d "{\"audio_data\":\"data:audio/wav;base64,UklGRg...\",\"language\":\"auto\"}"
```

PowerShell 中可以把本地音频转成 data URL 后调用：

```powershell
$bytes = [System.IO.File]::ReadAllBytes("sample.wav")
$base64 = [Convert]::ToBase64String($bytes)
$body = @{
  audio_data = "data:audio/wav;base64,$base64"
  language = "auto"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/speech/recognize" `
  -ContentType "application/json" `
  -Body $body
```

## 测试

```bash
pytest
```
