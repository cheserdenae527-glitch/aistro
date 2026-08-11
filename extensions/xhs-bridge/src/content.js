// AiRestro XHS Bridge — 内容提取器 v4
// 数据源：被动拦截 → INITIAL_STATE → 兜底主动 feed（页面内 mnsv2 签名）→ DOM
(() => {
  if (window.__AISTRO_XHS_CONTENT_LOADED__) return;
  window.__AISTRO_XHS_CONTENT_LOADED__ = true;
  const EXT_VERSION = 'v4.9';
  const CAPTURE_STORE = '__AISTRO_XHS_CAPTURE__';
  const localCapture = [];

  function normalizeRecord(p) {
    return {
      url: String((p && p.url) || ''),
      method: String((p && p.method) || 'GET').toUpperCase(),
      body: (p && p.body) || null,
      result: (p && p.result) || null,
      capturedAt: Number((p && p.capturedAt) || Date.now()),
    };
  }

  window.addEventListener('message', (event) => {
    if (event.source !== window) return;
    if (event.data && event.data.source === 'aistro-xhs-bridge' && event.data.type === 'api-response') {
      const rec = normalizeRecord(event.data.payload);
      if (!rec.url) return;
      localCapture.push(rec);
      while (localCapture.length > 200) localCapture.shift();
    }
  });

  async function refreshCapturedFromMain() {
    try {
      if (!chrome.runtime || typeof chrome.runtime.sendMessage !== 'function') return;
      const res = await chrome.runtime.sendMessage({ type: 'bridge:read-captured' });
      const records = res && Array.isArray(res.records) ? res.records : [];
      if (!records.length) return;
      const existing = new Set(localCapture.map((r) => r.url + '|' + r.method + '|' + r.capturedAt));
      for (const item of records) {
        const rec = normalizeRecord(item);
        if (!rec.url) continue;
        const key = rec.url + '|' + rec.method + '|' + rec.capturedAt;
        if (existing.has(key)) continue;
        existing.add(key);
        localCapture.push(rec);
      }
      while (localCapture.length > 200) localCapture.shift();
    } catch (_) {}
  }

  function rt() { return window.__AISTRO_CAPTURE_RUNTIME__ || null; }
  function normalizeText(v) { return String(v || '').replace(/\s+/g, ' ').trim(); }
  function parseCountText(v) { return rt() ? rt().parseCountText(v) : 0; }

  function readInitialState() {
    try {
      if (window.__INITIAL_STATE__ && typeof window.__INITIAL_STATE__ === 'object') return window.__INITIAL_STATE__;
    } catch (_) {}
    try {
      for (const script of document.querySelectorAll('script')) {
        const text = script.textContent || '';
        if (!text.includes('window.__INITIAL_STATE__=')) continue;
        const jsonText = text.replace('window.__INITIAL_STATE__=', '').replace(/undefined/g, 'null').replace(/;$/, '');
        return JSON.parse(jsonText);
      }
    } catch (_) {}
    return null;
  }

  function getNoteIdFromMask() {
    const mask = document.querySelector('.note-detail-mask[note-id]');
    if (mask) return String(mask.getAttribute('note-id') || '').trim();
    return '';
  }

  function getCurrentNoteId() {
    const fromMask = getNoteIdFromMask();
    if (fromMask) return fromMask;
    const pathMatch = location.pathname.match(/\/(?:explore|discovery\/item)\/([A-Za-z0-9]+)/);
    if (pathMatch && pathMatch[1]) return pathMatch[1];
    try {
      const params = new URLSearchParams(location.search);
      for (const key of ['noteId', 'note_id', 'id', 'itemId']) {
        const v = params.get(key);
        if (v) return v;
      }
    } catch (_) {}
    const state = readInitialState();
    const detailMap = state && state.note && state.note.noteDetailMap;
    if (detailMap && typeof detailMap === 'object') {
      const keys = Object.keys(detailMap);
      if (keys.length === 1) return keys[0];
    }
    return '';
  }

  function getXsecToken() {
    try { return new URL(location.href).searchParams.get('xsec_token') || ''; } catch (_) { return ''; }
  }

  function getXsecSource() {
    try { return new URL(location.href).searchParams.get('xsec_source') || 'pc_user'; } catch (_) { return 'pc_user'; }
  }

  // MAIN world 的 window 属性在 ISOLATED world 读不到（Beav 同款限制），
  // 记录统一来自 postMessage 响应体 + background 的主世界兜底读取。
  function getCapturedRecords() {
    return localCapture.slice();
  }

  // ── 兜底主动 feed：页面内 mnsv2 签名（对照 Beav seccoreSign）──
  function getCookie(name) {
    const cookies = document.cookie.split(';');
    for (const item of cookies) {
      const c = item.trim();
      if (c.startsWith(name + '=')) return c.slice(name.length + 1);
    }
    return '';
  }

  function crc32(value) {
    const bytes = typeof value === 'string' ? Array.from(new TextEncoder().encode(value)) : Array.from(value || []);
    let crc = -1;
    for (const byte of bytes) {
      crc ^= byte;
      for (let i = 0; i < 8; i += 1) crc = (crc & 1) ? ((crc >>> 1) ^ 0xedb88320) : (crc >>> 1);
    }
    return ((crc ^ -1) >>> 0);
  }

  function customBase64(inputBytes) {
    const alphabet = 'ZmserbBoHQtNP+wOcza/LpngG8yJq42KWYj0DSfdikx3VT16IlUAFM97hECvuRX5';
    const bytes = Array.isArray(inputBytes) ? inputBytes : Array.from(inputBytes || []);
    let out = '';
    for (let i = 0; i < bytes.length; i += 3) {
      const b1 = bytes[i];
      const b2 = i + 1 < bytes.length ? bytes[i + 1] : NaN;
      const b3 = i + 2 < bytes.length ? bytes[i + 2] : NaN;
      const t = (b1 << 16) | ((Number.isNaN(b2) ? 0 : b2) << 8) | (Number.isNaN(b3) ? 0 : b3);
      out += alphabet[(t >>> 18) & 63];
      out += alphabet[(t >>> 12) & 63];
      out += Number.isNaN(b2) ? '=' : alphabet[(t >>> 6) & 63];
      out += Number.isNaN(b3) ? '=' : alphabet[t & 63];
    }
    return out;
  }

  function getOS() {
    const ua = String(window.navigator ? navigator.userAgent : '').toLowerCase();
    if (ua.includes('android')) return 'Android';
    if (ua.includes('iphone') || ua.includes('ipad') || ua.includes('ipod')) return 'iOS';
    if (ua.includes('macintosh')) return 'Mac OS';
    if (ua.includes('windows')) return 'Windows';
    if (ua.includes('linux')) return 'Linux';
    return 'PC';
  }

  function getPlatform(os) {
    switch (os) {
      case 'Windows': return 0;
      case 'Android': return 2;
      case 'iOS': return 1;
      case 'Mac OS': return 3;
      case 'Linux': return 4;
      default: return 5;
    }
  }

  function getXSCommon() {
    const b1 = (() => { try { return localStorage.getItem('b1') || ''; } catch (_) { return ''; } })();
    const b1b1 = (() => { try { return localStorage.getItem('b1b1') || '1'; } catch (_) { return '1'; } })();
    const os = getOS();
    const payload = {
      s0: getPlatform(os), s1: '', x0: b1b1, x1: '4.2.6', x2: os, x3: 'xhs-pc-web', x4: '4.83.1',
      x5: getCookie('a1'), x6: '', x7: '', x8: b1, x9: crc32(String(b1)), x10: 0, x11: 'normal',
    };
    return customBase64(new TextEncoder().encode(JSON.stringify(payload)));
  }

  async function seccoreSign(path, body) {
    if (typeof window.mnsv2 !== 'function' || typeof window.md5 !== 'function') {
      throw new Error('页面缺少 mnsv2/md5，无法生成签名');
    }
    let content = path;
    const tag = Object.prototype.toString.call(body);
    if (tag === '[object Object]' || tag === '[object Array]') content += JSON.stringify(body);
    else if (typeof body === 'string') content += body;
    const contentMd5 = window.md5(content);
    const pathMd5 = window.md5(path);
    const signature = await window.mnsv2(content, contentMd5, pathMd5);
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

  function xB3TraceId() {
    let v = '';
    for (let i = 0; i < 16; i += 1) v += 'abcdef0123456789'.charAt(Math.floor(Math.random() * 16));
    return v;
  }

  async function rawFeedResponse(noteId, xsecToken, xsecSource) {
    if (!noteId || !xsecToken) return null;
    const path = '/api/sns/web/v1/feed';
    const body = {
      source_note_id: noteId,
      image_formats: ['jpg', 'webp', 'avif'],
      extra: { need_body_topic: '1' },
      xsec_source: xsecSource || 'pc_user',
      xsec_token: xsecToken,
    };
    const headers = {
      accept: 'application/json, text/plain, */*',
      'content-type': 'application/json;charset=UTF-8',
      'x-s': await seccoreSign(path, body),
      'x-t': String(Date.now()),
      'x-s-common': getXSCommon(),
      'x-xray-traceid': traceId(),
      'x-b3-traceid': xB3TraceId(),
    };
    const res = await fetch('https://edith.xiaohongshu.com' + path, {
      method: 'POST', credentials: 'include', headers, body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    const json = await res.json();
    if (!json || json.success === false) return null;
    const data = json.data || (json.result && json.result.data) || null;
    const items = data && Array.isArray(data.items) ? data.items : [];
    for (const it of items) {
      const nc = (it && (it.note_card || it.noteCard)) || it || {};
      const id = String(nc.note_id || nc.noteId || nc.id || it && (it.id || it.note_id) || '');
      if (id === String(noteId)) return nc;
    }
    return json;
  }

  async function fetchFeedNoteCard(noteId, xsecToken, xsecSource) {
    // 有界重试：data:null 是间歇性风控形态，最多重试 1 次（间隔 1.2s），避免死循环
    let json = await rawFeedResponse(noteId, xsecToken, xsecSource);
    if (json && (json.success === false || !json.data)) {
      await new Promise((r) => setTimeout(r, 1200));
      json = await rawFeedResponse(noteId, xsecToken, xsecSource);
    }
    if (!json || json.success === false || !json.data) return null;
    const d = json.data;
    const items = d && Array.isArray(d.items) ? d.items : [];
    for (const it of items) {
      const nc = (it && (it.note_card || it.noteCard)) || it || {};
      const id = String(nc.note_id || nc.noteId || nc.id || (it && (it.id || it.note_id)) || '');
      if (id === String(noteId)) return nc;
    }
    return items[0] && (items[0].note_card || items[0].noteCard) || null;
  }

  // 主动 feed 探测：报告响应结构（用于调试定位 data:null）
  async function probeFeed(noteId, xsecToken, xsecSource) {
    try {
      const json = await rawFeedResponse(noteId, xsecToken, xsecSource);
      if (!json) return { ok: false, reason: 'no response' };
      const d = json.data;
      const items = d && Array.isArray(d.items) ? d.items : [];
      const first = items[0] || null;
      const nc = first && (first.note_card || first.noteCard) || null;
      return {
        ok: Boolean(json && json.success !== false && d),
        topKeys: json && typeof json === 'object' ? Object.keys(json) : [],
        code: json.code,
        msg: String(json.msg || '').slice(0, 80),
        dataType: d === null ? 'null' : typeof d,
        itemCount: items.length,
        interactInfoPresent: Boolean(nc && nc.interact_info),
        firstItemId: first ? String(first.id || first.note_id || first.noteId || '') : '',
      };
    } catch (e) {
      return { ok: false, reason: String((e && e.message) || e).slice(0, 120) };
    }
  }

  // ── 被动拦截里递归找 note_card ──
  function walkForNote(obj, noteId, depth) {
    if (!obj || typeof obj !== 'object' || depth > 8) return null;
    if (Array.isArray(obj)) {
      for (const item of obj) {
        const hit = walkForNote(item, noteId, depth + 1);
        if (hit) return hit;
      }
      return null;
    }
    const nc = obj.note_card || obj.noteCard;
    if (nc && typeof nc === 'object') {
      const id = String(obj.id || obj.note_id || obj.noteId || nc.note_id || nc.noteId || nc.id || '');
      if (id === String(noteId)) return nc;
    }
    if (String(obj.id || obj.note_id || obj.noteId || '') === String(noteId) && (obj.display_title || obj.desc || obj.interact_info || obj.image_list)) {
      return obj;
    }
    for (const key of Object.keys(obj)) {
      if (key === 'note_card' || key === 'noteCard') continue;
      const v = obj[key];
      if (v && typeof v === 'object') {
        const hit = walkForNote(v, noteId, depth + 1);
        if (hit) return hit;
      }
    }
    return null;
  }

  function findNoteCardFromCapture(noteId) {
    if (!noteId) return null;
    for (const record of getCapturedRecords().slice().reverse()) {
      if (!record.result) continue;
      const hit = walkForNote(record.result, noteId, 0);
      if (hit) return hit;
    }
    return null;
  }

  function findNoteTokenFromCapture(noteId) {
    if (!noteId) return '';
    for (const record of getCapturedRecords().slice().reverse()) {
      if (!record.result) continue;
      const token = findNoteItemToken(record.result, noteId, 0);
      if (token) return token;
    }
    return '';
  }

  function findNoteItemToken(obj, noteId, depth) {
    if (!obj || typeof obj !== 'object' || depth > 8) return '';
    if (Array.isArray(obj)) {
      for (const item of obj) {
        const token = findNoteItemToken(item, noteId, depth + 1);
        if (token) return token;
      }
      return '';
    }
    const nc = obj.note_card || obj.noteCard;
    const id = String(obj.id || obj.note_id || obj.noteId || (nc && (nc.note_id || nc.noteId || nc.id)) || '');
    if (id === String(noteId)) {
      const token = String(obj.xsec_token || obj.xsecToken || (nc && (nc.xsec_token || nc.xsecToken)) || '');
      if (token) return token;
    }
    for (const key of Object.keys(obj)) {
      if (key === 'note_card' || key === 'noteCard') continue;
      const value = obj[key];
      if (value && typeof value === 'object') {
        const token = findNoteItemToken(value, noteId, depth + 1);
        if (token) return token;
      }
    }
    return '';
  }

  function unwrapEntry(entry) {
    if (entry && typeof entry === 'object' && entry.note && typeof entry.note === 'object') return entry.note;
    return entry;
  }

  function noteFromState(noteId) {
    const state = readInitialState();
    if (!state || !state.note || !state.note.noteDetailMap) return null;
    const map = state.note.noteDetailMap;
    const keys = Object.keys(map);
    if (!keys.length) return null;
    const candidates = [noteId].concat(getNoteIdFromMask() ? [getNoteIdFromMask()] : []);
    try {
      const sp = new URLSearchParams(location.search);
      ['noteId', 'note_id', 'id', 'itemId'].forEach((k) => { const v = sp.get(k); if (v) candidates.push(v); });
    } catch (_) {}
    const uniq = Array.from(new Set(candidates.filter(Boolean)));
    for (const cand of uniq) {
      if (map[cand]) return unwrapEntry(map[cand]);
      const byKey = keys.find((k) => k === cand || k.includes(cand) || cand.includes(k));
      if (byKey) return unwrapEntry(map[byKey]);
      const byId = keys.find((k) => {
        const e = unwrapEntry(map[k]);
        const ids = [e && (e.noteId || e.id || e.note_id), e && e.noteCard && (e.noteCard.note_id || e.noteCard.id)];
        return ids.some((x) => x && (String(x) === String(cand) || String(x).includes(String(cand)) || String(cand).includes(String(x))));
      });
      if (byId) return unwrapEntry(map[byId]);
    }
    const domTitle = normalizeText((document.querySelector('#detail-title') || {}).innerText || '');
    if (domTitle) {
      const byTitle = keys.find((k) => {
        const e = unwrapEntry(map[k]);
        const t = normalizeText((e && (e.title || e.display_title || (e.noteCard && (e.noteCard.title || e.noteCard.display_title)))) || '');
        return t && (t === domTitle || t.includes(domTitle) || domTitle.includes(t));
      });
      if (byTitle) return unwrapEntry(map[byTitle]);
    }
    // 注意：不做"单键兜底"——noteDetailMap 可能是上一篇笔记的残留状态，
    // 无精确匹配时返回 null，让 DOM 兜底取当前页面真实内容，避免数据错配。
    return null;
  }

  function pickImageUrl(item) {
    if (!item) return '';
    if (typeof item === 'string') return item;
    if (Array.isArray(item)) { for (const x of item) { const u = pickImageUrl(x); if (u) return u; } return ''; }
    if (typeof item !== 'object') return '';
    return String(item.urlDefault || item.urlPre || item.url || item.urlDefaultWebp || item.masterUrl || item.src || '');
  }

  function extractImages(rawNc) {
    const nc = rawNc && rawNc.noteCard ? rawNc.noteCard : rawNc || {};
    const list = Array.isArray(nc.image_list) ? nc.image_list : Array.isArray(nc.imageList) ? nc.imageList : Array.isArray(nc.images) ? nc.images : [];
    const urls = [];
    const seen = new Set();
    const push = (v) => { if (v && /^https?:\/\//.test(v) && !seen.has(v)) { seen.add(v); urls.push(v); } };
    for (const item of list) {
      if (item && Array.isArray(item.info_list)) { for (const info of item.info_list) push(info && (info.url || info.urlDefault)); }
      push(pickImageUrl(item));
    }
    return urls;
  }

  function extractVideo(rawNc) {
    const nc = rawNc && rawNc.noteCard ? rawNc.noteCard : rawNc || {};
    const video = nc.video || {};
    const media = video.media || {};
    if (media.stream && typeof media.stream === 'object') {
      let best = '';
      let bestBitrate = -1;
      for (const fmt of Object.values(media.stream)) {
        if (!Array.isArray(fmt)) continue;
        for (const it of fmt) {
          const url = (it && (it.master_url || it.url)) || '';
          const bitrate = Number((it && (it.video_bitrate || it.avg_bitrate)) || 0);
          if (url && /^https?:\/\//.test(url) && bitrate >= bestBitrate) { bestBitrate = bitrate; best = url; }
        }
      }
      if (best) return best;
    }
    return '';
  }

  function domFallback() {
    // 作者信息限定在笔记容器内找，避免匹配到全局导航头像（曾导致作者 ID 取错）
    const noteRoot = document.querySelector('#noteContainer, .note-container, .note-detail-mask, .note-content') || document;
    const metaContent = (sel) => { const el = document.querySelector(sel); return el ? String(el.content || el.getAttribute('content') || '').trim() : ''; };
    const title =
      (document.querySelector('#detail-title') || {}).innerText ||
      (document.querySelector('.note-title') || {}).innerText ||
      (document.querySelector('.title') || {}).innerText ||
      metaContent('meta[property="og:title"]') ||
      document.title || '';
    const descEls = Array.from(document.querySelectorAll('#detail-desc .note-text, .desc .note-text, .note-content .note-text'));
    let desc = descEls.map((el) => normalizeText(el.innerText || '')).filter(Boolean).join('\n\n');
    if (!desc) desc = metaContent('meta[property="og:description"]') || metaContent('meta[name="description"]');
    const authorEl = noteRoot.querySelector('.author .username, .author-wrapper .username, .username');
    const author = normalizeText((authorEl || {}).innerText || metaContent('meta[name="author"]') || '');
    const authorLink = noteRoot.querySelector('.author a[href*="/user/"], .author-wrapper a[href*="/user/"], a[href*="/user/profile/"]');
    const authorHref = (authorLink || {}).href || '';
    const authorIdMatch = authorHref.match(/\/user\/profile\/([^/?#]+)/);
    const images = [];
    const seen = new Set();
    for (const img of document.querySelectorAll('.note-slider .swiper-slide:not(.swiper-slide-duplicate) img, .note-content .img-container img, .note-content img, .swiper-slide img, #noteContainer img, [class*="img-container"] img')) {
      const src = img.currentSrc || img.src || '';
      if (src && /^https?:\/\//.test(src) && !seen.has(src)) { seen.add(src); images.push(src); }
    }
    for (const sel of ['meta[property="og:image"]', 'meta[property="og:image:url"]', 'meta[name="twitter:image"]']) {
      const v = metaContent(sel);
      if (v && /^https?:\/\//.test(v) && !seen.has(v)) { seen.add(v); images.push(v); }
    }
    let videoUrl = '';
    const videoEl = document.querySelector('video[mediatype="video"], .xgplayer video, video');
    if (videoEl) { const s = videoEl.currentSrc || videoEl.src || ''; if (/^https?:\/\//.test(s)) videoUrl = s; }
    if (!videoUrl) {
      for (const sel of ['meta[property="og:video"]', 'meta[property="og:video:url"]', 'meta[property="og:video:secure_url"]']) {
        const v = metaContent(sel);
        if (v && /^https?:\/\//.test(v)) { videoUrl = v; break; }
      }
    }
    return { title, desc, author, authorId: authorIdMatch ? authorIdMatch[1] : '', images, videoUrl };
  }

  function hasAnyCount(interact) {
    return interact && (Number(interact.liked_count) > 0 || Number(interact.collected_count) > 0 || Number(interact.comment_count) > 0);
  }

  function statsInteractComplete(rawNc) {
    const nc = rawNc && rawNc.noteCard ? rawNc.noteCard : rawNc || {};
    const it = nc.interact_info || {};
    return ['liked_count', 'collected_count', 'comment_count', 'shared_count', 'share_count']
      .every((k) => it[k] !== undefined && it[k] !== null && it[k] !== '');
  }

  function mapNoteCard(rawNc, statsSource) {
    const nc = rawNc && rawNc.noteCard ? rawNc.noteCard : rawNc || {};
    const user = nc.user || {};
    const interact = nc.interact_info || {};
    const images = extractImages(nc);
    const videoUrl = extractVideo(nc);
    return {
      display_title: normalizeText(nc.display_title || nc.title || ''),
      title: normalizeText(nc.display_title || nc.title || ''),
      desc: normalizeText(nc.desc || ''),
      type: String(nc.type || (videoUrl ? 'video' : 'normal')),
      user: {
        user_id: String(user.user_id || user.userId || user.id || ''),
        nickname: normalizeText(user.nickname || user.nick_name || ''),
        avatar: String(user.avatar || ''),
      },
      interact_info: {
        liked_count: interact ? parseCountText(interact.liked_count) : 0,
        collected_count: interact ? parseCountText(interact.collected_count) : 0,
        comment_count: interact ? parseCountText(interact.comment_count) : 0,
        shared_count: interact ? parseCountText(interact.shared_count || interact.share_count) : 0,
      },
      image_list: images.map((url) => ({ info_list: [{ url, image_scene: 'WB_DFT' }] })),
      video: videoUrl ? { media: { stream: { hd: [{ master_url: videoUrl, video_bitrate: 0 }] } } } : null,
      time: nc.time || nc.last_update_time || null,
      stats_source: statsSource,
    };
  }

  async function buildNotePayload() {
    await refreshCapturedFromMain();
    const noteId = getCurrentNoteId();
    const xsecToken = getXsecToken() || findNoteTokenFromCapture(noteId);
    const xsecSource = getXsecSource();
    const sourceUrl = location.href;

    // 1) 被动拦截（数据最全）
    let rawNc = findNoteCardFromCapture(noteId);
    let statsSource = rawNc ? 'capture' : null;

    // 2) INITIAL_STATE（内容可靠）
    if (!rawNc) {
      rawNc = noteFromState(noteId);
      statsSource = rawNc ? 'state' : null;
    }

    // 3) 互动指标补齐：只要四项（赞/藏/评/分享）缺任一字段就主动 feed 补全，
    //    不能只凭"点赞有值"就认为完整（列表接口经常只返回 liked_count）。
    let statsFull = statsInteractComplete(rawNc);
    if (rawNc && !statsFull) {
      try {
        const feedNc = await fetchFeedNoteCard(noteId, xsecToken, xsecSource);
        if (feedNc && statsInteractComplete(feedNc)) {
          rawNc = Object.assign({}, rawNc, feedNc, { interact_info: feedNc.interact_info });
          statsSource = 'feed';
          statsFull = true;
        } else if (feedNc && feedNc.interact_info && hasAnyCount(feedNc.interact_info)) {
          rawNc = Object.assign({}, rawNc, feedNc, { interact_info: feedNc.interact_info });
          statsSource = 'feed';
        }
      } catch (_) {}
    }

    if (rawNc) {
      return {
        id: noteId, xsec_token: xsecToken, source_url: sourceUrl,
        capture_channel: 'aistro-bridge',
        capture_has_full_stats: statsFull,
        note_card: mapNoteCard(rawNc, statsSource || 'none'),
      };
    }

    // 4) DOM 兜底
    const dom = domFallback();
    return {
      id: noteId, xsec_token: xsecToken, source_url: sourceUrl,
      capture_channel: 'aistro-bridge',
      capture_has_full_stats: false,
      note_card: {
        display_title: dom.title, title: dom.title, desc: dom.desc,
        type: dom.videoUrl ? 'video' : 'normal',
        user: { user_id: dom.authorId, nickname: dom.author, avatar: '' },
        interact_info: { liked_count: 0, collected_count: 0, comment_count: 0, shared_count: 0 },
        image_list: dom.images.map((url) => ({ info_list: [{ url, image_scene: 'WB_DFT' }] })),
        video: dom.videoUrl ? { media: { stream: { hd: [{ master_url: dom.videoUrl, video_bitrate: 0 }] } } } : null,
        time: null,
        stats_source: 'dom',
      },
    };
  }

  async function debugState() {
    await refreshCapturedFromMain();
    const noteId = getCurrentNoteId();
    const state = readInitialState();
    const detailMap = state && state.note && state.note.noteDetailMap;
    const stateNote = noteFromState(noteId);
    const captureNc = findNoteCardFromCapture(noteId);
    const dom = domFallback();
    const captured = getCapturedRecords();
    const apiUrls = captured.map((r) => String(r.url || '')).filter((u) => u.includes('/api/'));
    const stateNc = stateNote && (stateNote.noteCard || stateNote);
    return {
      extVersion: EXT_VERSION,
      url: location.href,
      noteId,
      detailMapKeys: detailMap && typeof detailMap === 'object' ? Object.keys(detailMap) : [],
      stateNoteMatched: Boolean(stateNote),
      captureNoteMatched: Boolean(captureNc),
      captureNoteFields: captureNc ? Object.keys(captureNc) : [],
      user: captureNc ? captureNc.user : (stateNc ? stateNc.user : null),
      interactInfoPresent: Boolean(captureNc ? captureNc.interact_info : (stateNc ? stateNc.interact_info : false)),
      captureHasFullStats: statsInteractComplete(captureNc || stateNc),
      imageListCount: captureNc ? extractImages(captureNc).length : (stateNote ? extractImages(stateNote).length : 0),
      videoFromCapture: extractVideo(captureNc || {}),
      mnsv2Available: typeof window.mnsv2 === 'function',
      md5Available: typeof window.md5 === 'function',
      dom: { title: dom.title.slice(0, 60), author: dom.author, authorId: dom.authorId, images: dom.images.length, video: dom.videoUrl.slice(0, 60) },
      capturedApiCount: captured.length,
      capturedApis: apiUrls.slice(-10),
      feedProbe: await probeFeed(noteId, getXsecToken(), getXsecSource()),
      domCountProbe: (() => {
        const out = [];
        const seen = new Set();
        for (const el of document.querySelectorAll('[class*="engage"], [class*="interact"], [class*="like"], [class*="collect"], [class*="comment"], [class*="count"], button, [role="button"]')) {
          const t = normalizeText(el.innerText || '').slice(0, 40);
          if (!t) continue;
          if (/(\d+(?:\.\d+)?\s*万?)\s*(赞|收藏|评论|分享)|(赞|收藏|评论|分享)[^\d]{0,4}(\d+(?:\.\d+)?\s*万?)/.test(t)) {
            const key = el.tagName + '.' + String(el.className || '').slice(0, 60) + '|' + t;
            if (!seen.has(key)) { seen.add(key); out.push({ tag: el.tagName, cls: String(el.className || '').slice(0, 80), text: t }); }
          }
          if (out.length >= 25) break;
        }
        return out;
      })(),
      feedRecords: getCapturedRecords()
        .filter((r) => /\/api\/sns\/web\/v1\/feed/.test(String(r.url || '')))
        .map((r) => {
          const res = r.result || {};
          const d = res.data;
          const items = d && Array.isArray(d.items) ? d.items : [];
          const first = items[0] || null;
          return {
            url: String(r.url || '').slice(0, 80),
            success: res.success, code: res.code, msg: String(res.msg || '').slice(0, 60),
            dataKeys: d && typeof d === 'object' ? Object.keys(d).slice(0, 15) : [],
            itemCount: items.length,
            firstItemKeys: first ? Object.keys(first).slice(0, 20) : [],
            firstItemId: first ? String(first.id || first.note_id || first.noteId || '') : '',
            firstNoteCardKeys: first && first.note_card ? Object.keys(first.note_card).slice(0, 25) : [],
          };
        }),
    };
  }

  // A 档批量：博主主页滚动后，从被动拦截的 user_posted 响应提取笔记（自带 interact_info）
  function collectBloggerNotesFromCapture(userId) {
    const notes = [];
    const seen = new Set();
    for (const record of getCapturedRecords()) {
      const url = String(record.url || '');
      if (!/\/api\/sns\/web\/v1\/user_posted/.test(url)) continue;
      const data = record.result && record.result.data;
      const list = data && Array.isArray(data.notes) ? data.notes : [];
      for (const it of list) {
        const nc = (it && (it.note_card || it.noteCard)) || it || {};
        const id = String(nc.note_id || nc.noteId || nc.id || (it && (it.id || it.note_id)) || '');
        if (!id || seen.has(id)) continue;
        seen.add(id);
        const token = String((it && (it.xsec_token || it.xsecToken)) || nc.xsec_token || nc.xsecToken || '');
        const source = id + (token ? '?xsec_token=' + encodeURIComponent(token) + '&xsec_source=pc_user' : '');
        notes.push({
          id,
          xsec_token: token,
          note_card: nc,
          source_url: 'https://www.xiaohongshu.com/explore/' + source,
          capture_channel: 'aistro-bridge',
          capture_has_full_stats: statsInteractComplete(nc),
        });
      }
    }
    return notes;
  }

  async function collectBlogger() {
    await refreshCapturedFromMain();
    const userId = (location.pathname.match(/\/user\/profile\/([^/?#]+)/) || [])[1] || '';
    if (!userId) return { success: false, error: '当前不是博主主页' };
    const runtime = rt();
    if (runtime) {
      // 有界滚动：页面自己加载 user_posted 翻页，被动拦截拿到带互动指标的笔记
      await runtime.scrollAndTrack(['a[href*="/explore/"], a[href*="/discovery/item/"]'], {
        targetCount: 200, maxRounds: 12, stallLimit: 3, waitMs: 600,
          onProgress: (p) => {
            try {
              chrome.runtime.sendMessage({ type: 'aistro-progress', phase: 'blogger', current: p.count, total: p.targetCount, label: '正在滚动采集博主作品' });
            } catch (_) {}
          },
      });
    }
    const fromCapture = collectBloggerNotesFromCapture(userId);
    const links = collectVisibleNoteLinks();
    const merged = new Map();
    for (const n of fromCapture) merged.set(n.id, n);
    for (const l of links) {
      if (!merged.has(l.noteId)) {
        merged.set(l.noteId, { id: l.noteId, xsec_token: '', note_card: {}, source_url: l.url, capture_channel: 'aistro-bridge', capture_has_full_stats: false });
      }
    }
    const notes = Array.from(merged.values());
    const withStats = notes.filter((n) => {
      const it = (n.note_card && n.note_card.interact_info) || {};
      return Number(it.liked_count || 0) > 0 || Number(it.collected_count || 0) > 0 || Number(it.comment_count || 0) > 0;
    }).length;
    return { success: true, userId, total: notes.length, withStats, notes };
  }

  function collectVisibleNoteLinks() {
    const links = [];
    const seen = new Set();
    for (const a of document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]')) {
      const href = a.href || a.getAttribute('href') || '';
      if (!href) continue;
      let u;
      try { u = new URL(href, location.href); } catch (_) { continue; }
      if (!/xiaohongshu\.com|rednote\.com/i.test(u.hostname)) continue;
      const m = u.pathname.match(/\/(?:explore|discovery\/item)\/([A-Za-z0-9]+)/);
      if (!m) continue;
      const token = u.searchParams.get('xsec_token') || '';
      const url = 'https://www.xiaohongshu.com/explore/' + m[1] + (token ? '?xsec_token=' + encodeURIComponent(token) + '&xsec_source=pc_user' : '');
      if (seen.has(url)) continue;
      seen.add(url);
      links.push({ noteId: m[1], url, title: normalizeText((a.querySelector('.title') || a).innerText || '') });
    }
    return links;
  }

  function normalizeBlockText(value) {
    return String(value || '').replace(/\r/g, '').replace(/\n{3,}/g, '\n\n').trim();
  }

  function pickCommentText(node) {
    const selectors = ['.content', '.comment-content', '.note-text', '[class*="content"]'];
    for (const selector of selectors) {
      const el = node.querySelector(selector);
      const candidate = normalizeBlockText(el ? (el.innerText || el.textContent || '') : '');
      if (candidate && candidate.length > 2) return candidate;
    }
    return normalizeBlockText(node.innerText || node.textContent || '');
  }

  function pickCommentAuthor(node) {
    const selectors = ['.author .name', '.user-name', '.username', '.name', '[class*="author"]', '[class*="name"]'];
    for (const selector of selectors) {
      const text = normalizeText((node.querySelector(selector) || {}).textContent || '');
      if (text && text.length <= 32 && !/赞|回复|展开|更多/.test(text)) return text;
    }
    return '';
  }

  function pickCommentMeta(node) {
    const text = normalizeText(node.innerText || node.textContent || '');
    const createdAt = (text.match(/\d{1,2}-\d{1,2}|\d{4}-\d{1,2}-\d{1,2}|昨天|今天|刚刚|\d+\s*(分钟|小时|天)前/) || [])[0] || '';
    const locationRaw = normalizeText((node.querySelector('.date .location, [class*="location"]') || {}).textContent || '') ||
      (text.match(/IP属地[:：]?\s*[\u4e00-\u9fa5A-Za-z]+/) || [])[0] || '';
    const location = locationRaw.replace(/^IP属地[:：]?/, '');
    const likeText = normalizeText((node.querySelector('.like-wrapper .count, [class*="like"] [class*="count"]') || {}).textContent || '');
    const replyText = normalizeText((node.querySelector('.reply .count, [class*="reply"] [class*="count"]') || {}).textContent || '');
    return { createdAt, location, likes: parseCountText(likeText), replies: parseCountText(replyText) };
  }

  async function extractComments() {
    const runtime = rt();
    if (!runtime) return { success: false, error: 'capture runtime not loaded' };
    const itemSelectors = ['.comment-item', '.comment-container', '.list-item', '[class*="comment-item"]', '[class*="commentItem"]'];
    const rootSelectors = ['.comments-container', '.comments-el', '.comment-list', '[class*="comments"]'];
    for (let round = 0; round < 3; round += 1) {
      let clicked = 0;
      for (const btn of document.querySelectorAll('button, [role="button"], .show-more, .more, [class*="show-more"]')) {
        const t = normalizeText(btn.textContent || '');
        if (!/展开|全部回复|查看更多|更多回复|条回复/.test(t)) continue;
        try { btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); clicked += 1; } catch (_) {}
      }
      if (!clicked) break;
      await runtime.sleep(400);
    }
    const { nodes, diagnostics } = await runtime.scrollAndTrack(itemSelectors, {
      rootResolver: () => document.querySelector(rootSelectors.join(',')) || document,
      targetCount: 200, maxRounds: 28, stallLimit: 5, waitMs: 520,
    });
    const comments = [];
    const seen = new Set();
    for (const node of nodes) {
      const text = normalizeBlockText(pickCommentText(node));
      if (!text || text.length < 2 || seen.has(text)) continue;
      seen.add(text);
      const rawId = normalizeText(node.getAttribute('id') || '').replace(/^comment-/, '');
      const parentWrapper = node.closest('.parent-comment');
      const parentItem = parentWrapper && parentWrapper.querySelector(':scope > .comment-item');
      const parentCommentId = parentItem && parentItem !== node
        ? normalizeText(parentItem.getAttribute('id') || '').replace(/^comment-/, '')
        : '';
      const meta = pickCommentMeta(node);
      const authorLink = node.querySelector('.author a[href*="/user/profile"], a[href*="/user/profile"]');
      const avatarImg = node.querySelector('.avatar img, [class*="avatar"] img');
      comments.push({
        id: rawId || undefined,
        platformCommentId: rawId || undefined,
        parentCommentId: parentCommentId || undefined,
        rootCommentId: parentCommentId || rawId || undefined,
        level: parentCommentId ? 1 : 0,
        author: {
          nickname: pickCommentAuthor(node),
          userId: normalizeText(authorLink ? (authorLink.getAttribute('data-user-id') || '') : ''),
          profileUrl: authorLink ? (authorLink.href || '') : '',
          avatarUrl: avatarImg ? (avatarImg.src || avatarImg.getAttribute('data-src') || '') : '',
        },
        content: text,
        text,
        likes: meta.likes,
        replies: meta.replies,
        createdAt: meta.createdAt,
        location: meta.location,
      });
      if (comments.length >= 200) break;
    }
    return { success: true, noteId: getCurrentNoteId(), comments, diagnostics };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    void (async () => {
      try {
        if (!message || typeof message.type !== 'string') { sendResponse({ success: false, error: 'bad message' }); return; }
        if (message.type === 'xhs:extract-note') { sendResponse({ success: true, note: await buildNotePayload() }); return; }
        if (message.type === 'xhs:debug-state') { sendResponse({ success: true, debug: await debugState() }); return; }
        if (message.type === 'xhs:collect-blogger') { sendResponse(await collectBlogger()); return; }
        if (message.type === 'xhs:collect-links') { sendResponse({ success: true, links: collectVisibleNoteLinks() }); return; }
        if (message.type === 'xhs:extract-comments') { sendResponse(await extractComments()); return; }
        sendResponse({ success: false, error: 'unknown message type: ' + message.type });
      } catch (e) {
        sendResponse({ success: false, error: String((e && e.message) || e) });
      }
    })();
    return true;
  });
})();


