(() => {
  const $ = (id) => document.getElementById(id);
  const statusEl = $('status');
  const resultEl = $('result');

  function setStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.className = 'status ' + (kind || '');
  }
  function setResult(text) {
    resultEl.textContent = text;
    resultEl.className = 'result';
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === 'bridge:progress') {
      const total = msg.total ? ` ${msg.current}/${msg.total}` : '';
      setResult((msg.label || '采集进度') + total + '...');
    }
  });

  async function send(type, extra) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ type, ...(extra || {}) }, (res) => resolve(res || { success: false, error: 'no response' }));
    });
  }

  async function refreshStatus() {
    const s = await send('bridge:get-status');
    if (!s.success) { setStatus(s.error || '状态获取失败', 'error'); return; }
    $('endpoint').value = s.endpoint;
    $('extVersion').textContent = 'v' + (s.extVersion || '?');
    if (!s.onXhs) {
      setStatus('请打开小红书笔记页', 'warn');
    } else if (!s.endpointOk) {
      setStatus('已连接页面 · 后端未启动', 'warn');
    } else {
      setStatus('已连接页面 · 后端 OK', 'ok');
    }
  }

  $('saveEndpoint').addEventListener('click', async () => {
    const endpoint = $('endpoint').value.trim();
    const res = await send('bridge:set-endpoint', { endpoint });
    if (res.success) setStatus('端点已保存', 'ok');
    else setStatus(res.error || '保存失败', 'error');
    refreshStatus();
  });

  $('collectBlogger').addEventListener('click', async () => {
    const bloggerUrl = $('bloggerUrl').value.trim();
    setResult('采集中…（博主主页滚动 + 批量入库）');
    const res = await send('bridge:collect-blogger', { bloggerUrl });
    if (!res.success) { setResult('失败：' + (res.error || '')); return; }
    const r = res.result || {};
    const kbText = r.knowledge_synced === undefined ? '（后端未返回同步状态）' : (r.knowledge_synced ? '是' : '否');
    setResult('博主 ' + res.userId + '\n笔记 ' + res.total + ' 条（含互动指标 ' + res.withStats + ' 条）\n知识库同步：' + kbText + '\n' + JSON.stringify(r, null, 2));
  });

  $('saveNote').addEventListener('click', async () => {
    setResult('采集中…');
    const res = await send('bridge:save-current-note');
    if (!res.success) { setResult('失败：' + (res.error || '')); return; }
    const r = res.result || {};
    const kbText = r.knowledge_synced === undefined ? '（后端未返回同步状态）' : (r.knowledge_synced ? '是' : '否');
    const feedLine = res.feed && res.feed.used ? ('feed ' + (res.feed.ok ? 'OK' : '未取到') + (res.feed.reason ? ' · ' + res.feed.reason : '')) : '';
    setResult('已保存 ' + res.noteId + '\n知识库同步：' + kbText + '\n' + JSON.stringify(r, null, 2) + (feedLine ? ('\n' + feedLine) : ''));
  });

  $('saveComments').addEventListener('click', async () => {
    setResult('采集中…');
    const res = await send('bridge:save-comments');
    if (!res.success) { setResult('失败：' + (res.error || '')); return; }
    setResult('评论 ' + res.count + ' 条\n' + JSON.stringify(res.result || {}, null, 2));
  });

  $('debug').addEventListener('click', async () => {
    const res = await send('bridge:debug-state');
    if (!res.success) { setResult('失败：' + (res.error || '')); return; }
    setResult(JSON.stringify(res.debug, null, 2));
  });

  $('collectLinks').addEventListener('click', async () => {
    const res = await send('bridge:collect-links');
    if (!res.success) { setResult('失败：' + (res.error || '')); return; }
    setResult('本页链接 ' + res.links.length + ' 条（批量采集将在阶段 4 接入）');
  });

  refreshStatus();
})();
