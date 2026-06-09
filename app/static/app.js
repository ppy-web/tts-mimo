const modeSelect = document.getElementById("mode");
const modePill = document.getElementById("mode-pill");
const modeHint = document.getElementById("mode-hint");
const requestState = document.getElementById("request-state");
const voiceField = document.getElementById("voice-field");
const voiceSelect = document.getElementById("voice");
const textInput = document.getElementById("text");
const textCount = document.getElementById("text-count");
const compactModeText = document.getElementById("compact-mode-text");
const compactVoiceText = document.getElementById("compact-voice-text");
const compactRequestText = document.getElementById("compact-request-text");
const stylePromptField = document.getElementById("style-prompt-field");
const stylePromptInput = document.getElementById("style-prompt");
const voiceDesignTemplateField = document.getElementById("voice-design-template-field");
const voiceDesignTemplate = document.getElementById("voice-design-template");
const voiceDesignPromptField = document.getElementById("voice-design-prompt-field");
const voiceDesignPromptInput = document.getElementById("voice-design-prompt");
const voiceCloneFileField = document.getElementById("voice-clone-file-field");
const voiceCloneFileInput = document.getElementById("voice-clone-file");
const voiceCloneFileMeta = document.getElementById("voice-clone-file-meta");
const audioTagGrid = document.getElementById("audio-tag-grid");
const submitButton = document.getElementById("submit-button");
const downloadLink = document.getElementById("download-link");
const player = document.getElementById("player");
const summary = document.getElementById("summary");
const errorText = document.getElementById("error");
const requestPreview = document.getElementById("request-preview");
const streamToggle = document.getElementById("stream-toggle");
const appModeToggle = document.getElementById("app-mode-toggle");
const appModeToggleText = document.getElementById("app-mode-toggle-text");
const appModeIcon = document.querySelector(".app-mode-icon");
const ttsControls = document.querySelectorAll(".tts-control");
const asrPanel = document.getElementById("asr-panel");
const asrLanguage = document.getElementById("asr-language");
const asrFileInput = document.getElementById("asr-file");
const asrFileMeta = document.getElementById("asr-file-meta");
const asrSubmitButton = document.getElementById("asr-submit-button");
const asrRecordButton = document.getElementById("asr-record-button");

let currentObjectUrl = null;
let voiceCloneAudio = null;
let appMode = "tts";
let asrAudioData = null;
let asrRecording = null;
const apiBase = window.location.port === "5500"
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : "";

function buildApiUrl(path) {
  return `${apiBase}${path}`;
}

function updateModeDisplay() {
  if (appMode === "asr") {
    ttsControls.forEach((element) => element.classList.add("hidden"));
    asrPanel.classList.remove("hidden");
    modePill.textContent = "当前：语音识别";
    compactModeText.textContent = "语音识别";
    compactVoiceText.textContent = `语言：${getAsrLanguageLabel()}`;
    appModeToggle.classList.add("asr-active");
    appModeToggle.setAttribute("aria-pressed", "true");
    appModeToggleText.textContent = "语音识别模式";
    appModeIcon.textContent = "A";
    updateRequestPreview();
    return;
  }

  ttsControls.forEach((element) => element.classList.remove("hidden"));
  asrPanel.classList.add("hidden");
  appModeToggle.classList.remove("asr-active");
  appModeToggle.setAttribute("aria-pressed", "false");
  appModeToggleText.textContent = "TTS 模式";
  appModeIcon.textContent = "T";

  const mode = modeSelect.value;
  const isPreset = mode === "preset";
  const isVoiceDesign = mode === "voice_design";
  const isVoiceClone = mode === "voice_clone";

  voiceField.classList.toggle("hidden", !isPreset);
  stylePromptField.classList.toggle("hidden", isVoiceDesign);
  voiceDesignTemplateField.classList.toggle("hidden", !isVoiceDesign);
  voiceDesignPromptField.classList.toggle("hidden", !isVoiceDesign);
  voiceCloneFileField.classList.toggle("hidden", !isVoiceClone);

  const modeLabel = {
    preset: "预置音色",
    voice_design: "音色设计",
    voice_clone: "音色复刻",
  }[mode];
  modePill.textContent = `当前：${modeLabel}`;
  compactModeText.textContent = modeLabel;
  modeHint.textContent = {
    preset: "使用官方预置音色，适合快速验证文本内容、唱歌标签与整体说话风格。",
    voice_design: "通过文本描述生成音色，更适合做角色感、气质和人设方向的探索。",
    voice_clone: "上传 WAV/MP3 样本进行音色复刻，样本会按官方要求作为 audio.voice 发送。",
  }[mode];

  updateCompactVoiceText();
  updateRequestPreview();
}

function updateTextCount() {
  textCount.textContent = `${textInput.value.trim().length} 字`;
}

function updateRequestState(state, label) {
  requestState.className = `request-state ${state}`;
  requestState.textContent = label;
  compactRequestText.textContent = `状态：${label}`;
}

function updateCompactVoiceText() {
  if (appMode === "asr") {
    compactVoiceText.textContent = `语言：${getAsrLanguageLabel()}`;
    return;
  }

  const mode = modeSelect.value;
  if (mode === "preset") {
    const selectedOption = voiceSelect.selectedOptions[0];
    compactVoiceText.textContent = selectedOption
      ? `音色：${selectedOption.value}`
      : "音色未选择";
    return;
  }

  if (mode === "voice_clone") {
    compactVoiceText.textContent = voiceCloneAudio ? "音色：已选复刻样本" : "音色：待选复刻样本";
    return;
  }

  const hasPrompt = voiceDesignPromptInput.value.trim().length > 0;
  compactVoiceText.textContent = hasPrompt ? "音色：已写设计描述" : "音色：待写设计描述";
}

function resetDownload() {
  downloadLink.classList.add("disabled");
  downloadLink.removeAttribute("href");
  player.removeAttribute("src");
}

function setDownloadUrl(blob) {
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl);
  }
  currentObjectUrl = URL.createObjectURL(blob);
  downloadLink.href = currentObjectUrl;
  downloadLink.classList.remove("disabled");
  player.src = currentObjectUrl;
}

function setPlayerPreview(blob) {
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl);
  }
  currentObjectUrl = URL.createObjectURL(blob);
  player.src = currentObjectUrl;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result));
    reader.addEventListener("error", () => reject(new Error("无法读取音频样本。")));
    reader.readAsDataURL(file);
  });
}

function getModeLabel(mode) {
  return {
    preset: "预置音色",
    voice_design: "音色设计",
    voice_clone: "音色复刻",
  }[mode] || mode;
}

function getAsrLanguageLabel() {
  return {
    auto: "自动检测",
    zh: "中文",
    en: "英文",
  }[asrLanguage.value] || asrLanguage.value;
}

function buildPayload({ maskCloneAudio = false } = {}) {
  const mode = modeSelect.value;
  const body = {
    mode,
    text: textInput.value.trim(),
  };

  if (streamToggle && streamToggle.checked) {
    body.stream = true;
  }

  if (mode === "preset") {
    body.voice = voiceSelect.value;
    const stylePrompt = stylePromptInput.value.trim();
    if (stylePrompt) {
      body.style_prompt = stylePrompt;
    }
  } else if (mode === "voice_design") {
    body.voice_design_prompt = voiceDesignPromptInput.value.trim();
  } else {
    const stylePrompt = stylePromptInput.value.trim();
    if (stylePrompt) {
      body.style_prompt = stylePrompt;
    }
    if (voiceCloneAudio) {
      body.voice_clone_audio = maskCloneAudio ? "[已选择音频样本 data URI]" : voiceCloneAudio;
    }
  }

  return body;
}

function buildAsrPayload({ maskAudioData = false } = {}) {
  return {
    audio_data: asrAudioData
      ? (maskAudioData ? "[已选择音频 data URI]" : asrAudioData)
      : "",
    language: asrLanguage.value,
  };
}

function updateRequestPreview() {
  const payload = appMode === "asr"
    ? buildAsrPayload({ maskAudioData: true })
    : buildPayload({ maskCloneAudio: true });
  requestPreview.textContent = JSON.stringify(payload, null, 2);
}

function insertTextAtCursor(input, value) {
  const start = input.selectionStart ?? input.value.length;
  const end = input.selectionEnd ?? input.value.length;
  input.value = `${input.value.slice(0, start)}${value}${input.value.slice(end)}`;
  input.focus();
  const nextPosition = start + value.length;
  input.setSelectionRange(nextPosition, nextPosition);
  updateTextCount();
  updateRequestPreview();
}

async function loadVoices() {
  const response = await fetch(buildApiUrl("/api/v1/voices"));
  if (!response.ok) {
    throw new Error("无法加载音色列表。");
  }

  const data = await response.json();
  voiceSelect.innerHTML = "";

  data.voices.forEach((voice) => {
    const option = document.createElement("option");
    option.value = voice.value;
    option.textContent = `${voice.label} / ${voice.language} / ${voice.gender}`;
    voiceSelect.appendChild(option);
  });

  if (Array.isArray(data.audio_tag_examples) && data.audio_tag_examples.length) {
    audioTagGrid.innerHTML = "";
    data.audio_tag_examples.forEach((example) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.tag = example.match(/^(\([^)]+\)|\[[^\]]+\])/)?.[0] || example;
      button.textContent = button.dataset.tag.replace(/[()[\]]/g, "");
      audioTagGrid.appendChild(button);
    });
  }

  if (Array.isArray(data.voice_design_templates) && data.voice_design_templates.length) {
    voiceDesignTemplate.innerHTML = '<option value="">自定义描述</option>';
    data.voice_design_templates.forEach((template) => {
      const option = document.createElement("option");
      option.value = template.value;
      option.textContent = template.name;
      voiceDesignTemplate.appendChild(option);
    });
  }
}

async function synthesize() {
  if (streamToggle && streamToggle.checked) {
    return synthesizeStream();
  }
  return synthesizeNonStream();
}

async function synthesizeStream() {
  errorText.textContent = "当前没有错误。";

  const mode = modeSelect.value;
  const body = buildPayload();

  submitButton.disabled = true;
  submitButton.textContent = "流式生成中...";
  summary.textContent = "SSE 流式请求已发送，正在逐步接收并播放音频。";
  updateRequestState("loading", "流式生成中");
  resetDownload();

  let audioCtx = null;
  let playbackTime = 0;
  let totalBytes = 0;
  let chunkCount = 0;
  let aborted = false;

  try {
    const response = await fetch(buildApiUrl("/api/v1/speech/synthesize"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      let message = "生成失败。";
      try {
        const detail = await response.json();
        if (detail && detail.detail) {
          message = detail.detail;
        }
      } catch { /* ignore */ }
      throw new Error(message);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = "";
    const allPcmChunks = [];

    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    playbackTime = audioCtx.currentTime + 0.1;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      sseBuffer += decoder.decode(value, { stream: true });
      const lines = sseBuffer.split("\n");
      sseBuffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const dataStr = trimmed.slice(5).trim();

        if (dataStr === "[DONE]") {
          continue;
        }

        let parsed;
        try {
          parsed = JSON.parse(dataStr);
        } catch {
          continue;
        }

        if (parsed.error) {
          throw new Error(parsed.error);
        }

        if (parsed.audio) {
          const raw = atob(parsed.audio);
          const pcmBytes = new Uint8Array(raw.length);
          for (let i = 0; i < raw.length; i++) {
            pcmBytes[i] = raw.charCodeAt(i);
          }
          allPcmChunks.push(pcmBytes);
          totalBytes += pcmBytes.length;
          chunkCount++;

          const int16 = new Int16Array(pcmBytes.buffer, pcmBytes.byteOffset, pcmBytes.length / 2);
          const float32 = new Float32Array(int16.length);
          for (let i = 0; i < int16.length; i++) {
            float32[i] = int16[i] / 32768.0;
          }

          const audioBuffer = audioCtx.createBuffer(1, float32.length, 24000);
          audioBuffer.getChannelData(0).set(float32);
          const source = audioCtx.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(audioCtx.destination);
          source.start(playbackTime);
          playbackTime += audioBuffer.duration;

          summary.textContent = `流式接收中：${chunkCount} 个数据块，共 ${(totalBytes / 1024).toFixed(1)} KB。`;
        }
      }
    }

    // Build WAV for download from collected chunks
    const totalLength = allPcmChunks.reduce((sum, c) => sum + c.length, 0);
    const merged = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of allPcmChunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }

    const wavBlob = pcm16ToWavBlob(merged, 24000);
    setDownloadUrl(wavBlob);

    summary.textContent = `流式生成成功：${getModeLabel(mode)} 模式，${chunkCount} 个数据块，音频大小 ${(totalBytes / 1024).toFixed(1)} KB。`;
    errorText.textContent = "当前没有错误。";
    updateRequestState("success", "已完成");
  } catch (error) {
    if (audioCtx) {
      try { audioCtx.close(); } catch { /* ignore */ }
    }
    errorText.textContent = error instanceof Error ? error.message : "发生未知错误。";
    summary.textContent = "流式请求未成功完成，请检查输入参数或本地服务日志。";
    updateRequestState("error", "失败");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "生成语音";
  }
}

function pcm16ToWavBlob(pcmData, sampleRate) {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const wavHeaderSize = 44;
  const buffer = new ArrayBuffer(wavHeaderSize + pcmData.length);
  const view = new DataView(buffer);

  function writeString(offset, str) {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  }

  writeString(0, "RIFF");
  view.setUint32(4, 36 + pcmData.length, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeString(36, "data");
  view.setUint32(40, pcmData.length, true);
  new Uint8Array(buffer, wavHeaderSize).set(pcmData);

  return new Blob([buffer], { type: "audio/wav" });
}

async function synthesizeNonStream() {
  errorText.textContent = "当前没有错误。";

  const mode = modeSelect.value;
  const body = buildPayload();

  submitButton.disabled = true;
  submitButton.textContent = "生成中...";
  summary.textContent = "请求已发送，正在等待本地服务返回音频数据。";
  updateRequestState("loading", "生成中");
  resetDownload();

  try {
    const response = await fetch(buildApiUrl("/api/v1/speech/synthesize"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      let message = "生成失败。";
      try {
        const detail = await response.json();
        if (detail && detail.detail) {
          message = detail.detail;
        }
      } catch {
        // Ignore JSON parse errors and keep fallback message.
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    setDownloadUrl(blob);
    player.play().catch(() => {});

    summary.textContent = `生成成功：${getModeLabel(mode)} 模式，音频大小 ${(blob.size / 1024).toFixed(1)} KB。`;
    errorText.textContent = "当前没有错误。";
    updateRequestState("success", "已完成");
  } catch (error) {
    errorText.textContent = error instanceof Error ? error.message : "发生未知错误。";
    summary.textContent = "请求未成功完成，请检查输入参数或本地服务日志。";
    updateRequestState("error", "失败");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "生成语音";
  }
}

async function recognize() {
  errorText.classList.remove("meta-info");
  errorText.textContent = "当前没有错误。";

  if (!asrAudioData) {
    errorText.textContent = "请先选择或录制一段 MP3/WAV 音频。";
    summary.textContent = "语音识别尚未开始。";
    updateRequestState("error", "缺少音频");
    return;
  }

  const body = buildAsrPayload();
  asrSubmitButton.disabled = true;
  asrSubmitButton.textContent = "识别中...";
  summary.textContent = "请求已发送，正在等待本地服务返回识别文本。";
  updateRequestState("loading", "识别中");
  updateRequestPreview();

  try {
    const response = await fetch(buildApiUrl("/api/v1/speech/recognize"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      let message = "识别失败。";
      try {
        const detail = await response.json();
        if (detail && detail.detail) {
          message = detail.detail;
        }
      } catch {
        // Ignore JSON parse errors and keep fallback message.
      }
      throw new Error(message);
    }

    const data = await response.json();
    summary.textContent = data.text || "识别成功，但结果为空。";
    errorText.classList.add("meta-info");
    errorText.textContent = formatUsage(data.usage);
    updateRequestState("success", "已识别");
  } catch (error) {
    errorText.classList.remove("meta-info");
    errorText.textContent = error instanceof Error ? error.message : "发生未知错误。";
    summary.textContent = "语音识别未成功完成，请检查音频格式或本地服务日志。";
    updateRequestState("error", "失败");
  } finally {
    asrSubmitButton.disabled = false;
    asrSubmitButton.textContent = "开始识别";
  }
}

function formatUsage(usage) {
  if (!usage || typeof usage !== "object" || !Object.keys(usage).length) {
    return "Usage：上游未返回用量信息。";
  }

  const pairs = Object.entries(usage)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${value}`);

  return pairs.length ? `Usage：${pairs.join("，")}` : "Usage：上游未返回用量信息。";
}

async function handleAsrFileChange() {
  const file = asrFileInput.files[0];
  asrAudioData = null;
  errorText.classList.remove("meta-info");

  if (!file) {
    asrFileMeta.textContent = "未选择待识别音频";
    updateRequestPreview();
    return;
  }

  if (file.size > 18 * 1024 * 1024) {
    asrFileMeta.textContent = "音频过大，建议选择 Base64 后不超过 25 MB 的文件。";
    updateRequestPreview();
    return;
  }

  try {
    asrAudioData = await readFileAsDataUrl(file);
    asrFileMeta.textContent = `${file.name} / ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    setPlayerPreview(file);
  } catch (error) {
    asrFileMeta.textContent = error instanceof Error ? error.message : "无法读取待识别音频。";
  }

  updateRequestPreview();
}

async function toggleAsrRecording() {
  if (asrRecording) {
    await stopAsrRecording();
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    errorText.classList.remove("meta-info");
    errorText.textContent = "当前浏览器不支持录音，请改为上传音频文件。";
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const audioContext = new AudioContextClass();
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    const chunks = [];

    processor.onaudioprocess = (event) => {
      chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    asrRecording = {
      stream,
      audioContext,
      source,
      processor,
      chunks,
      sampleRate: audioContext.sampleRate,
      startedAt: Date.now(),
    };

    asrRecordButton.textContent = "停止录音";
    asrRecordButton.classList.add("recording");
    asrFileMeta.textContent = "录音中...";
    updateRequestState("loading", "录音中");
  } catch (error) {
    errorText.classList.remove("meta-info");
    errorText.textContent = error instanceof Error ? error.message : "无法启动浏览器录音。";
  }
}

async function stopAsrRecording() {
  const recording = asrRecording;
  if (!recording) {
    return;
  }

  asrRecording = null;
  recording.processor.disconnect();
  recording.source.disconnect();
  recording.stream.getTracks().forEach((track) => track.stop());
  await recording.audioContext.close();

  const samples = mergeFloat32Chunks(recording.chunks);
  const wavBlob = encodeWavBlob(samples, recording.sampleRate);
  const durationSeconds = Math.max(0.1, (Date.now() - recording.startedAt) / 1000);

  asrAudioData = await readFileAsDataUrl(wavBlob);
  setPlayerPreview(wavBlob);
  asrFileInput.value = "";
  asrFileMeta.textContent = `浏览器录音 / ${durationSeconds.toFixed(1)} 秒 / ${(wavBlob.size / 1024).toFixed(1)} KB`;
  asrRecordButton.textContent = "开始录音";
  asrRecordButton.classList.remove("recording");
  updateRequestState("idle", "待识别");
  updateRequestPreview();
}

function mergeFloat32Chunks(chunks) {
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const result = new Float32Array(totalLength);
  let offset = 0;
  chunks.forEach((chunk) => {
    result.set(chunk, offset);
    offset += chunk.length;
  });
  return result;
}

function encodeWavBlob(samples, sampleRate) {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataLength = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  function writeString(offset, value) {
    for (let i = 0; i < value.length; i++) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  }

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeString(36, "data");
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

modeSelect.addEventListener("change", updateModeDisplay);
appModeToggle.addEventListener("click", async () => {
  if (appMode === "asr" && asrRecording) {
    await stopAsrRecording();
  }
  appMode = appMode === "tts" ? "asr" : "tts";
  errorText.classList.remove("meta-info");
  updateModeDisplay();
});
voiceSelect.addEventListener("change", () => {
  updateCompactVoiceText();
  updateRequestPreview();
});
stylePromptInput.addEventListener("input", updateRequestPreview);
voiceDesignPromptInput.addEventListener("input", () => {
  updateCompactVoiceText();
  updateRequestPreview();
});
voiceDesignTemplate.addEventListener("change", () => {
  if (voiceDesignTemplate.value) {
    voiceDesignPromptInput.value = voiceDesignTemplate.value;
  }
  updateCompactVoiceText();
  updateRequestPreview();
});
voiceCloneFileInput.addEventListener("change", async () => {
  const file = voiceCloneFileInput.files[0];
  voiceCloneAudio = null;
  if (!file) {
    voiceCloneFileMeta.textContent = "未选择音频样本";
    updateCompactVoiceText();
    updateRequestPreview();
    return;
  }

  if (file.size > 7.5 * 1024 * 1024) {
    voiceCloneFileMeta.textContent = "样本过大，建议选择 Base64 后不超过 10 MB 的音频。";
    updateCompactVoiceText();
    updateRequestPreview();
    return;
  }

  try {
    voiceCloneAudio = await readFileAsDataUrl(file);
    voiceCloneFileMeta.textContent = `${file.name} / ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  } catch (error) {
    voiceCloneFileMeta.textContent = error instanceof Error ? error.message : "无法读取音频样本。";
  }
  updateCompactVoiceText();
  updateRequestPreview();
});
audioTagGrid.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tag]");
  if (!button) {
    return;
  }
  insertTextAtCursor(textInput, button.dataset.tag);
});
textInput.addEventListener("input", () => {
  updateTextCount();
  updateRequestPreview();
});
submitButton.addEventListener("click", synthesize);
if (streamToggle) {
  streamToggle.addEventListener("change", updateRequestPreview);
}
asrLanguage.addEventListener("change", () => {
  updateCompactVoiceText();
  updateRequestPreview();
});
asrFileInput.addEventListener("change", handleAsrFileChange);
asrSubmitButton.addEventListener("click", recognize);
asrRecordButton.addEventListener("click", toggleAsrRecording);

loadVoices()
  .then(() => {
    updateModeDisplay();
    updateTextCount();
    updateRequestState("idle", "空闲");
    updateCompactVoiceText();
    updateRequestPreview();
  })
  .catch((error) => {
    errorText.textContent = error instanceof Error ? error.message : "初始化失败。";
    summary.textContent = "初始化未完成，音色列表加载失败。";
    updateRequestState("error", "初始化失败");
  });
