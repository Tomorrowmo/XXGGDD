function formatSize(bytes) {
    if (bytes == null) return '-';
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(2) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
}

function _(id) { return document.getElementById(id); }

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}
// 更新底栏状态
function updateStatus(filename) {
    const src = document.querySelector('.statusbar span:nth-child(2)');
    if (src) src.textContent = '数据来源：' + filename;
}
function switchTab(tabId) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    const nav = document.querySelector(`[data-tab="${tabId}"]`);
    const panel = document.getElementById(tabId);
    if (nav) nav.classList.add('active');
    if (panel) panel.classList.add('active');
}

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        switchTab(item.dataset.tab);
        if (item.dataset.tab === 'tab-experiment' && typeof refreshFileSelector === 'function') {
            refreshFileSelector();
        }
    });
});
const themeSelect = document.getElementById('theme-select');
const saved = localStorage.getItem('theme');
if (saved) { document.body.setAttribute('data-theme', saved); themeSelect.value = saved; }
themeSelect.addEventListener('change', () => {
    document.body.setAttribute('data-theme', themeSelect.value);
    localStorage.setItem('theme', themeSelect.value);
});

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

function closeLightbox() {
    const overlay = _('img-lightbox-overlay');
    if (overlay) overlay.style.display = 'none';
    document.body.style.overflow = '';
}

function openLightbox(src, title) {
    _('img-lightbox-img').src = src;
    _('img-lightbox-cap').textContent = title || '';
    _('img-lightbox-overlay').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

async function bootstrapApp() {
  await loadAllTabPanels();
  const inits = [
    ['config', initConfigModule],
    ['ragflow', initRagflowModule],
    ['simulation', initSimulationModule],
    ['experiment', initExperimentModule],
  ];
  for (const [name, fn] of inits) {
    if (typeof fn !== 'function') continue;
    try {
      fn();
    } catch (err) {
      console.error(`模块 ${name} 初始化失败:`, err);
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  bootstrapApp().catch(err => console.error('Tab 加载失败:', err));
});
