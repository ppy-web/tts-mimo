# 调研记录

## 官方文档摘录
- 官方文档地址：https://platform.xiaomimimo.com/docs/zh-CN/usage-guide/speech-synthesis-v2.5
- 三个模型：
  - `mimo-v2.5-tts`：预置音色，支持唱歌，不支持音色设计与音色复刻。
  - `mimo-v2.5-tts-voicedesign`：通过文本描述定制音色，不支持唱歌、预置音色、复刻。
  - `mimo-v2.5-tts-voiceclone`：通过音频样本复刻音色，不支持唱歌、预置音色、音色设计。
- 目标合成文本必须放在 `role: assistant` 消息中。
- `role: user` 消息可选，用于自然语言风格控制；使用 voicedesign 时必填。
- 音频标签控制放在 `assistant` 文本中，可用 `(风格)`、`[音频标签]` 等形式。
- v2.5 TTS 低延迟流式输出暂未上线，流式目前为兼容模式。
- 预置音色：`mimo_default`、`冰糖`、`茉莉`、`苏打`、`白桦`、`Mia`、`Chloe`、`Milo`、`Dean`。
- 音色复刻样本需 base64 data URI 前缀，支持 `audio/mpeg`、`audio/mp3`、`audio/wav`，编码后不超过 10 MB。

## 风格控制
- 自然语言控制适合整体风格和导演模式。
- 标签控制支持基础情绪、复合情绪、语调、音色定位、人设腔调、方言、角色扮演、唱歌。
- 细粒度音频标签支持吸气、叹气、紧张、疲惫、颤抖、笑、哽咽等。
