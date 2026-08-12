import { useEffect, useState } from 'react';
import { Button, Drawer, Input, message, Progress, Typography, Tabs, Row, Col, Space, Avatar, Switch } from 'antd';
import { SearchOutlined, HistoryOutlined, UserOutlined, EyeOutlined, BarChartOutlined, DatabaseOutlined, PlusOutlined, SettingOutlined } from '@ant-design/icons';
import { NoteCardView, type NoteCardData } from '../components/NoteCard';
import NoteDetail from '../components/NoteDetail';
import SubscriptionsPage from './SubscriptionsPage';
import CrawlerPoolPanel from '../components/CrawlerPoolPanel';
import UserAnalysisPanel from '../components/UserAnalysisPanel';
import BatchAnalysisPanel, { type BatchQueueItem } from '../components/BatchAnalysisPanel';
import SubscribeButton from '../components/SubscribeButton';
import { listAnalysisTasks, ScreeningRow, BloggerAnalysisResult, AnalysisTaskPayload } from '../services/analysis';

const { Title, Text } = Typography;

const USER_SEARCH_HISTORY_KEY = 'aistro_xhs_user_history';
const MAX_HISTORY = 10;

function loadUserHistory(): string[] {
  try { return JSON.parse(localStorage.getItem(USER_SEARCH_HISTORY_KEY) || '[]'); }
  catch { return []; }
}

function saveUserHistory(query: string) {
  const h = loadUserHistory().filter(x => x !== query);
  h.unshift(query);
  localStorage.setItem(USER_SEARCH_HISTORY_KEY, JSON.stringify(h.slice(0, MAX_HISTORY)));
}

const proxyImg = (url: string, size = 0) => '/api/v1/images/proxy?url=' + encodeURIComponent(url.replace(/^http:/, 'https:')) + '&size=' + size;

interface XhsUser {
  user_id: string;
  nickname: string;
  avatar: string;
  fans: number;
  notes: number;
  desc: string;
}

export default function CrawlJobsPage() {
  const [activeTab, setActiveTab] = useState('user-notes');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [detailNote, setDetailNote] = useState<NoteCardData | null>(null);
  const [userSearchHistory, setUserSearchHistory] = useState<string[]>(loadUserHistory());
  const [showUserHistory, setShowUserHistory] = useState(false);

  // 搜索博主（置顶搜索框）
  const [userQuery, setUserQuery] = useState('');
  const [users, setUsers] = useState<XhsUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);

  // 博主作品
  const [viewingUser, setViewingUser] = useState<XhsUser | null>(null);
  const [userNotes, setUserNotes] = useState<NoteCardData[]>([]);
  const [userNotesLoading, setUserNotesLoading] = useState(false);
  const [viewNotesProgress, setViewNotesProgress] = useState(0);
  const [viewNotesStatus, setViewNotesStatus] = useState('');

  // 博主分析
  const [analysisUser, setAnalysisUser] = useState<XhsUser | null>(null);
  const [analysisTaskId, setAnalysisTaskId] = useState<string | null>(null);
  const [analysisData, setAnalysisData] = useState<any | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [analysisStatus, setAnalysisStatus] = useState('');
  const [withComments, setWithComments] = useState(false);

  // 批量筛选
  const [screeningRows, setScreeningRows] = useState<ScreeningRow[]>([]);
  const [screeningLoading, setScreeningLoading] = useState(false);

  // 批量分析队列
  const [batchQueue, setBatchQueue] = useState<BatchQueueItem[]>([]);

  const loadScreening = async (silent = false) => {
    if (!silent) setScreeningLoading(true);
    try {
      const res = await listAnalysisTasks({ status: 'success', limit: 200 });
      const items = res.items || [];
      // 去重：每个 xhs_user_id 保留最新 finished_at 的一条
      const latest = new Map<string, AnalysisTaskPayload>();
      for (const t of items) {
        const prev = latest.get(t.xhs_user_id);
        if (!prev || (t.finished_at || '') > (prev.finished_at || '')) latest.set(t.xhs_user_id, t);
      }
      const rows: ScreeningRow[] = Array.from(latest.values()).map((t) => {
        const r = (t.result || {}) as BloggerAnalysisResult;
        return {
          user_id: t.xhs_user_id,
          nickname: t.nickname || '',
          fans: t.follower_count || 0,
          overall_score: r.overall?.score ?? null,
          score_suppressed: !!(r.overall_score_suppressed || r.overall?.score_suppressed),
          level: r.overall?.level || '-',
          recommendation: r.decision?.recommendation || 'insufficient_data',
          stage_label: r.stage?.label || '-',
          stage_confidence: r.stage?.confidence || 'low',
          red_flags: (r.decision?.red_flags || []).map((f) => f.detail),
          collect_rate: r.dimensions?.seeding_depth?.detail?.collect_rate_percent ?? null,
          food_ratio: r.dimensions?.verticality?.detail?.food_ratio ?? null,
          confidence: r.confidence || 'low',
        };
      });
      setScreeningRows(rows);
    } catch (e: unknown) {
      message.error('批量筛选数据加载失败：' + ((e as { message?: unknown })?.message || e));
    } finally {
      if (!silent) setScreeningLoading(false);
    }
  };
  useEffect(() => { loadScreening(); }, []);

  const addToBatchQueue = (u: XhsUser) => {
    const result: { outcome: 'added' | 'duplicate' | 'full' | null } = { outcome: null };
    // 去重 + 上限在 updater 内完成，提示由 updater 结果推导，避免快速双击展示过期信息
    setBatchQueue((q) => {
      if (q.some((x) => x.user_id === u.user_id)) { result.outcome = 'duplicate'; return q; }
      if (q.length >= 50) { result.outcome = 'full'; return q; }
      result.outcome = 'added';
      return [...q, { user_id: u.user_id, nickname: u.nickname, fans: u.fans }];
    });
    if (result.outcome === 'full') message.warning('批量分析单次最多 50 个博主');
    else if (result.outcome === 'duplicate') message.info('该博主已在批量分析队列中');
    else if (result.outcome === 'added') message.success(`已加入批量分析队列：${u.nickname}`);
  };

  const addParsedToBatchQueue = (items: BatchQueueItem[]) => {
    if (items.length === 0) return;
    const result: { outcome: { kind: 'added'; count: number } | { kind: 'duplicate' } | { kind: 'full' } | null } = { outcome: null };
    // 去重 + 上限在 updater 内完成，数量提示由 updater 结果推导，避免快速连续点击展示过期数量
    setBatchQueue((q) => {
      const seen = new Set(q.map((x) => x.user_id));
      const addable = items.filter((x) => !seen.has(x.user_id)).slice(0, Math.max(0, 50 - q.length));
      if (addable.length === 0) {
        result.outcome = q.length >= 50 ? { kind: 'full' } : { kind: 'duplicate' };
        return q;
      }
      result.outcome = { kind: 'added', count: addable.length };
      return [...q, ...addable];
    });
    if (result.outcome?.kind === 'full') message.warning('批量分析单次最多 50 个博主');
    else if (result.outcome?.kind === 'duplicate') message.info('这些博主已在批量分析队列中');
    else if (result.outcome?.kind === 'added') message.success(`已加入 ${result.outcome.count} 个博主到批量分析队列`);
  };

  const removeFromBatchQueue = (userId: string) => {
    setBatchQueue((q) => q.filter((x) => x.user_id !== userId));
  };

  const handleSearchUsers = async (q?: string) => {
    const query = (q !== undefined ? q : userQuery).trim();
    if (!query) return;
    if (q !== undefined) setUserQuery(q);
    saveUserHistory(query);
    setUserSearchHistory(loadUserHistory());
    setUsersLoading(true);
    try {
      const api = (await import('../services/api')).default;
      const res = await api.post('/notes/search-users', { query, limit: 10 });
      setUsers(res.data.items || []);
      if (!res.data.items?.length) message.info('未找到相关博主');
    } catch (err: any) {
      message.error('搜索失败: ' + (err?.response?.data?.detail || err?.message || ''), 5);
    } finally { setUsersLoading(false); setShowUserHistory(false); }
  };

  const handleViewUserNotes = async (u: XhsUser) => {
    setViewingUser(u); setUserNotesLoading(true); setViewNotesProgress(0); setViewNotesStatus('正在获取并补齐完整数据...'); setActiveTab('user-notes');
    const timer = setInterval(() => setViewNotesProgress(p => Math.min(p + 5, 90)), 600);
    try {
      const api = (await import('../services/api')).default;
      const res = await api.get(`/notes/users/${u.user_id}/notes`, { params: { limit: 50, nickname: u.nickname, enrich_limit: 50 }, timeout: 300000 });
      setUserNotes(res.data.items || []);
      setViewNotesProgress(100); setViewNotesStatus('抓取完成');
      if (res.data.source === 'search_fallback') message.info('作品接口暂不可用，已按昵称搜索展示', 3);
      if (!res.data.items?.length) message.info('未找到该博主作品');
    } catch (err: any) {
      message.error('查看博主作品失败: ' + (err?.response?.data?.detail || err?.message || ''), 5);
      setViewNotesProgress(0);
    } finally {
      clearInterval(timer); setUserNotesLoading(false);
      setTimeout(() => setViewNotesProgress(0), 1500);
    }
  };

  const handleAnalyzeUser = async (u: XhsUser, refresh = false) => {
    setAnalysisUser(u); setAnalysisTaskId(null); setAnalysisData(null); setAnalysisLoading(true); setAnalysisProgress(0);
    setAnalysisStatus('正在创建分析任务...'); setActiveTab('analysis');
    try {
      const api = (await import('../services/api')).default;
      const res = await api.post(`/notes/users/${u.user_id}/analysis-tasks${refresh ? '?refresh=1' : ''}`, { nickname: u.nickname, fans: u.fans, with_comments: withComments }, { timeout: 60000 });
      if (res.data.passed_prescreen === false) {
        setAnalysisStatus('未通过粗筛：' + (res.data.reason || ''));
        setAnalysisLoading(false);
        message.warning('未通过粗筛：' + (res.data.reason || ''), 6);
        return;
      }
      // 命中缓存：直接展示最近结果，不重复爬取
      if (res.data.from_cache) {
        setAnalysisTaskId(res.data.id);
        setAnalysisData(res.data.result);
        setAnalysisStatus('已复用最近分析结果（' + (res.data.cached_finished_at ? res.data.cached_finished_at.slice(0, 16).replace('T', ' ') : '') + '）');
        setAnalysisProgress(100);
        setAnalysisLoading(false);
        message.success('已复用最近分析结果，未重复爬取');
        return;
      }
      const taskId = res.data.id;
      setAnalysisTaskId(taskId);
      const poll = setInterval(async () => {
        try {
          const r = await api.get(`/notes/users/${u.user_id}/analysis-tasks/${taskId}`);
          const t = r.data;
          const denom = t.target_notes || t.total_notes;
          const pct = denom ? Math.round((t.fetched_notes || 0) / denom * 90) : 5;
          setAnalysisProgress(pct);
          setAnalysisStatus(t.target_notes && t.target_notes < (t.total_notes || 0)
            ? `正在抓取真实详情（抽样 ${t.fetched_notes || 0}/${t.target_notes}，共 ${t.total_notes} 篇）...`
            : `正在抓取真实详情 ${t.fetched_notes || 0}/${t.total_notes || '?'}...`);
          if (['success', 'partial', 'failed', 'cancelled'].includes(t.status)) {
            clearInterval(poll);
            if (t.status === 'success' || t.status === 'partial') {
              setAnalysisData(t.result);
              const commentsOn = withComments && t.result?.dimensions?.seeding_depth?.detail?.comment_signal_low_conf === false;
              const doneMsg = commentsOn ? '分析完成（已启用评论意向分析）' : (t.status === 'partial' ? '分析完成（部分数据）' : '分析完成');
              setAnalysisStatus(doneMsg);
              setAnalysisProgress(100);
              message.success(doneMsg);
            } else {
              setAnalysisStatus('分析失败');
              message.error('分析失败：' + (t.error || t.status), 6);
            }
            setAnalysisLoading(false);
            setTimeout(() => setAnalysisProgress(0), 1500);
          }
        } catch {
          clearInterval(poll);
          setAnalysisLoading(false);
          message.error('查询分析任务失败', 5);
        }
      }, 3000);
    } catch (err: any) {
      setAnalysisLoading(false);
      message.error('创建分析任务失败：' + (err?.response?.data?.detail || err?.message || ''), 6);
    }
  };

  const saveNotesToKnowledge = async (notes: any[], source: string) => {
    if (!notes?.length) { message.info('没有可加入的笔记'); return; }
    try {
      const api = (await import('../services/api')).default;
      const res = await api.post('/knowledge/notes', { notes, source });
      message.success(`已加入知识库 ${res.data?.synced || 0} 条`);
    } catch (err: any) {
      message.error('加入知识库失败：' + (err?.response?.data?.detail || err?.message || ''), 5);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>达人寻觅</Title>
        <div style={{ flex: 1 }} />
        <Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>采集设置</Button>
      </div>

      {/* 置顶搜索框：搜索博主（任务列表与搜索博主合并于此） */}
      <div style={{ position: 'relative', marginBottom: 12, maxWidth: 560 }}>
        <Input.Search
          placeholder='输入博主昵称搜索达人，如：泡芙味的女孩子'
          value={userQuery}
          onChange={e => { setUserQuery(e.target.value); setShowUserHistory(true); }}
          onFocus={() => setShowUserHistory(userSearchHistory.length > 0)}
          onBlur={() => setTimeout(() => setShowUserHistory(false), 200)}
          onSearch={handleSearchUsers}
          enterButton={<><SearchOutlined /> 搜索</>}
          loading={usersLoading}
          size="large"
        />
        {showUserHistory && userSearchHistory.length > 0 && (
          <div style={{ position:'absolute', top:'100%', left:0, right:0, zIndex:10, background:'#fff', border:'1px solid #d9d9d9', borderRadius:4, marginTop:2, maxHeight:200, overflow:'auto', boxShadow:'0 2px 8px rgba(0,0,0,0.1)' }}>
            <div style={{ padding:'4px 8px', fontSize:12, color:'#999', display:'flex', justifyContent:'space-between' }}>
              <span><HistoryOutlined /> 搜索历史</span>
              <span style={{ cursor:'pointer' }} onClick={() => { localStorage.removeItem(USER_SEARCH_HISTORY_KEY); setUserSearchHistory([]); }}>清除</span>
            </div>
            {userSearchHistory.map((h,i) => (
              <div key={i} style={{ padding:'6px 12px', cursor:'pointer', fontSize:13 }} onClick={() => handleSearchUsers(h)}
                onMouseEnter={e => (e.target as HTMLElement).style.background='#f5f5f5'}
                onMouseLeave={e => (e.target as HTMLElement).style.background='transparent'}
              >{h}</div>
            ))}
          </div>
        )}
      </div>

      {/* 博主搜索结果 */}
      {users.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#999', marginBottom: 12 }}>搜索博主昵称，开始达人寻觅</div>
      ) : (
        <Row gutter={[12,12]} style={{ marginBottom: 12 }}>
          {users.map((u, i) => (
            <Col key={i} xs={24} sm={12} md={8} lg={6}>
              <div style={{ border:'1px solid #f0f0f0', borderRadius:8, padding:16, background:'#fff' }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8 }}>
                  <Space>
                    {u.avatar ? <Avatar src={proxyImg(u.avatar, 80)} size={40} /> : <Avatar icon={<UserOutlined />} size={40} />}
                    <div>
                      <Text strong>{u.nickname}</Text>
                      <div><Text type='secondary' style={{ fontSize:12 }}>粉丝 {u.fans} · 笔记 {u.notes}</Text></div>
                    </div>
                  </Space>
                  <SubscribeButton user={{ xhs_user_id: u.user_id, nickname: u.nickname, avatar: u.avatar }} />
                </div>
                {u.desc && <div style={{ marginTop:8, fontSize:12, color:'#666', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{u.desc}</div>}
                <Space style={{ marginTop:10 }}>
                  <Button type='primary' size='small' icon={<EyeOutlined />} onClick={() => handleViewUserNotes(u)}>查看作品</Button>
                  <Button size='small' type='primary' ghost icon={<BarChartOutlined />} onClick={() => handleAnalyzeUser(u)}>分析</Button>
                  <Button size='small' icon={<PlusOutlined />} onClick={() => addToBatchQueue(u)}>加入批量分析</Button>
                </Space>
              </div>
            </Col>
          ))}
        </Row>
      )}

      {/* 其余功能 */}
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        { key:'user-notes', label: viewingUser ? viewingUser.nickname + ' 的作品' : '博主作品', children: userNotesLoading ? (
          <div style={{ padding: 24, textAlign: 'center' }}>
            <Progress percent={viewNotesProgress} status="active" style={{ maxWidth: 480, margin: '0 auto' }} />
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>{viewNotesStatus || '正在获取博主作品...'}</Text>
          </div>
        ) : userNotes.length > 0 ? (
          <>
            <div style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
              <Text type="secondary">共 {userNotes.length} 篇</Text>
              <Button size="small" type="primary" ghost icon={<DatabaseOutlined />} onClick={() => saveNotesToKnowledge(userNotes, 'user_notes')}>加入知识库</Button>
            </div>
            <Row gutter={[16,16]}>
              {userNotes.map((n,i) => <Col key={i} xs={24} sm={12} md={8} lg={6}><div onClick={() => setDetailNote(n)} style={{cursor:'pointer'}}><NoteCardView note={n} /></div></Col>)}
            </Row>
          </>
        ) : <div style={{ padding:48, textAlign:'center', color:'#999' }}>搜索博主后点击"查看作品"</div> },
        { key:'analysis', label: analysisUser ? '博主分析 · ' + analysisUser.nickname : '博主分析', children: (
          <Tabs size="small" items={[
            { key:'single', label:'单号分析', children: (
              <>
                <div style={{ padding: 12, textAlign: 'center' }}>
                  <Space>
                    <Switch checked={withComments} disabled={analysisLoading} onChange={setWithComments} checkedChildren="评论分析开" unCheckedChildren="评论分析关" />
                    <Text type="secondary">深度诊断可开启评论意向分析（抓取代表笔记评论，更准但更慢）</Text>
                  </Space>
                </div>
                {analysisLoading ? (
                  <div style={{ padding: 24, textAlign: 'center' }}>
                    <Progress percent={analysisProgress} status="active" style={{ maxWidth: 480, margin: '0 auto' }} />
                    <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>{analysisStatus || '正在分析...'}</Text>
                  </div>
                ) : <UserAnalysisPanel user={analysisUser} data={analysisData} onOpenNote={(n) => setDetailNote(n)} taskId={analysisTaskId} onReAnalyze={() => analysisUser && handleAnalyzeUser(analysisUser, true)} onAnalyzeUser={(u) => handleAnalyzeUser(u as XhsUser)} />}
              </>
            ) },
            { key:'batch', label:'批量分析', children: (
              <BatchAnalysisPanel
                queue={batchQueue}
                onRemoveFromQueue={removeFromBatchQueue}
                onAddFromQueue={addParsedToBatchQueue}
                screeningRows={screeningRows}
                screeningLoading={screeningLoading}
                onRefreshScreening={loadScreening}
                onPollRefreshScreening={() => loadScreening(true)}
                withComments={withComments}
              />
            ) },
          ]} />
        ) },
        { key:'subscriptions', label:'博主订阅', children: <SubscriptionsPage /> },
      ]} />

      <Drawer title="采集设置" width={760} open={settingsOpen} onClose={() => setSettingsOpen(false)}>
        <CrawlerPoolPanel />
      </Drawer>
      <NoteDetail open={!!detailNote} note={detailNote} onClose={() => setDetailNote(null)} />
    </div>
  );
}
