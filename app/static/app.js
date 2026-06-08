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

let currentObjectUrl = null;
let voiceCloneAudio = null;
const apiBase = window.location.port === "5500"
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : "";

function buildApiUrl(path) {
  return `${apiBase}${path}`;
}

function updateModeDisplay() {
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

function buildPayload({ maskCloneAudio = false } = {}) {
  const mode = modeSelect.value;
  const body = {
    mode,
    text: textInput.value.trim(),
  };

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

function updateRequestPreview() {
  requestPreview.textContent = JSON.stringify(buildPayload({ maskCloneAudio: true }), null, 2);
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

modeSelect.addEventListener("change", updateModeDisplay);
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
