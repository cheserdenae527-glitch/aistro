// AiRestro XHS Bridge — 采集运行时工具（滚动/可见节点/验证页/间隔）
// 挂到 window.__AISTRO_CAPTURE_RUNTIME__，供 content.js 使用。
(() => {
  if (window.__AISTRO_CAPTURE_RUNTIME__) return;

  function normalizeText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function parseCountText(value) {
    const text = normalizeText(value).replace(/[\s,]/g, '');
    if (!text) return 0;
    const m = text.match(/(\d+(?:\.\d+)?)(万|亿)?/);
    if (!m) return 0;
    const num = parseFloat(m[1]);
    if (Number.isNaN(num)) return 0;
    if (m[2] === '万') return Math.round(num * 10000);
    if (m[2] === '亿') return Math.round(num * 100000000);
    return Math.round(num);
  }

  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  function randomIntBetween(min, max) {
    const lo = Math.ceil(Math.min(min, max));
    const hi = Math.floor(Math.max(min, max));
    return lo + Math.floor(Math.random() * (hi - lo + 1));
  }

  function isVisible(el, minW = 20, minH = 10) {
    if (!el || !(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > minW && rect.height > minH;
  }

  function collectVisibleNodes(selectors, root = document, limit = 1000) {
    const seen = new Set();
    const nodes = [];
    for (const selector of selectors) {
      if (!selector) continue;
      for (const node of Array.from(root.querySelectorAll(selector))) {
        if (seen.has(node) || !isVisible(node)) continue;
        seen.add(node);
        nodes.push(node);
        if (nodes.length >= limit) return nodes;
      }
    }
    return nodes;
  }

  function isChallengePage() {
    const title = normalizeText(document.title).toLowerCase();
    const body = normalizeText(document.body ? document.body.innerText : '').slice(0, 1200).toLowerCase();
    const patterns = ['just a moment', 'attention required', 'human verification', 'verifying you are human', 'security check', 'access denied', 'checking your browser', '人机验证', '人类验证', '安全验证', '访问被拒绝'];
    return patterns.some((p) => title.includes(p) || body.includes(p));
  }

  async function scrollAndTrack(selectors, options = {}) {
    // 目标数量 / 最大轮次 / 连续无新增上限
    const targetCount = Math.max(1, Number(options.targetCount || 200));
    const maxRounds = Math.max(1, Number(options.maxRounds || 28));
    const stallLimit = Math.max(1, Number(options.stallLimit || 5));
    const waitMs = Number(options.waitMs || 520);
    const rootResolver = typeof options.rootResolver === 'function' ? options.rootResolver : () => document;
    const diagnostics = [];
    let root = rootResolver();
    let nodes = collectVisibleNodes(selectors, root);
    let prevCount = nodes.length;
    let prevSig = nodeSignature(nodes);
    let stalled = 0;
    diagnostics.push({ event: 'scroll.start', count: prevCount, challenge: isChallengePage() });

    for (let round = 0; round < maxRounds; round += 1) {
      if (isChallengePage()) {
        diagnostics.push({ event: 'scroll.challenge', round });
        break;
      }
      root = rootResolver();
      nodes = collectVisibleNodes(selectors, root);
      const sig = nodeSignature(nodes);
      if (nodes.length >= targetCount) {
        diagnostics.push({ event: 'scroll.target_reached', round, count: nodes.length });
        break;
      }
      if (nodes.length <= prevCount && sig === prevSig) {
        stalled += 1;
      } else {
        stalled = 0;
        prevCount = nodes.length;
        prevSig = sig;
      }
      if (stalled >= stallLimit) {
        diagnostics.push({ event: 'scroll.stalled', round, count: nodes.length });
        break;
      }
      window.scrollBy({ top: Math.max(420, Math.floor((window.innerHeight || 600) * 0.75)), behavior: 'smooth' });
      await sleep(waitMs + Math.min(round, 5) * 80);
      diagnostics.push({ event: 'scroll.round', round, count: nodes.length });
    }
    root = rootResolver();
    nodes = collectVisibleNodes(selectors, root);
    diagnostics.push({ event: 'scroll.complete', count: nodes.length });
    return { nodes, diagnostics };
  }

  function nodeSignature(nodes) {
    return nodes.slice(0, 80).map((n) => {
      const id = n.getAttribute ? (n.getAttribute('id') || '') : '';
      const text = normalizeText(n.textContent || '').slice(0, 60);
      return id + '|' + text;
    }).join('\n');
  }

  window.__AISTRO_CAPTURE_RUNTIME__ = {
    normalizeText, parseCountText, sleep, randomIntBetween, isVisible, collectVisibleNodes, isChallengePage, scrollAndTrack, nodeSignature,
  };
})();
