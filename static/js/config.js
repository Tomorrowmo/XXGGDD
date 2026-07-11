let configModels = [];

async function loadConfigModels() {
    try {
        const r = await fetch('/api/models/config');
        const data = await r.json();
        configModels = data.models || [];
        renderConfigModels();
    } catch(e) { _('config-model-list').innerHTML = '<p style="color:#ef4444">加载配置失败: ' + e.message + '</p>'; }
}

function renderConfigModels() {
    const container = _('config-model-list');
    container.innerHTML = '';
    if (!configModels.length) {
        container.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:20px;">暂无模型配置</p>';
        return;
    }
    configModels.forEach((m, i) => {
        const isLocal = m.provider === 'local';
        const cls = isLocal ? 'local' : 'remote';
        const card = document.createElement('div');
        card.className = 'config-model-card';
        card.innerHTML =
            '<div class="config-model-header" onclick="configToggleBody('+i+')">'+
                '<span class="config-model-id"><span class="'+cls+'">'+escapeHtml(m.id)+'</span> <span style="font-size:0.72rem;opacity:0.6">('+ (isLocal?'本地':'商用') +')</span></span>'+
                '<span style="font-size:0.7rem;color:var(--text-secondary);">▼</span>'+
            '</div>'+
            '<div class="config-model-body" id="config-body-'+i+'">'+
                '<div class="config-row"><div><div class="config-label">模型ID</div><input class="config-input" data-field="id" data-idx="'+i+'" value="'+escapeHtml(m.id)+'"></div>'+
                '<div><div class="config-label">显示名称</div><input class="config-input" data-field="name" data-idx="'+i+'" value="'+escapeHtml(m.name||'')+'"></div></div>'+
                '<div class="config-row"><div><div class="config-label">Provider</div><input class="config-input" data-field="provider" data-idx="'+i+'" value="'+escapeHtml(m.provider||'')+'"></div>'+
                '<div><div class="config-label">API Base URL</div><input class="config-input" data-field="api_base" data-idx="'+i+'" value="'+escapeHtml(m.api_base||'')+'"></div></div>'+
                '<div class="config-row"><div><div class="config-label">Model Name</div><input class="config-input" data-field="model_name" data-idx="'+i+'" value="'+escapeHtml(m.model_name||'')+'"></div>'+
                '<div><div class="config-label">直接 Key（优先）</div><input class="config-input" data-field="api_key" data-idx="'+i+'" value="'+escapeHtml(m.api_key||'')+'" type="password" placeholder="直接填写 API Key"></div>'+'<div><div class="config-label">环境变量（备选）</div><input class="config-input" data-field="api_key_env" data-idx="'+i+'" value="'+escapeHtml(m.api_key_env||'')+'" placeholder="如 DEEPSEEK_API_KEY"></div></div>'+'<div class="config-row single"><div style="font-size:0.7rem;color:var(--text-secondary);margin-top:-2px;">💡 直接 Key 不为空时优先使用，否则从环境变量读取。已保存的 Key 会脱敏显示为 ****</div></div>'+
                '<div class="config-row"><div><div class="config-label">max_tokens</div><input class="config-input" data-field="max_tokens" data-idx="'+i+'" value="'+ (m.max_tokens||4096) +'" type="number"></div>'+
                '<div><div class="config-label">temperature</div><input class="config-input" data-field="temperature" data-idx="'+i+'" value="'+ (m.temperature||0.3) +'" type="number" step="0.1"></div></div>'+
                '<div class="config-row"><div><div class="config-label">multimodal</div><select class="config-input" data-field="multimodal" data-idx="'+i+'"><option value="false"'+(m.multimodal?'':' selected')+'>否</option><option value="true"'+(m.multimodal?' selected':'')+'>是</option></select></div>'+
                '<div><div class="config-label">reasoning_effort</div><input class="config-input" data-field="reasoning_effort" data-idx="'+i+'" value="'+escapeHtml(m.reasoning_effort||'')+'"></div></div>'+
                '<div class="config-actions">'+
                    '<button onclick="configTestModel('+i+')">⚡ 测试连接</button>'+
                    '<button class="del-btn" onclick="configDeleteModel('+i+')">删除</button>'+
                '</div>'+
            '</div>';
        container.appendChild(card);
    });
}

function configToggleBody(i) {
    const body = _('config-body-'+i);
    if (body) body.classList.toggle('open');
}

function configSyncField(el) {
    const idx = parseInt(el.dataset.idx), field = el.dataset.field;
    let val = el.value;
    if (field === 'api_key' && val === '****') return; // 未改动，保持脱敏值
    if (el.type === 'number') val = parseFloat(val) || 0;
    if (field === 'multimodal') val = el.value === 'true';
    configModels[idx][field] = val;
}

function configAddModel() {
    configModels.push({
        id: 'new/model-id', name: '新模型', provider: 'local',
        api_base: 'http://localhost:8000/v1', api_key: '', api_key_env: null,
        model_name: 'model-name', multimodal: false,
        max_tokens: 4096, temperature: 0.3, extra_body: {}
    });
    renderConfigModels();
    configToggleBody(configModels.length - 1);
}

function configDeleteModel(i) {
    if (!confirm('确定删除 ' + configModels[i].id + '？')) return;
    configModels.splice(i, 1);
    renderConfigModels();
}

async function configTestModel(i) {
    const m = configModels[i];
    const status = _('config-save-status');
    status.textContent = '测试中...';
    try {
        const r = await fetch('/api/models/test', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({model: m})
        });
        const d = await r.json();
        status.textContent = d.ok ? '✅ ' + d.message : '❌ ' + d.message;
        status.style.color = d.ok ? '#22c55e' : '#ef4444';
    } catch(e) {
        status.textContent = '❌ 请求失败'; status.style.color = '#ef4444';
    }
}

async function configSaveAll() {
    const status = _('config-save-status');
    status.textContent = '保存中...';
    try {
        const r = await fetch('/api/models/config', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({models: configModels})
        });
        const d = await r.json();
        status.textContent = d.ok ? '✅ ' + d.message : '❌ ' + (d.error || '');
        status.style.color = d.ok ? '#22c55e' : '#ef4444';
        if (d.ok) loadRagflowModels(); // 刷新 RAGflow 下拉
    } catch(e) {
        status.textContent = '❌ ' + e.message; status.style.color = '#ef4444';
    }
}

// --- RAG 知识库配置 ---
async function loadRAGConfig() {
    try {
        const r = await fetch('/api/rag/config');
        const data = await r.json();
        const url = data.iframe_url || '';
        _('rag-iframe-url').value = url;
        applyRAGUrl(url);
    } catch(e) { /* ignore */ }
}

function applyRAGUrl(url) {
    if (!url) return;
    _('rag-kb-iframe').src = url;
    // 链接地址取 URL 的 origin 部分
    try {
        const u = new URL(url);
        _('rag-kb-link').href = u.origin + '/';
    } catch(e) { _('rag-kb-link').href = url; }
}

async function configSaveRAG() {
    const status = _('config-rag-status');
    const url = _('rag-iframe-url').value.trim();
    if (!url) { status.textContent = '❌ URL 不能为空'; status.style.color = '#ef4444'; return; }
    status.textContent = '保存中...'; status.style.color = '';
    try {
        const r = await fetch('/api/rag/config', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({iframe_url: url})
        });
        const d = await r.json();
        status.textContent = d.ok ? '✅ ' + d.message : '❌ ' + (d.error || '');
        status.style.color = d.ok ? '#22c55e' : '#ef4444';
        if (d.ok) applyRAGUrl(url);
    } catch(e) { status.textContent = '❌ ' + e.message; status.style.color = '#ef4444'; }
}

function initConfigModule() {
  loadConfigModels();
  loadRAGConfig();
  document.addEventListener('input', e => {
    if (e.target.dataset.field && e.target.dataset.idx !== undefined) configSyncField(e.target);
  });
  document.addEventListener('change', e => {
    if (e.target.dataset.field && e.target.dataset.idx !== undefined) configSyncField(e.target);
  });
}
