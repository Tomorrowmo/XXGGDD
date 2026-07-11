let llmChatMessages = [];
let llmRunning = false;
let chatMessages = [];     // [{role, content}]
let vlmRunning = false;
let allChannels = [];       // [{index, label, header}]
let currentFilename = '';
function uploadFile(file) {
    const zone = document.getElementById('upload-zone');
    const statusEl = document.getElementById('upload-status');
    const fill = document.getElementById('progress-fill');
    const text = document.getElementById('progress-text');
    const detail = document.getElementById('progress-detail');

    // 进入上传状态
    zone.classList.add('uploading');
    zone.classList.remove('success');
    fill.style.width = '0%';
    text.textContent = '准备上传...';
    detail.textContent = `${file.name}（${formatSize(file.size)}）`;
    if (statusEl) statusEl.style.display = 'none';

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');

    xhr.upload.addEventListener('progress', e => {
        if (e.lengthComputable) {
            const pct = Math.round(e.loaded / e.total * 100);
            fill.style.width = pct + '%';
            text.textContent = pct + '%';
            detail.textContent = `${formatSize(e.loaded)} / ${formatSize(e.total)}`;
        }
    });

    xhr.addEventListener('load', () => {
        zone.classList.remove('uploading');
        try {
            const result = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300 && !result.error) {
                zone.classList.add('success');
                document.querySelector('.upload-zone .uicon').textContent = '✅';
                if (statusEl) {
                    statusEl.style.display = 'block';
                    statusEl.innerHTML = `<div class="placeholder" style="border-color:#22c55e;color:#16a34a;">✅ ${result.message}（${formatSize(result.size_bytes)}）</div>`;
                }
                document.getElementById('file-input').value = '';
                loadFileList();
                refreshFileSelector();
                // 3秒后恢复
                setTimeout(() => {
                    zone.classList.remove('success');
                    document.querySelector('.upload-zone .uicon').textContent = '📁';
                }, 3000);
            } else {
                text.textContent = '❌ 上传失败';
                detail.textContent = result.error || result.detail || '未知错误';
                if (statusEl) {
                    statusEl.innerHTML = `<div class="placeholder" style="border-color:#ef4444;color:#dc2626;">❌ 上传失败：${result.error || result.detail}</div>`;
                    statusEl.style.display = 'block';
                }
            }
        } catch (e) {
            text.textContent = '❌ 解析响应失败';
            detail.textContent = e.message;
        }
    });

    xhr.addEventListener('error', () => {
        zone.classList.remove('uploading');
        text.textContent = '❌ 网络错误';
        detail.textContent = '请检查服务器连接';
    });

    xhr.send(formData);
}

async function loadFileList() {
    const listEl = document.getElementById('file-list');
    try {
        const resp = await fetch('/api/files');
        const data = await resp.json();
        if (data.files && data.files.length > 0) {
            listEl.innerHTML = data.files.map(f =>
                `<div class="file-list-item">
                    <span>📄 ${f.name} <span style="font-size:0.75rem;opacity:0.5;">(${formatSize(f.size_bytes)})</span></span>
                    <span class="file-actions">
                        <button onclick="renameFile('${f.name.replace(/'/g, "\\'")}')">✏️ 重命名</button>
                        <button onclick="deleteFile('${f.name.replace(/'/g, "\\'")}')">🗑 删除</button>
                    </span>
                </div>`
            ).join('');
        } else {
            listEl.innerHTML = '暂无文件';
        }
    } catch (e) {
        listEl.innerHTML = '加载失败';
    }
}

async function renameFile(oldName) {
    const newName = prompt('输入新文件名：', oldName);
    if (!newName || newName === oldName) return;
    try {
        const resp = await fetch(`/api/files/${encodeURIComponent(oldName)}/rename`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_name: newName }),
        });
        const result = await resp.json();
        if (resp.ok) {
            loadFileList();
        } else {
            alert('重命名失败：' + (result.error || result.detail));
        }
    } catch (e) {
        alert('重命名失败：' + e.message);
    }
}

async function deleteFile(filename) {
    if (!confirm(`确定删除 ${filename}？`)) return;
    try {
        const resp = await fetch(`/api/files/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const result = await resp.json();
        if (resp.ok) {
            loadFileList();
        } else {
            alert('删除失败：' + (result.error || result.detail));
        }
    } catch (e) {
        alert('删除失败：' + e.message);
    }
}
// ==========================================================================
// LLM / VLM 模型选择器 — 试验分析
// ==========================================================================
async function loadExpModels() {
    try {
        const r = await fetch('/api/ragflow/models');
        const models = await r.json();
        const llmSel = _('llm-model-select');
        if (llmSel) {
            llmSel.innerHTML = '';
            const llmModels = models.filter(m => !m.multimodal);
            (llmModels.length ? llmModels : models).forEach(m => {
                const o = document.createElement('option');
                o.value = m.id; o.textContent = m.id;
                if (m.id === 'deepseek/deepseek-v4-flash') o.selected = true;
                llmSel.appendChild(o);
            });
        }
        const vlmSel = _('vlm-model-select');
        if (vlmSel) {
            vlmSel.innerHTML = '';
            const vlmModels = models.filter(m => m.multimodal);
            if (!vlmModels.length) { vlmSel.innerHTML = '<option value="">-- 无可用 VLM --</option>'; return; }
            vlmModels.sort((a, b) => (a.provider==='local' && b.provider!=='local') ? -1 : (a.provider!=='local' && b.provider==='local') ? 1 : 0);
            vlmModels.forEach(m => {
                const o = document.createElement('option');
                o.value = m.id; o.textContent = m.id;
                if (m.id === 'local/vllm_Qwen2.5-VL-7B') o.selected = true;
                vlmSel.appendChild(o);
            });
        }
    } catch(e) {}
}

function appendLLMBubble(role, html) {
    const box = document.getElementById('llm-chat-box');
    const ph = document.getElementById('llm-chat-placeholder');
    if (ph) ph.style.display = 'none';
    const div = document.createElement('div');
    div.className = 'chat-msg ' + role;
    div.innerHTML = html;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

async function startLLMDiagnosis() {
    if (llmRunning || !currentFilename) return;
    llmRunning = true;

    const btn = document.getElementById('btn-llm-diagnose');
    btn.disabled = true;
    btn.textContent = '⏳ 诊断中...';

    document.getElementById('llm-chat-box').innerHTML = '';
    llmChatMessages = [];

    const userMsg = `请对数据文件 ${currentFilename} 进行诊断分析`;
    llmChatMessages.push({ role: 'user', content: userMsg });
    appendLLMBubble('user', userMsg);

    document.getElementById('btn-llm-send').disabled = false;

    const loading = document.getElementById('llm-chat-loading');
    loading.textContent = '🧠 DeepSeek 分析中...';
    const bubble = appendLLMBubble('assistant', '');
    let rawText = '';

    try {
        const resp = await fetch('/api/llm/diagnose', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: currentFilename, model_id: _('llm-model-select').value }),
        });
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop() || '';
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) {
                        rawText += data.text;
                        bubble.innerHTML = marked.parse(rawText);
                        document.getElementById('llm-chat-box').scrollTop = document.getElementById('llm-chat-box').scrollHeight;
                        loading.textContent = '🟢 输出中...';
                    } else if (data.done) {
                        loading.textContent = '';
                    } else if (data.error) {
                        loading.textContent = '❌ ' + data.error;
                    }
                }
            }
        }
    } catch (e) {
        loading.textContent = '❌ 连接失败：' + e.message;
    }

    if (rawText) llmChatMessages.push({ role: 'assistant', content: rawText });
    loading.textContent = '';
    btn.disabled = false;
    btn.textContent = '🤖 开始诊断';
    llmRunning = false;
}

async function sendLLMMessage() {
    if (llmRunning) return;
    const input = document.getElementById('llm-chat-input');
    const text = input.value.trim();
    if (!text) return;

    if (llmChatMessages.length >= 10) llmChatMessages = llmChatMessages.slice(-9);
    llmChatMessages.push({ role: 'user', content: text });
    appendLLMBubble('user', text);
    input.value = '';

    llmRunning = true;
    document.getElementById('btn-llm-send').disabled = true;
    const loading = document.getElementById('llm-chat-loading');
    loading.textContent = '🧠 思考中...';
    const bubble = appendLLMBubble('assistant', '');
    let rawText = '';

    try {
        // 传入对话历史（不含最后一条刚加的 user 消息之前的 system 角色消息）
        // diagnose_data 会将数据摘要 + 历史对话一起发给 LLM
        const resp = await fetch('/api/llm/diagnose', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: currentFilename,
                messages: llmChatMessages,
                model_id: _('llm-model-select').value,
            }),
        });
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop() || '';
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const d = JSON.parse(line.slice(6));
                    if (d.text) { rawText += d.text; bubble.innerHTML = marked.parse(rawText); }
                    else if (d.done) loading.textContent = '';
                    else if (d.error) loading.textContent = '❌ ' + d.error;
                }
            }
        }
    } catch (e) {
        loading.textContent = '❌ ' + e.message;
    }
    if (rawText) llmChatMessages.push({ role: 'assistant', content: rawText });
    loading.textContent = '';
    document.getElementById('btn-llm-send').disabled = false;
    llmRunning = false;
}
const MAX_CONTEXT = 10;    // 最多 10 条消息（5 轮）

function appendChatBubble(role, html) {
    const box = document.getElementById('chat-box');
    const ph = document.getElementById('chat-placeholder');
    if (ph) ph.style.display = 'none';
    const div = document.createElement('div');
    div.className = 'chat-msg ' + role;
    div.innerHTML = html;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

async function startVLMAnalysis() {
    if (vlmRunning) return;
    vlmRunning = true;

    const btn = document.getElementById('btn-vlm-start');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = '⏳ 分析中...';

    document.getElementById('btn-send').disabled = false;  // 允许后续对话

    // 清空聊天
    document.getElementById('chat-box').innerHTML = '';
    chatMessages = [];

    // 发初始消息
    const userMsg = '请分析这张航天发动机试验的压力曲线图。';
    chatMessages.push({ role: 'user', content: userMsg });
    appendChatBubble('user', userMsg);

    await streamChatResponse();
    btn.disabled = false;
    btn.textContent = '开始分析';
    vlmRunning = false;
}

async function sendChatMessage() {
    if (vlmRunning) return;

    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;

    // 截断上下文
    if (chatMessages.length >= MAX_CONTEXT) {
        chatMessages = chatMessages.slice(-MAX_CONTEXT + 1);
    }

    chatMessages.push({ role: 'user', content: text });
    appendChatBubble('user', text);
    input.value = '';
    input.focus();

    vlmRunning = true;
    document.getElementById('btn-send').disabled = true;
    await streamChatResponse();
    document.getElementById('btn-send').disabled = false;
    vlmRunning = false;
}

async function streamChatResponse() {
    const loading = document.getElementById('chat-loading');
    loading.textContent = '🤖 思考中...';

    // 创建空的助手气泡
    const bubble = appendChatBubble('assistant', '');
    let rawText = '';

    try {
        const resp = await fetch('/api/vlm/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: chatMessages, model_id: _('vlm-model-select').value }),
        });
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop() || '';
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) {
                        rawText += data.text;
                        bubble.innerHTML = marked.parse(rawText);
                        document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;
                        loading.textContent = '🟢 输出中...';
                    } else if (data.done) {
                        loading.textContent = '';
                    } else if (data.error) {
                        loading.textContent = '❌ ' + data.error;
                    }
                }
            }
        }
    } catch (e) {
        loading.textContent = '❌ 连接失败：' + e.message;
    }

    if (rawText) {
        chatMessages.push({ role: 'assistant', content: rawText });
    }
    loading.textContent = '';
}
// ==========================================================================
// 数据分析 — 文件列表填充
// ==========================================================================
async function refreshFileSelector() {
    const select = document.getElementById('data-file-select');
    const hint = document.getElementById('hint-file-count');
    try {
        const resp = await fetch('/api/files');
        const data = await resp.json();
        select.innerHTML = '<option value="">-- 选择已上传的文件 --</option>';
        if (data.files && data.files.length > 0) {
            data.files.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.name;
                opt.textContent = `${f.name} (${formatSize(f.size_bytes)})`;
                select.appendChild(opt);
            });
            hint.textContent = `共 ${data.files.length} 个可用文件`;
        } else {
            hint.textContent = '暂无文件，请先在上方上传区上传试验数据';
        }
    } catch (e) {
        hint.textContent = '加载失败';
    }
}

// ==========================================================================
// 加载数据文件 Header
// ==========================================================================
async function loadDataFile() {
    const select = document.getElementById('data-file-select');
    const filename = select.value;
    if (!filename) { alert('请先选择一个文件'); return; }

    document.getElementById('btn-load-data').disabled = true;
    document.getElementById('btn-load-data').textContent = '⏳ 加载中...';

    try {
        const resp = await fetch(`/api/data/info?filename=${encodeURIComponent(filename)}`);
        const data = await resp.json();
        if (data.error) { alert('加载失败：' + data.error); return; }

        // 显示概览
        document.getElementById('data-overview').style.display = 'block';
        document.getElementById('stat-name').textContent = data.filename;
        document.getElementById('stat-cols').textContent = data.column_count;
        document.getElementById('stat-rows').textContent = data.data_rows.toLocaleString();
        document.getElementById('stat-hidx').textContent = data.header_index;
        document.getElementById('stat-size').textContent = formatSize(data.size_bytes);

        // 填充 header 表格
        const tbody = document.getElementById('header-tbody');
        tbody.innerHTML = data.headers.map((h, i) =>
            `<tr><td class="col-idx">${i}</td><td>${h}</td></tr>`
        ).join('');

        // 隐藏之前展开的面板
        document.querySelectorAll('.analysis-panel').forEach(p => p.style.display = 'none');
        document.querySelectorAll('.action-btn').forEach(b => b.classList.remove('active'));

        // 加载通道列表
        await loadChannels(data.filename);

        // 更新底栏
        updateStatus(filename);
        document.getElementById('btn-load-data').textContent = '📋 加载数据';
    } catch (e) {
        alert('加载失败：' + e.message);
    } finally {
        document.getElementById('btn-load-data').disabled = false;
    }
}

// Header 搜索过滤
function filterHeaders() {
    const kw = document.getElementById('header-filter').value.toLowerCase();
    document.querySelectorAll('#header-tbody tr').forEach(tr => {
        tr.classList.toggle('hidden', kw && !tr.textContent.toLowerCase().includes(kw));
    });
}

// ==========================================================================
// 图表 — 通道选择器
// ==========================================================================

// ==========================================================================
// 面板互斥切换
// ==========================================================================
function switchAnalysisPanel(panelId) {
    // 更新按钮高亮
    document.querySelectorAll('.action-btn').forEach(b => {
        b.classList.remove('active');
        if (b.id === 'btn-' + panelId) b.classList.add('active');
    });

    // 互斥显示：隐藏所有面板，显示选中的
    document.querySelectorAll('.analysis-panel').forEach(p => {
        p.style.display = p.id === 'panel-' + panelId ? 'block' : 'none';
    });
}

// data load 时调用，填充通道列表
async function loadChannels(filename) {
    currentFilename = filename;
    try {
        const resp = await fetch(`/api/chart/channels?filename=${encodeURIComponent(filename)}`);
        const data = await resp.json();
        if (data.error) { console.error(data.error); return; }
        allChannels = data.channels;

        const list = document.getElementById('chan-list');
        // 默认选中流道22-26
        const defaults = ['流道22', '流道23', '流道24', '流道25', '流道26'];

        list.innerHTML = allChannels.map(ch => {
            const checked = defaults.includes(ch.label);
            return `<label class="chan-item" data-label="${ch.label}">
                <input type="checkbox" value="${ch.index}" ${checked ? 'checked' : ''}
                       onchange="onChannelChange()">
                ${ch.label}
            </label>`;
        }).join('');
    } catch (e) {
        console.error('加载通道列表失败:', e);
    }
}

function filterChannelList() {
    const kw = document.getElementById('chan-filter').value.toLowerCase();
    document.querySelectorAll('.chan-item').forEach(el => {
        el.classList.toggle('hidden', kw && !el.dataset.label.toLowerCase().includes(kw));
    });
}

function onChannelChange() {
    // 可选：勾选时自动刷新？暂不做，等用户手动点刷新
}

function selectAllChannels() {
    document.querySelectorAll('.chan-item input').forEach(cb => { cb.checked = true; });
}
function deselectAllChannels() {
    document.querySelectorAll('.chan-item input').forEach(cb => { cb.checked = false; });
}

function getSelectedCols() {
    const checked = document.querySelectorAll('.chan-item input:checked');
    return Array.from(checked).map(cb => parseInt(cb.value));
}

async function refreshChart() {
    const cols = getSelectedCols();
    if (!cols.length) { alert('请至少选择一个通道'); return; }
    if (!currentFilename) { alert('请先加载数据文件'); return; }

    const container = document.getElementById('chart-pressure');
    container.style = '';  // 清除 placeholder 的 flex 样式
    container.innerHTML = `
        <div style="padding:40px 20px;">
            <div class="skeleton" style="height:320px;"></div>
            <div class="skeleton" style="width:60%;height:16px;margin-top:12px;"></div>
        </div>`;

    try {
        const resp = await fetch('/api/chart/pressure-curve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: currentFilename,
                time_col: 0,
                value_cols: cols,
            }),
        });
        const fig = await resp.json();
        if (fig.error) { container.innerHTML = `<div style="color:red;padding:20px;">${fig.error}</div>`; return; }
        Plotly.newPlot('chart-pressure', fig.data, fig.layout, { responsive: true, displaylogo: false });
    } catch (e) {
        container.innerHTML = `<div style="color:red;padding:20px;">加载失败：${e.message}</div>`;
    }
}

function initExperimentModule() {
  const uploadZone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');
  if (uploadZone && fileInput) {
    uploadZone.addEventListener('click', () => fileInput.click());
    uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('dragover'); });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', e => {
      e.preventDefault();
      uploadZone.classList.remove('dragover');
      if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files.length) uploadFile(fileInput.files[0]);
    });
  }
  loadExpModels();
  loadFileList();
  refreshFileSelector();
}
