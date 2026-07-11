let ragflowMessages = [];
let ragflowRunning = false;
async function loadRagflowModels() {
    try {
        const resp = await fetch('/api/ragflow/models');
        const models = await resp.json();
        const sel = document.getElementById('ragflow-model-select');
        sel.innerHTML = '';

        // 按 provider 分两组：本地 / 商用
        const localModels = [];
        const remoteModels = [];
        for (const m of models) {
            if (m.provider === 'local') localModels.push(m);
            else remoteModels.push(m);
        }

        function buildOptgroup(label, groupModels) {
            const g = document.createElement('optgroup');
            g.label = label;
            for (const m of groupModels) {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.id;
                if (m.id === 'deepseek/deepseek-v4-flash') opt.selected = true;
                g.appendChild(opt);
            }
            sel.appendChild(g);
        }

        if (localModels.length) buildOptgroup('本地模型', localModels);
        if (remoteModels.length) buildOptgroup('商用模型', remoteModels);
    } catch (e) {
        document.getElementById('ragflow-model-select').innerHTML =
            '<option value="">-- 加载失败 --</option>';
    }
}

function onRagflowModelChange() {
    const sel = document.getElementById('ragflow-model-select');
    ragflowCurrentModel = sel.value;
    // 切换模型时清除测试状态
    const status = document.getElementById('ragflow-test-status');
    status.textContent = '';
    status.className = 'ragflow-test-status';
}

async function testRagflowModel() {
    const sel = document.getElementById('ragflow-model-select');
    const modelId = sel.value;
    if (!modelId) return;

    const btn = document.getElementById('btn-ragflow-test');
    const status = document.getElementById('ragflow-test-status');

    btn.disabled = true;
    btn.classList.add('spinning');
    status.textContent = '';
    status.className = 'ragflow-test-status';

    try {
        const resp = await fetch('/api/ragflow/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_id: modelId }),
        });
        const data = await resp.json();
        if (data.ok) {
            status.textContent = `✅ ${data.message || '连接正常'}`;
            status.className = 'ragflow-test-status success';
        } else {
            status.textContent = `❌ ${data.message || '连接失败'}`;
            status.className = 'ragflow-test-status error';
        }
    } catch (e) {
        status.textContent = '❌ 测试请求失败';
        status.className = 'ragflow-test-status error';
    }

    btn.classList.remove('spinning');
    btn.disabled = false;
}

function appendRagflowBubble(role, html) {
    const box = document.getElementById('ragflow-chat-box');
    const ph = document.getElementById('ragflow-chat-placeholder');
    if (ph) ph.remove();
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.innerHTML = html;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

async function sendRagflowMessage() {
    if (ragflowRunning) return;
    const sel = document.getElementById('ragflow-model-select');
    const modelId = sel.value;
    if (!modelId) return;

    const input = document.getElementById('ragflow-chat-input');
    const text = input.value.trim();
    if (!text) return;

    // 存上下文
    if (ragflowMessages.length >= 10) ragflowMessages = ragflowMessages.slice(-9);
    ragflowMessages.push({ role: 'user', content: text });
    appendRagflowBubble('user', text);
    input.value = '';

    ragflowRunning = true;
    document.getElementById('btn-ragflow-send').disabled = true;
    const loading = document.getElementById('ragflow-chat-loading');
    loading.textContent = '🤖 思考中...';
    const bubble = appendRagflowBubble('assistant', '');
    let rawText = '';

    try {
        const resp = await fetch('/api/ragflow/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_id: modelId,
                messages: ragflowMessages,
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
    if (rawText) ragflowMessages.push({ role: 'assistant', content: rawText });
    loading.textContent = '';
    document.getElementById('btn-ragflow-send').disabled = false;
    ragflowRunning = false;
}

function initRagflowModule() {
  loadRagflowModels();
  document.getElementById('ragflow-model-select')?.addEventListener('change', onRagflowModelChange);
  document.querySelectorAll('.ragflow-subtab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.ragflow-subtab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.ragflow-subpanel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.ragflowSub).classList.add('active');
    });
  });
}
