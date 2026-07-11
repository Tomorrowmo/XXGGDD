let fluentCasPath = '';
let fluentDatPath = '';
let fluentCaseName = '';
let fluentWalls = [];
let fluentXsliceMeta = null;
let fluentSymSections = null;
function fmtN(n) {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    const x = Number(n);
    if (!Number.isFinite(x)) return '—';
    return x.toFixed(3);
}

function fluentShowErr(m) {
    const el = _('fluent-err');
    el.style.display = m ? 'block' : 'none';
    el.textContent = m || '';
}
function fluentStatus(m) { _('fluent-status').textContent = m || ''; }
function fluentBtns(on) {
    ['btn-fluent-quick','btn-fluent-inlet','btn-fluent-wall',
     'btn-fluent-sym','btn-fluent-xslice','btn-fluent-vlm','btn-fluent-load','btn-fluent-clear'].forEach(id => {
        const b = _(id); if (b) b.disabled = !on;
    });
}
function setFluentSymBusy(busy) {
    const btn = _('btn-fluent-sym');
    if (btn) btn.disabled = busy || !fluentCasPath || !fluentDatPath;
    closeFluentSymMenu();
}
function closeFluentSymMenu() {
    const menu = _('fluent-sym-menu');
    if (menu) menu.hidden = true;
}
function toggleFluentSymMenu(ev) {
    ev.stopPropagation();
    const btn = _('btn-fluent-sym');
    const menu = _('fluent-sym-menu');
    if (!btn || !menu || btn.disabled) return;
    menu.hidden = !menu.hidden;
}
function pickFluentSymSection(section) {
    closeFluentSymMenu();
    runFluentSymmetry(section);
}

const FLUENT_SYM_LABELS = { symmetry: '对称面', xy: 'XY 平面', xz: 'XZ 平面' };

async function loadFluentOutputCache() {
    if (!fluentCasPath) return;
    try {
        const r = await fetch('/api/fluent/output/load?' + fluentOutputQuery());
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || r.statusText);
        applyFluentOutputPayload(data);
        const parts = [];
        if (data.inlets) parts.push('入口');
        if (data.walls) parts.push('壁面力');
        if (data.sections && data.sections.length) parts.push('截面云图');
        if (data.xslice) parts.push('沿程曲线');
        if (parts.length) fluentStatus('已读取 Output 缓存：' + parts.join('、'));
    } catch (e) { /* 无缓存时静默 */ }
}

function applyFluentOutputPayload(data) {
    if (data.inlets) applyFluentInlets(data.inlets);
    if (data.walls) applyFluentWalls(data.walls);
    if (data.sections && data.sections.length) {
        mergeFluentSymSections(data.sections, Date.now());
    }
    if (data.xslice) {
        fillFluentXsliceMeta(data.xslice.meta);
        _('fluent-xslice-img').src = (data.xslice.plot_url || '') + '?t=' + Date.now();
        _('fluent-sec-xslice').style.display = 'block';
    }
}

async function clearFluentOutput() {
    if (!fluentCasPath || !fluentDatPath) return;
    if (!confirm('确定清空当前算例 Output/ 中的全部后处理结果？\n（入口、壁面力、云图、沿程曲线等）')) return;
    fluentShowErr('');
    fluentStatus('正在清空 Output...');
    try {
        const data = await fluentPost('/api/fluent/output/clear', fluentCaseParams());
        clearFluentCards();
        fluentSymSections = null;
        fluentStatus(`已删除 ${data.count || 0} 个结果文件`);
    } catch (e) { fluentShowErr(e.message); fluentStatus(''); }
}
function clearFluentCards() {
    _('fluent-sec-inlet').style.display = 'none';
    _('fluent-sec-wall').style.display = 'none';
    _('fluent-sec-sym').style.display = 'none';
    _('fluent-sec-xslice').style.display = 'none';
    _('fluent-sec-vlm').style.display = 'none';
}

async function fluentPost(url, body) {
    const r = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
}

function fluentCaseParams(extra = {}) {
    return {
        cas_path: fluentCasPath,
        dat_path: fluentDatPath,
        case_name: fluentCaseName || _('fluent-case-select')?.value || '',
        ...extra,
    };
}

function fluentOutputQuery() {
    let q = 'cas_path=' + encodeURIComponent(fluentCasPath);
    const cn = fluentCaseName || _('fluent-case-select')?.value || '';
    if (cn) q += '&case_name=' + encodeURIComponent(cn);
    return q;
}

// --- 算例 ---
async function loadFluentCases() {
    try {
        const r = await fetch('/api/fluent/cases');
        const data = await r.json();
        const sel = _('fluent-case-select'); sel.innerHTML = '';
        if (!data.exists || !data.cases.length) {
            sel.innerHTML = '<option value="">-- 无可用算例 --</option>';
            return;
        }
        for (const c of data.cases) {
            const o = document.createElement('option');
            o.value = c.name; o.textContent = c.name;
            sel.appendChild(o);
        }
    } catch(e) {
        _('fluent-case-select').innerHTML = '<option value="">-- 加载失败 --</option>';
    }
}

function onFluentCaseChange() {
    clearFluentCards();
    fluentCasPath = ''; fluentDatPath = ''; fluentCaseName = '';
    _('fluent-case-info').textContent = '';
    _('fluent-zones-out').textContent = '{}';
    fluentBtns(false); _('btn-fluent-load').disabled = false;
}

async function loadFluentCaseInfo() {
    const name = _('fluent-case-select').value;
    if (!name) return;
    const info = _('fluent-case-info');
    info.textContent = '加载中...';
    try {
        const r = await fetch('/api/fluent/case/resolve?case_name=' + encodeURIComponent(name));
        const data = await r.json();
        if (data.error) { info.textContent = '❌ ' + data.error; return; }
        fluentCasPath = data.cas_path;
        fluentDatPath = data.dat_path;
        fluentCaseName = data.case_name || name;
        _('fluent-cas-path').value = fluentCasPath;
        _('fluent-dat-path').value = fluentDatPath;
        info.textContent = '✅ ' + (data.pair_label || name);
        fluentBtns(true);
        clearFluentCards();
        await loadFluentOutputCache();
    } catch(e) { info.textContent = '❌ ' + e.message; }
}

// --- 操作 ---
async function runFluentZones() {
    if (!fluentCasPath) return;
    fluentShowErr(''); fluentStatus('读取边界列表...');
    try {
        const r = await fetch('/api/fluent/zones?cas_path=' + encodeURIComponent(fluentCasPath));
        const data = await r.json();
        _('fluent-zones-out').textContent = JSON.stringify(data.zones || data, null, 2);
        fluentStatus('');
    } catch(e) { fluentShowErr(e.message); fluentStatus(''); }
}

async function runFluentQuickLoad() {
    if (!fluentCasPath || !fluentDatPath) { fluentShowErr('请先选择算例'); return; }
    fluentShowErr(''); fluentStatus('正在加载入口参数与壁面力...');
    try {
        const data = await fluentPost('/api/fluent/quick-load', fluentCaseParams({ force: false }));
        if (data.zones) _('fluent-zones-out').textContent = JSON.stringify(data.zones, null, 2);
        applyFluentInlets(data.inlets);
        applyFluentWalls(data);
        const cached = (data.from_cache || []).join('、');
        fluentStatus(cached ? `已从 Output 读取：${cached}` : '已计算并保存 inlet_parameters.txt、wall_forces.txt');
    } catch(e) { fluentShowErr(e.message); fluentStatus(''); }
}

async function runFluentInlet() {
    if (!fluentCasPath || !fluentDatPath) return;
    fluentStatus('正在计算入口参数...');
    try {
        const data = await fluentPost('/api/fluent/inlet-only', fluentCaseParams({ force: true }));
        applyFluentInlets(data.inlets);
        fluentStatus(data.from_cache ? '已从 Output 读取入口参数' : '入口参数已重新计算');
    } catch(e) { fluentShowErr(e.message); fluentStatus(''); }
}

async function runFluentWall() {
    if (!fluentCasPath || !fluentDatPath) return;
    let force = false;
    try {
        const st = await fetch('/api/fluent/output/status?' + fluentOutputQuery());
        const info = await st.json();
        if (info.available && info.available.wall) {
            if (!confirm('Output 中已有壁面力结果，确定重新计算？\n选「取消」将直接读取缓存。')) {
                force = false;
            } else {
                force = true;
            }
        }
    } catch (e) { /* 忽略 */ }
    fluentStatus(force ? '正在重新计算壁面力...' : '正在读取壁面力...');
    try {
        const data = await fluentPost('/api/fluent/wall-forces-only', fluentCaseParams({ force }));
        applyFluentWalls(data);
        fluentStatus(data.from_cache ? '已从 Output 读取壁面力' : '壁面力已重新计算并保存');
    } catch(e) { fluentShowErr(e.message); fluentStatus(''); }
}

async function runFluentSymmetry(section) {
    if (!fluentCasPath || !fluentDatPath) return;
    const label = FLUENT_SYM_LABELS[section] || section;
    let needCompute = true;
    try {
        const st = await fetch('/api/fluent/output/status?' + fluentOutputQuery());
        const info = await st.json();
        needCompute = !(info.available && info.available.sections && info.available.sections[section]);
    } catch (e) { /* 默认需计算 */ }
    if (needCompute && !confirm(`生成 ${label} 截面云图（耗时较长），确定开始？`)) return;

    fluentStatus(needCompute ? `正在生成 ${label} 截面云图...` : `正在读取 ${label} 缓存...`);
    setFluentSymBusy(true);
    try {
        const data = await fluentPost('/api/fluent/symmetry', fluentCaseParams({ section, force: false }));
        mergeFluentSymSections(data.sections, Date.now());
        if (data.section) _('fluent-sym-plane').value = data.section;
        renderFluentSymPlane(Date.now());
        fluentStatus(data.from_cache ? `${label} 云图已从 Output 读取` : `${label} 云图已保存到 Output`);
    } catch(e) { fluentShowErr(e.message); fluentStatus(''); }
    setFluentSymBusy(false);
}

async function runFluentXSlice() {
    if (!fluentCasPath || !fluentDatPath) return;
    let needCompute = true;
    try {
        const st = await fetch('/api/fluent/output/status?' + fluentOutputQuery());
        const info = await st.json();
        needCompute = !(info.available && info.available.xslice);
    } catch (e) { /* 默认需计算 */ }
    if (needCompute && !confirm('沿程面平均需遍历体网格，耗时很长，确定开始？')) return;

    fluentStatus(needCompute ? '沿程面平均计算中（可能数十分钟）...' : '正在读取沿程曲线缓存...');
    _('btn-fluent-xslice').disabled = true;
    try {
        const data = await fluentPost('/api/fluent/x-slice/run', fluentCaseParams({ n_slices: 100, force: false }));
        fillFluentXsliceMeta(data.meta);
        _('fluent-xslice-img').src = (data.plot_url || '') + '?t=' + Date.now();
        _('fluent-sec-xslice').style.display = 'block';
        fluentStatus(data.from_cache ? '沿程曲线已从 Output 读取' : '沿程 CSV 与默认曲线已写入 Output');
    } catch(e) { fluentShowErr(e.message); fluentStatus(''); }
    _('btn-fluent-xslice').disabled = false;
}

async function redrawFluentXslice() {
    if (!fluentCasPath || !fluentDatPath) return;
    const field = _('fluent-xslice-field').value;
    if (!field) return;
    fluentStatus('正在更新曲线...');
    try {
        const data = await fluentPost('/api/fluent/x-slice/plot', fluentCaseParams({
            field,
            x_min_mm: _('fluent-x-min').value, x_max_mm: _('fluent-x-max').value,
            y_min: _('fluent-y-min').value, y_max: _('fluent-y-max').value,
        }));
        _('fluent-xslice-img').src = (data.plot_url || '') + '?t=' + Date.now();
        fluentStatus('曲线已更新');
    } catch(e) { fluentShowErr(e.message); fluentStatus(''); }
}

// --- 数据显示 ---
function applyFluentInlets(rows) {
    const tb = _('fluent-inlet-body'); tb.innerHTML = '';
    if (!rows || !rows.length) {
        _('fluent-sec-inlet').style.display = 'block';
        tb.innerHTML = '<tr><td colspan="6">未找到名称含 inlet 的边界</td></tr>';
        return;
    }
    rows.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td>'+escapeHtml(r.name)+'</td><td>'+escapeHtml(r.zone_type)+'</td>'+
            '<td>'+fmtN(r.velocity_ms)+'</td><td>'+fmtN(r.pressure_mpa)+'</td><td>'+fmtN(r.temperature_k)+'</td><td>'+fmtN(r.mass_flow_kgs)+'</td>';
        tb.appendChild(tr);
    });
    _('fluent-sec-inlet').style.display = 'block';
}

function applyFluentWalls(data) {
    const s = data.sum_all || {};
    _('fluent-sums-all').innerHTML =
        '<div class="fluent-sum-box"><strong>全部壁面 — 压力 ∑Fx (N)</strong><span>'+fmtN(s.fx_pressure)+'</span></div>'+
        '<div class="fluent-sum-box"><strong>全部壁面 — 黏性 ∑Fx (N)</strong><span>'+fmtN(s.fx_viscous)+'</span></div>'+
        '<div class="fluent-sum-box"><strong>全部壁面 — 合力 ∑Fx (N)</strong><span>'+fmtN(s.fx_total)+'</span></div>';
    fluentWalls = data.walls || [];
    fluentRebuildWallTable();
    fluentWireChk();
    _('fluent-sec-wall').style.display = 'block';
}

function fluentRebuildWallTable() {
    const tb = _('fluent-wall-body'); tb.innerHTML = '';
    fluentWalls.forEach((w, i) => {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td><input type="checkbox" data-fidx="'+i+'" checked /></td>'+
            '<td>'+escapeHtml(w.name)+'</td>'+
            '<td>'+fmtN(w.fx_pressure)+'</td><td>'+fmtN(w.fx_viscous)+'</td><td>'+fmtN(w.fx_total)+'</td>';
        tb.appendChild(tr);
    });
}

function fluentWireChk() {
    const ca = _('fluent-chk-all'), boxes = [...document.querySelectorAll('input[data-fidx]')];
    ca.onchange = () => { boxes.forEach(b => b.checked = ca.checked); fluentRecomputeSel(); };
    boxes.forEach(b => b.addEventListener('change', () => {
        ca.checked = boxes.length && boxes.every(x => x.checked);
        ca.indeterminate = boxes.some(x => x.checked) && !ca.checked;
        fluentRecomputeSel();
    }));
    ca.checked = true; ca.indeterminate = false; boxes.forEach(b => b.checked = true);
    fluentRecomputeSel();
}

function fluentRecomputeSel() {
    let sp = 0, sv = 0;
    fluentWalls.forEach((w, i) => {
        const cb = document.querySelector('input[data-fidx="'+i+'"]');
        if (cb && cb.checked) { sp += w.fx_pressure; sv += w.fx_viscous; }
    });
    _('fluent-sums-sel').innerHTML =
        '<div class="fluent-sum-box"><strong>选中壁面 — 压力 ∑Fx (N)</strong><span>'+fmtN(sp)+'</span></div>'+
        '<div class="fluent-sum-box"><strong>选中壁面 — 黏性 ∑Fx (N)</strong><span>'+fmtN(sv)+'</span></div>'+
        '<div class="fluent-sum-box"><strong>选中壁面 — 合力 ∑Fx (N)</strong><span>'+fmtN(sp+sv)+'</span></div>';
}

function mergeFluentSymSections(newSections, ts) {
    const map = new Map((fluentSymSections || []).map(s => [s.key, s]));
    (newSections || []).forEach(s => map.set(s.key, s));
    fluentSymSections = [...map.values()];
    applyFluentSym({ sections: fluentSymSections }, ts);
}

function applyFluentSym(dataOrImages, ts) {
    if (Array.isArray(dataOrImages)) {
        fluentSymSections = [{ key: 'symmetry', label: '对称面', images: dataOrImages }];
    } else {
        fluentSymSections = dataOrImages.sections
            || (dataOrImages.symmetry_images ? [{ key: 'symmetry', label: '对称面', images: dataOrImages.symmetry_images }] : []);
    }
    const sel = _('fluent-sym-plane');
    sel.innerHTML = '';
    sel.style.display = fluentSymSections.length > 1 ? '' : 'none';
    fluentSymSections.forEach(s => {
        const o = document.createElement('option');
        o.value = s.key;
        o.textContent = s.label || s.key;
        sel.appendChild(o);
    });
    sel.onchange = () => renderFluentSymPlane(ts);
    renderFluentSymPlane(ts);
    _('fluent-sec-sym').style.display = 'block';
}

function renderFluentSymPlane(ts) {
    const key = _('fluent-sym-plane').value;
    const sec = (fluentSymSections || []).find(s => s.key === key) || (fluentSymSections || [])[0];
    const images = sec ? (sec.images || []) : [];
    const g = _('fluent-sym-grid'); g.innerHTML = '';
    images.forEach(im => {
        const fig = document.createElement('div'); fig.className = 'fluent-sym-item';
        const img = document.createElement('img'); img.alt = im.title;
        img.src = (im.url || '') + '?t=' + (ts || Date.now());
        img.addEventListener('click', () => openLightbox(img.src, im.title));
        fig.appendChild(img);
        const cap = document.createElement('div'); cap.className = 'fluent-sym-cap';
        cap.textContent = im.title; fig.appendChild(cap);
        g.appendChild(fig);
    });
    populateVLMSelector(images);
}

function populateVLMSelector(images) {
    const sel = _('fluent-vlm-select');
    sel.innerHTML = '<option value="">-- 选择云图 --</option>';
    (images || []).forEach(im => {
        const o = document.createElement('option');
        o.value = im.url || '';
        o.textContent = im.title || im.filename || '';
        sel.appendChild(o);
    });
    _('fluent-vlm-img').src = '';
    _('fluent-vlm-chat-box').innerHTML = '<div class="chat-placeholder">选择云图后点击「VLM 云图分析」按钮开始分析</div>';
}

function openLightbox(src, title) {
    _('img-lightbox-img').src = src;
    _('img-lightbox-cap').textContent = title || '';
    _('img-lightbox-overlay').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    _('img-lightbox-overlay').style.display = 'none';
    document.body.style.overflow = '';
}

function clearFluentSym() {
    fluentSymSections = null;
    _('fluent-sym-plane').innerHTML = '';
    _('fluent-sym-grid').innerHTML = '';
    _('fluent-sec-sym').style.display = 'none';
}

function fillFluentXsliceMeta(meta) {
    fluentXsliceMeta = meta;
    const sel = _('fluent-xslice-field'); sel.innerHTML = '';
    (meta.fields || []).forEach(f => {
        const o = document.createElement('option');
        o.value = f.key; o.textContent = f.label + ' / ' + f.y_unit;
        sel.appendChild(o);
    });
    _('fluent-x-min').value = meta.x_min_mm; _('fluent-x-max').value = meta.x_max_mm;
    const first = meta.fields[0];
    if (first) { _('fluent-y-min').value = first.y_min_default; _('fluent-y-max').value = first.y_max_default; }
}

function clearFluentXslice() {
    _('fluent-sec-xslice').style.display = 'none';
    _('fluent-xslice-img').removeAttribute('src');
    fluentXsliceMeta = null; _('fluent-xslice-field').innerHTML = '';
}

// --- VLM 云图分析 ---
async function loadVLMModels() {
    const sel = _('fluent-vlm-model');
    try {
        const r = await fetch('/api/ragflow/models');
        const models = await r.json();
        sel.innerHTML = '';
        const multimodal = models.filter(m => m.multimodal);
        if (!multimodal.length) {
            sel.innerHTML = '<option value="">-- 无可用 VLM --</option>';
            return;
        }
        // 本地模型优先
        const sorted = [...multimodal].sort((a, b) => {
            if (a.provider === 'local' && b.provider !== 'local') return -1;
            if (a.provider !== 'local' && b.provider === 'local') return 1;
            return 0;
        });
        sorted.forEach(m => {
            const o = document.createElement('option');
            o.value = m.id; o.textContent = m.id;
            if (m.id === 'local/vllm_Qwen2.5-VL-7B') o.selected = true;
            sel.appendChild(o);
        });
    } catch(e) { sel.innerHTML = '<option value="">-- 加载失败 --</option>'; }
}

async function runFluentVLM() {
    const sel = _('fluent-vlm-select');
    if (!sel || !sel.selectedIndex) {
        fluentShowErr('请先在下方「VLM 云图分析」卡片中选择一张云图');
        _('fluent-sec-vlm').style.display = 'block';
        return;
    }
    const imagePath = sel.value;
    const modelId = _('fluent-vlm-model').value;

    _('fluent-sec-vlm').style.display = 'block';
    const box = _('fluent-vlm-chat-box');
    box.innerHTML = '';
    const loading = _('fluent-vlm-loading');
    loading.textContent = '🤖 VLM 分析中...';

    try {
        const resp = await fetch('/api/fluent/vlm/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_path: imagePath, model_id: modelId }),
        });
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '', rawText = '';
        const bubble = document.createElement('div');
        bubble.className = 'chat-msg assistant';
        box.appendChild(bubble);

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
                    else if (d.error) { loading.textContent = '❌ ' + d.error; bubble.innerHTML = '<span style="color:#ef4444">' + d.error + '</span>'; }
                }
            }
            box.scrollTop = box.scrollHeight;
        }
    } catch (e) {
        loading.textContent = '❌ ' + e.message;
    }
}
// --- 算例上传 ---
function toggleUploadForm() {
    const form = _('fluent-upload-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function startCaseUpload() {
    const name = _('fluent-upload-name').value.trim();
    const fileInput = _('fluent-upload-files');
    if (!name) { _('fluent-upload-status').textContent = '❌ 请输入算例名称'; _('fluent-upload-status').style.color = '#ef4444'; return; }
    if (!fileInput.files.length) { _('fluent-upload-status').textContent = '❌ 请选择文件'; _('fluent-upload-status').style.color = '#ef4444'; return; }

    const formData = new FormData();
    formData.append('case_name', name);
    for (const f of fileInput.files) formData.append('files', f);

    _('fluent-upload-status').textContent = '上传中...'; _('fluent-upload-status').style.color = '';
    const wrap = _('fluent-upload-progress-wrap'); wrap.style.display = 'block';
    const bar = _('fluent-upload-progress-fill'); bar.style.width = '0%';
    const txt = _('fluent-upload-progress-text'); txt.textContent = '0%';

    try {
        const resp = await fetch('/api/fluent/case/upload', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.error) { _('fluent-upload-status').textContent = '❌ ' + data.error; _('fluent-upload-status').style.color = '#ef4444'; return; }

        // 轮询进度 SSE
        const evtResp = await fetch('/api/fluent/case/upload-progress/' + data.job_id);
        const reader = evtResp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split('\n'); buf = lines.pop() || '';
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const d = JSON.parse(line.slice(6));
                    if (d.percent !== undefined) {
                        bar.style.width = d.percent + '%'; txt.textContent = d.percent.toFixed(1) + '%';
                        _('fluent-upload-status').textContent = d.message || '';
                    }
                    if (d.status === 'done') {
                        _('fluent-upload-status').textContent = '✅ 上传完成：' + (d.case_name || '');
                        _('fluent-upload-status').style.color = '#22c55e';
                        loadFluentCases(); // 刷新算例列表
                    } else if (d.status === 'error') {
                        _('fluent-upload-status').textContent = '❌ ' + (d.error || '上传失败');
                        _('fluent-upload-status').style.color = '#ef4444';
                    }
                }
            }
        }
    } catch (e) {
        _('fluent-upload-status').textContent = '❌ ' + e.message;
        _('fluent-upload-status').style.color = '#ef4444';
    }
}

function initSimulationModule() {
  loadFluentCases();
  loadVLMModels();
  _('fluent-xslice-field')?.addEventListener('change', () => {
    if (!fluentXsliceMeta) return;
    const k = _('fluent-xslice-field').value;
    const f = (fluentXsliceMeta.fields || []).find(x => x.key === k);
    if (f) { _('fluent-y-min').value = f.y_min_default; _('fluent-y-max').value = f.y_max_default; }
  });
  _('fluent-vlm-select')?.addEventListener('change', () => {
    const url = _('fluent-vlm-select').value;
    const img = _('fluent-vlm-img');
    if (url) { img.src = url + '?t=' + Date.now(); _('fluent-sec-vlm').style.display = 'block'; }
    else img.src = '';
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });
  document.addEventListener('click', e => {
    const wrap = _('fluent-sym-dropdown');
    if (wrap && !wrap.contains(e.target)) closeFluentSymMenu();
  });
}
