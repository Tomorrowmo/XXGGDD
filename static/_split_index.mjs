import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const MONOLITH = path.join(ROOT, 'index.monolith.html');
const SRC = fs.existsSync(MONOLITH) ? MONOLITH : path.join(ROOT, 'index.html');

// 若当前 index.html 仍是 monolith（>500 行），先备份
const current = path.join(ROOT, 'index.html');
if (fs.existsSync(current)) {
  const n = fs.readFileSync(current, 'utf8').split('\n').length;
  if (n > 500 && !fs.existsSync(MONOLITH)) {
    fs.copyFileSync(current, MONOLITH);
    console.log('已备份 index.monolith.html');
  }
}

const lines = fs.readFileSync(SRC.includes('monolith') ? SRC : (fs.existsSync(MONOLITH) ? MONOLITH : current), 'utf8').split('\n');
const sl = (a, b) => lines.slice(a - 1, b).join('\n') + '\n';
const w = (rel, c) => {
  const p = path.join(ROOT, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, c, 'utf8');
};

// --- CSS ---
w('css/common.css', sl(10, 348) + sl(501, 504) + sl(654, 809));
w('css/ragflow.css', sl(349, 448) + sl(604, 612));
w('css/simulation.css', sl(449, 499) + sl(544, 602));
w('css/config.css', sl(505, 543));
w('css/experiment.css', sl(190, 297) + sl(614, 652));

// --- Tab HTML（面板内部内容）---
w('tabs/ragflow.html', sl(915, 970));
w('tabs/simulation.html', sl(975, 1108));
w('tabs/experiment.html', sl(1113, 1302));
w('tabs/upcoming.html', sl(1307, 1317));
w('tabs/config.html', sl(1322, 1344));

// --- JS ---
const COMMON_HELPERS = `
function _(id) { return document.getElementById(id); }

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}
`;

w('js/common.js', sl(1363, 1368) + COMMON_HELPERS + sl(2623, 2627) + sl(2819, 2833) + sl(2838, 2844) + `
const TAB_HTML = {
  'tab-ragflow': '/static/tabs/ragflow.html',
  'tab-simulation': '/static/tabs/simulation.html',
  'tab-experiment': '/static/tabs/experiment.html',
  'tab-upcoming': '/static/tabs/upcoming.html',
  'tab-config': '/static/tabs/config.html',
};

async function loadAllTabPanels() {
  await Promise.all(Object.entries(TAB_HTML).map(async ([id, url]) => {
    const el = document.getElementById(id);
    if (!el || el.dataset.loaded === '1') return;
    el.innerHTML = await (await fetch(url)).text();
    el.dataset.loaded = '1';
  }));
}

async function bootstrapApp() {
  await loadAllTabPanels();
  if (typeof initConfigModule === 'function') initConfigModule();
  if (typeof initRagflowModule === 'function') initRagflowModule();
  if (typeof initSimulationModule === 'function') initSimulationModule();
  if (typeof initExperimentModule === 'function') initExperimentModule();
}

document.addEventListener('DOMContentLoaded', () => {
  bootstrapApp().catch(err => console.error('Tab 加载失败:', err));
});
`);

w('js/ragflow.js', sl(1558, 1559) + sl(1704, 1854) + `
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
`);

w('js/simulation.js', sl(1562, 1565) + sl(1875, 2148) + sl(2153, 2172) + sl(2182, 2263) + sl(2270, 2328) + `
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
}
`);

w('js/config.js', sl(2336, 2397) + sl(2406, 2493) + `
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
`);

const EXP_VARS = `let llmChatMessages = [];
let llmRunning = false;
let chatMessages = [];
let vlmRunning = false;
let allChannels = [];
let currentFilename = '';
`;
// 勿重复 ragflow/simulation 状态块、勿重复 allChannels/chatMessages 声明
w('js/experiment.js', EXP_VARS + sl(2509, 2509) + sl(1391, 1515) + sl(1517, 1549) + sl(1575, 1699)
  + sl(2511, 2621) + sl(2629, 2712) + sl(2716, 2810) + `
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
`);

const shell = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>导弹动力智能评估</title>
<script src="https://cdn.plot.ly/plotly-3.1.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<link rel="stylesheet" href="/static/css/common.css">
<link rel="stylesheet" href="/static/css/ragflow.css">
<link rel="stylesheet" href="/static/css/simulation.css">
<link rel="stylesheet" href="/static/css/experiment.css">
<link rel="stylesheet" href="/static/css/config.css">
</head>
<body data-theme="deepspace">

<div class="bg-effects">
    <div class="bg-nozzle-glow"></div>
    <div class="bg-spark s1"></div><div class="bg-spark s2"></div><div class="bg-spark s3"></div><div class="bg-spark s4"></div><div class="bg-spark s5"></div>
    <div class="bg-spark s6"></div><div class="bg-spark s7"></div><div class="bg-spark s8"></div><div class="bg-spark s9"></div><div class="bg-spark s10"></div>
    <div class="bg-spark s11"></div><div class="bg-spark s12"></div><div class="bg-spark s13"></div><div class="bg-spark s14"></div><div class="bg-spark s15"></div>
    <div class="bg-spark s16"></div><div class="bg-spark s17"></div><div class="bg-spark s18"></div><div class="bg-spark s19"></div><div class="bg-spark s20"></div>
</div>

<header class="topbar">
    <span style="display:flex;align-items:center;gap:16px;">
        <span class="topbar-title">🚀 导弹动力智能评估</span>
        <a href="/help" class="topbar-docs-btn">📖 Docs</a>
    </span>
</header>

<div class="body-row">
    <nav class="nav-side">
        <div class="nav-item active" data-tab="tab-ragflow"><span class="icon">🧠</span> RAGflow</div>
        <div class="nav-item" data-tab="tab-simulation"><span class="icon">🔬</span> 仿真分析</div>
        <div class="nav-item" data-tab="tab-experiment"><span class="icon">📊</span> 试验分析</div>
        <div class="nav-item" data-tab="tab-upcoming"><span class="icon">✨</span> 敬请期待</div>
        <div class="nav-divider"></div>
        <div class="nav-item" data-tab="tab-config"><span class="icon">⚙️</span> 模型配置</div>
        <div class="nav-bottom">
            <label>🎨 界面风格</label>
            <select id="theme-select">
                <option value="deepspace">深空科技风</option>
                <option value="minimal">极简白底风</option>
                <option value="cockpit">航天仪表风</option>
                <option value="sunset">日落发射风</option>
            </select>
        </div>
    </nav>
    <main class="content">
        <div id="tab-ragflow" class="tab-panel active"></div>
        <div id="tab-simulation" class="tab-panel"></div>
        <div id="tab-experiment" class="tab-panel"></div>
        <div id="tab-upcoming" class="tab-panel"></div>
        <div id="tab-config" class="tab-panel"></div>
    </main>
</div>

<footer class="statusbar">
    <span><span class="status-dot ok"></span>系统就绪</span>
    <span>数据来源：未上传</span>
    <span>GPU：cuda:6,7</span>
    <span>环境：gy_pytorch</span>
    <span style="margin-left:auto;opacity:0.5">FastAPI + HTML/JS</span>
</footer>

<script src="/static/js/common.js"></script>
<script src="/static/js/config.js"></script>
<script src="/static/js/ragflow.js"></script>
<script src="/static/js/simulation.js"></script>
<script src="/static/js/experiment.js"></script>

<div id="img-lightbox-overlay" class="img-lightbox-overlay" style="display:none;" onclick="closeLightbox()">
    <button class="img-lightbox-close" onclick="closeLightbox()">✕</button>
    <img id="img-lightbox-img" src="" alt="" onclick="event.stopPropagation()" />
    <div class="img-lightbox-cap" id="img-lightbox-cap"></div>
</div>

</body>
</html>
`;

// 确保 monolith 来自最新 index
if (!fs.existsSync(MONOLITH)) {
  fs.copyFileSync(current, MONOLITH);
}

w('index.html', shell);
console.log('拆分完成：5 个 Tab 模块 + shell');
