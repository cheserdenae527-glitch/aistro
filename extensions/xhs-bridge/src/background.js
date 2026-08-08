// AiRestro XHS Bridge — 后台（串行任务 + 上报本地后端）
// 阶段 3 最小闭环：保存当前笔记 / 采集评论 / 收集本页链接。
const EXT_VERSION = 'v4.1';
const DEFAULT_ENDPOINT = 'http://127.0.0.1:8000/api/v1/bridge';
const SETTINGS_KEY = 'aistroBridgeSettings';
const INTERVAL_MIN_MS = 1500;
const INTERVAL_MAX_MS = 3500;

const settingsStore = {
  async get() {
    const raw = await chrome.storage.local.get(SETTINGS_KEY);
    const s = raw[SETTINGS_KEY] || {};
    return {
      endpoint: String(s.endpoint || DEFAULT_ENDPOINT).replace(/\/$/, ''),
      intervalMinMs: Number(s.intervalMinMs || INTERVAL_MIN_MS),
      intervalMaxMs: Number(s.intervalMaxMs || INTERVAL_MAX_MS),
    };
  },
  async set(patch) {
    const s = await settingsStore.get();
    Object.assign(s, patch);
    await chrome.storage.local.set({ [SETTINGS_KEY]: s });
    return s;
  },
};

function randomIntBetween(min, max) {
  const lo = Math.ceil(Math.min(min, max));
  const hi = Math.floor(Math.max(min, max));
  return lo + Math.floor(Math.random() * (hi - lo + 1));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseCountText(v) {
  const s = String(v == null ? '' : v).replace(/[\s,]/g, '');
  if (!s) return 0;
  const m = s.match(/(\d+(?:\.\d+)?)(万|亿)?/);
  if (!m) return 0;
  const n = parseFloat(m[1]);
  if (Number.isNaN(n)) return 0;
  if (m[2] === '万') return Math.round(n * 10000);
  if (m[2] === '亿') return Math.round(n * 100000000);
  return Math.round(n);
}

// 在 MAIN world 里执行签名 + feed 请求（mnsv2/md5 只在 MAIN world 存在）
const mainWorldFeedFetch = async (noteId, xsecToken, xsecSource) => {
  const alphabet = 'ZmserbBoHQtNP+wOcza/LpngG8yJq42KWYj0DSfdikx3VT16IlUAFM97hECvuRX5';
  function customBase64(bytes) {
    const arr = Array.from(bytes || []);
    let out = '';
    for (let i = 0; i < arr.length; i += 3) {
      const b1 = arr[i];
      const b2 = i + 1 < arr.length ? arr[i + 1] : NaN;
      const b3 = i + 2 < arr.length ? arr[i + 2] : NaN;
      const t = (b1 << 16) | ((Number.isNaN(b2) ? 0 : b2) << 8) | (Number.isNaN(b3) ? 0 : b3);
      out += alphabet[(t >>> 18) & 63];
      out += alphabet[(t >>> 12) & 63];
      out += Number.isNaN(b2) ? '=' : alphabet[(t >>> 6) & 63];
      out += Number.isNaN(b3) ? '=' : alphabet[t & 63];
    }
    return out;
  }
  function crc32(value) {
    const bytes = typeof value === 'string' ? Array.from(new TextEncoder().encode(value)) : Array.from(value || []);
    let crc = -1;
    for (const byte of bytes) { crc ^= byte; for (let i = 0; i < 8; i += 1) crc = (crc & 1) ? ((crc >>> 1) ^ 0xedb88320) : (crc >>> 1); }
    return ((crc ^ -1) >>> 0);
  }
  function getCookie(name) {
    for (const item of document.cookie.split(';')) { const c = item.trim(); if (c.startsWith(name + '=')) return c.slice(name.length + 1); }
    return '';
  }
  function getOS() {
    const ua = String(navigator.userAgent || '').toLowerCase();
    if (ua.includes('android')) return 'Android';
    if (ua.includes('iphone') || ua.includes('ipad') || ua.includes('ipod')) return 'iOS';
    if (ua.includes('macintosh')) return 'Mac OS';
    if (ua.includes('windows')) return 'Windows';
    if (ua.includes('linux')) return 'Linux';
    return 'PC';
  }
  function getPlatform(os) {
    switch (os) { case 'Windows': return 0; case 'Android': return 2; case 'iOS': return 1; case 'Mac OS': return 3; case 'Linux': return 4; default: return 5; }
  }
  function getXSCommon() {
    let b1 = '', b1b1 = '1';
    try { b1 = localStorage.getItem('b1') || ''; b1b1 = localStorage.getItem('b1b1') || '1'; } catch (_) {}
    const os = getOS();
    const payload = { s0: getPlatform(os), s1: '', x0: b1b1, x1: '4.2.6', x2: os, x3: 'xhs-pc-web', x4: '4.83.1', x5: getCookie('a1'), x6: '', x7: '', x8: b1, x9: crc32(String(b1)), x10: 0, x11: 'normal' };
    return customBase64(new TextEncoder().encode(JSON.stringify(payload)));
  }
  async function seccoreSign(path, body) {
    if (typeof window.mnsv2 !== 'function' || typeof window.md5 !== 'function') throw new Error('no mnsv2/md5');
    let content = path;
    const tag = Object.prototype.toString.call(body);
    if (tag === '[object Object]' || tag === '[object Array]') content += JSON.stringify(body);
    else if (typeof body === 'string') content += body;
    const signature = await window.mnsv2(content, window.md5(content), window.md5(path));
    const payload = { x0: '4.2.6', x1: 'xhs-pc-web', x2: window.xsecplatform || 'PC', x3: signature, x4: body ? typeof body : '' };
    return 'XYS_' + customBase64(new TextEncoder().encode(JSON.stringify(payload)));
  }
  function traceId() {
    const random = (bits) => Math.floor(Math.random() * (1 << bits));
    const time = Date.now();
    const p1 = (BigInt(time) << 23n) | BigInt(random(23));
    const p2 = (BigInt(random(32)) << 32n) | BigInt(random(32));
    return p1.toString(16).padStart(16, '0') + p2.toString(16).padStart(16, '0');
  }
  function xB3TraceId() { let v = ''; for (let i = 0; i < 16; i += 1) v += 'abcdef0123456789'.charAt(Math.floor(Math.random() * 16)); return v; }

  if (!noteId || !xsecToken) return { ok: false, reason: 'missing noteId/xsec_token' };
  if (typeof window.mnsv2 !== 'function' || typeof window.md5 !== 'function') return { ok: false, reason: 'no mnsv2/md5 in MAIN world' };
  const path = '/api/sns/web/v1/feed';
  const body = { source_note_id: noteId, image_formats: ['jpg', 'webp', 'avif'], extra: { need_body_topic: '1' }, xsec_source: xsecSource || 'pc_user', xsec_token: xsecToken };
  try {
    const res = await fetch('https://edith.xiaohongshu.com' + path, {
      method: 'POST', credentials: 'include',
      headers: { accept: 'application/json, text/plain, */*', 'content-type': 'application/json;charset=UTF-8', 'x-s': await seccoreSign(path, body), 'x-t': String(Date.now()), 'x-s-common': getXSCommon(), 'x-xray-traceid': traceId(), 'x-b3-traceid': xB3TraceId() },
      body: JSON.stringify(body),
    });
    const json = await res.json();
    if (!json || json.success === false) return { ok: false, code: json && json.code, msg: String((json && json.msg) || '').slice(0, 80), reason: 'feed failed' };
    const data = json.data;
    const items = data && Array.isArray(data.items) ? data.items : [];
    const first = items[0] || null;
    const nc = first && (first.note_card || first.noteCard) || null;
    return { ok: Boolean(nc), note_card: nc, itemCount: items.length, dataType: data === null ? 'null' : typeof data, code: json.code, msg: String(json.msg || '').slice(0, 80), topKeys: json && typeof json === 'object' ? Object.keys(json) : [] };
  } catch (e) {
    return { ok: false, reason: String((e && e.message) || e).slice(0, 120) };
  }
};

async function fetchFeedMainWorld(tabId, noteId, xsecToken, xsecSource) {
  try {
    const [r] = await chrome.scripting.executeScript({
      target: { tabId }, world: 'MAIN', args: [noteId, xsecToken, xsecSource], func: mainWorldFeedFetch,
    });
    return r && r.result ? r.result : { ok: false, reason: 'no result' };
  } catch (e) {
    return { ok: false, reason: String((e && e.message) || e).slice(0, 120) };
  }
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

async function xsecSourceFromUrl(url) {
  try { return new URL(url || '').searchParams.get('xsec_source') || 'pc_user'; } catch (_) { return 'pc_user'; }
}

async function waitForTabComplete(tabId, timeoutMs = 20000) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (v) => { if (!settled) { settled = true; clearTimeout(timer); chrome.tabs.onUpdated.removeListener(listener); resolve(v); } };
    const listener = (id, info) => { if (id === tabId && info.status === 'complete') finish(true); };
    chrome.tabs.onUpdated.addListener(listener);
    const timer = setTimeout(() => finish(false), timeoutMs);
  });
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab || null;
}

function isXhsTab(tab) {
  if (!tab || !tab.url) return false;
  return /(^|\.)xiaohongshu\.com|(^|\.)rednote\.com/i.test(tab.url);
}

async function injectContentScripts(tabId) {
  // 按需注入（Beav 同款动态注入）：内容脚本没加载时，后台主动注入后重试
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ['src/captureRuntime.js', 'src/content.js'] });
  } catch (_) {}
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ['src/xhsBridge.js'], world: 'MAIN' });
  } catch (_) {}
  await sleep(200);
}

async function sendToTab(tabId, type, options) {
  const attempt = async () => {
    const res = await chrome.tabs.sendMessage(tabId, { type, ...(options || {}) });
    if (!res) throw new Error('页面无响应（请确认已在小红书页面）');
    if (res.success === false) throw new Error(res.error || '提取失败');
    return res;
  };
  try {
    return await attempt();
  } catch (e) {
    const msg = String((e && e.message) || e);
    if (/Receiving end does not exist|Could not establish connection/i.test(msg)) {
      await injectContentScripts(tabId);
      return await attempt();
    }
    throw e;
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  void (async () => {
    try {
      if (!message || typeof message.type !== 'string') { sendResponse({ success: false, error: 'bad message' }); return; }

      if (message.type === 'bridge:get-status') {
        const tab = await getActiveTab();
        const settings = await settingsStore.get();
        const endpointOk = await checkEndpoint(settings.endpoint);
        sendResponse({
          success: true,
          onXhs: isXhsTab(tab),
          tabUrl: tab ? tab.url : '',
          endpoint: settings.endpoint,
          endpointOk,
          extVersion: EXT_VERSION,
        });
        return;
      }

      if (message.type === 'bridge:save-current-note') {
        const tab = await getActiveTab();
        if (!isXhsTab(tab)) { sendResponse({ success: false, error: '请在笔记页使用' }); return; }
        const settings = await settingsStore.get();
        const extracted = await sendToTab(tab.id, 'xhs:extract-note');
        const note = extracted.note;
        const nc = note && note.note_card || {};
        const st = nc.interact_info || {};
        const needsFeed = !(parseCountText(st.liked_count) > 0 || parseCountText(st.collected_count) > 0 || parseCountText(st.comment_count) > 0);
        let feed = null;
        if (needsFeed) {
          // MAIN world 里签名拉 feed 补齐互动指标（兜底主动请求）
          feed = await fetchFeedMainWorld(tab.id, note.id, note.xsec_token, xsecSourceFromUrl(note.source_url));
          if (feed && feed.ok && feed.note_card && feed.note_card.interact_info) {
            const fi = feed.note_card.interact_info;
            nc.interact_info = {
              liked_count: parseCountText(fi.liked_count),
              collected_count: parseCountText(fi.collected_count),
              comment_count: parseCountText(fi.comment_count),
              shared_count: parseCountText(fi.shared_count || fi.share_count),
            };
            nc.stats_source = 'feed';
          }
        }
        await sleep(randomIntBetween(settings.intervalMinMs, settings.intervalMaxMs));
        const result = await postJson(settings.endpoint + '/notes', { note });
        sendResponse({
          success: true,
          noteId: note.id,
          result,
          feed: {
            used: needsFeed,
            ok: Boolean(feed && feed.ok),
            reason: (feed && feed.reason) || '',
            itemCount: (feed && feed.itemCount) || 0,
            dataType: (feed && feed.dataType) || '',
            code: feed && feed.code,
            msg: (feed && feed.msg) || '',
          },
        });
        return;
      }

      if (message.type === 'bridge:save-comments') {
        const tab = await getActiveTab();
        if (!isXhsTab(tab)) { sendResponse({ success: false, error: '请在笔记页使用' }); return; }
        const settings = await settingsStore.get();
        const extracted = await sendToTab(tab.id, 'xhs:extract-comments');
        await sleep(randomIntBetween(settings.intervalMinMs, settings.intervalMaxMs));
        const result = await postJson(settings.endpoint + '/comments', { comments: extracted.comments, noteId: extracted.noteId });
        sendResponse({ success: true, count: extracted.comments.length, result });
        return;
      }

      if (message.type === 'bridge:debug-state') {
        const tab = await getActiveTab();
        if (!isXhsTab(tab)) { sendResponse({ success: false, error: '请在小红书页面使用' }); return; }
        const extracted = await sendToTab(tab.id, 'xhs:debug-state');
        sendResponse({ success: true, debug: extracted.debug });
        return;
      }

      if (message.type === 'bridge:collect-blogger') {
        const bloggerUrl = String(message.bloggerUrl || '').trim();
        const settings = await settingsStore.get();
        let tab = await getActiveTab();
        const onProfile = tab && isXhsTab(tab) && /\/user\/profile\//.test(tab.url || '');
        if (!onProfile) {
          if (bloggerUrl && /\/user\/profile\//.test(bloggerUrl)) {
            tab = await chrome.tabs.create({ url: bloggerUrl, active: true });
            await waitForTabComplete(tab.id);
            await sleep(1800);
          } else {
            sendResponse({ success: false, error: '请提供博主主页链接，或先在博主主页使用' });
            return;
          }
        }
        await injectContentScripts(tab.id);
        const extracted = await sendToTab(tab.id, 'xhs:collect-blogger');
        const notes = Array.isArray(extracted.notes) ? extracted.notes : [];
        if (notes.length === 0) {
          sendResponse({ success: false, error: '未捕获到笔记（请在扩展加载后刷新博主主页再试）', userId: extracted.userId });
          return;
        }
        await sleep(randomIntBetween(settings.intervalMinMs, settings.intervalMaxMs));
        const result = await postJson(settings.endpoint + '/batch', { notes });
        sendResponse({ success: true, userId: extracted.userId, total: notes.length, withStats: extracted.withStats, result });
        return;
      }

      if (message.type === 'bridge:collect-links') {
        const tab = await getActiveTab();
        if (!isXhsTab(tab)) { sendResponse({ success: false, error: '请在小红书页面使用' }); return; }
        const extracted = await sendToTab(tab.id, 'xhs:collect-links');
        sendResponse({ success: true, links: extracted.links });
        return;
      }

      if (message.type === 'bridge:set-endpoint') {
        const settings = await settingsStore.set({ endpoint: String(message.endpoint || DEFAULT_ENDPOINT) });
        sendResponse({ success: true, settings });
        return;
      }

      sendResponse({ success: false, error: 'unknown message type: ' + message.type });
    } catch (e) {
      sendResponse({ success: false, error: String((e && e.message) || e) });
    }
  })();
  return true;
});

async function checkEndpoint(endpoint) {
  try {
    const res = await fetch(endpoint + '/health', { method: 'GET' });
    return res.ok;
  } catch (_) {
    return false;
  }
}
