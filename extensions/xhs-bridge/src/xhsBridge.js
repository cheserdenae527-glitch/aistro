// AiRestro XHS Bridge — 主世界被动拦截（学习 Beav xhsBridge 机制）
// 功能：monkey-patch window.fetch / XMLHttpRequest，把小红书接口 JSON 响应缓存进
// window.__AISTRO_XHS_CAPTURE__，并 postMessage 通知扩展（零额外请求）。
(() => {
  const FLAG = '__AISTRO_XHS_BRIDGE__';
  const STORE = '__AISTRO_XHS_CAPTURE__';
  const MAX_RESPONSES = 120;

  if (window[FLAG]) return;
  window[FLAG] = true;
  window[STORE] = Array.isArray(window[STORE]) ? window[STORE] : [];

  // 只缓存有数据价值的接口：edith / www 的 /api/sns/web/*；埋点（collect/metrics_report/apm 等）全部丢弃
  function shouldCapture(url) {
    try {
      const u = new URL(String(url || ''), location.href);
      const host = String(u.hostname || '').toLowerCase();
      const isXhs = /(^|\.)xiaohongshu\.com$/i.test(host) || /(^|\.)rednote\.com$/i.test(host);
      if (!isXhs) return false;
      const path = u.pathname || '';
      if (/^edith\./i.test(host) && /\/api\//.test(path)) return true;
      if (/\/api\/sns\/web\//.test(path)) {
        if (/metrics_report|history\/report|unread_count|collect|click|expose|feed\/recommend/i.test(path)) return false;
        return true;
      }
      return false;
    } catch (_) {
      return false;
    }
  }

  function parseJson(text) {
    const s = String(text || '').trim();
    if (!s || !/^[\[\{]/.test(s)) return null;
    try { return JSON.parse(s); } catch (_) { return null; }
  }

  function remember(url, method, body, result) {
    if (!url || !result) return;
    const store = window[STORE];
    store.push({ url: String(url), method: String(method || 'GET').toUpperCase(), body: body || null, result, capturedAt: Date.now() });
    while (store.length > MAX_RESPONSES) store.shift();
    window[STORE] = store;
    window.postMessage({
      source: 'aistro-xhs-bridge',
      type: 'api-response',
      payload: { url: String(url), method: String(method || 'GET').toUpperCase(), capturedAt: Date.now() },
    }, '*');
  }

  function requestUrl(input) {
    if (typeof input === 'string') return input;
    if (input instanceof URL) return input.toString();
    if (input && typeof input.url === 'string') return input.url;
    return '';
  }

  const nativeFetch = window.fetch;
  if (typeof nativeFetch === 'function') {
    window.fetch = async function aistroFetch(input, init) {
      const response = await nativeFetch.apply(this, arguments);
      const url = requestUrl(input);
      if (!shouldCapture(url)) return response;
      try {
        const clone = response.clone();
        const text = await clone.text();
        const result = parseJson(text);
        if (result) {
          remember(response.url || url, (init && init.method) || 'GET', (init && typeof init.body === 'string') ? parseJson(init.body) : null, result);
        }
      } catch (_) {
        // 捕获失败不影响页面请求
      }
      return response;
    };
  }

  if (window.XMLHttpRequest && XMLHttpRequest.prototype) {
    const nativeOpen = XMLHttpRequest.prototype.open;
    const nativeSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function aistroOpen(method, url) {
      this.__aistroMethod = method || 'GET';
      this.__aistroUrl = url || '';
      return nativeOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function aistroSend(body) {
      this.addEventListener('loadend', () => {
        const url = this.responseURL || this.__aistroUrl || '';
        if (!shouldCapture(url)) return;
        const result = parseJson(this.responseText);
        if (result) remember(url, this.__aistroMethod || 'GET', typeof body === 'string' ? parseJson(body) : null, result);
      });
      return nativeSend.apply(this, arguments);
    };
  }
})();
