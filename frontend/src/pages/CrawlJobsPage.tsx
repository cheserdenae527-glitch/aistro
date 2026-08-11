import { useEffect, useState } from 'react';
import { Button, Input, InputNumber, message, Select, Progress, Table, Tag, Typography, Tabs, Row, Col, Space, Avatar } from 'antd';
import { SearchOutlined, HistoryOutlined, UserOutlined, EyeOutlined, BarChartOutlined, DatabaseOutlined } from '@ant-design/icons';
import { NoteCardView, parseNote, type NoteCardData } from '../components/NoteCard';
import NoteDetail from '../components/NoteDetail';
import SubscriptionsPage from './SubscriptionsPage';
import KnowledgeBasePanel from '../components/KnowledgeBasePanel';
import CrawlerPoolPanel from '../components/CrawlerPoolPanel';
import UserAnalysisPanel from '../components/UserAnalysisPanel';
import SubscribeButton from '../components/SubscribeButton';

const { Title, Text } = Typography;

const SEARCH_HISTORY_KEY = 'aistro_xhs_history';
const USER_SEARCH_HISTORY_KEY = 'aistro_xhs_user_history';
const MAX_HISTORY = 10;

function loadHistory(): string[] {
  try { return JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) || '[]'); }
  catch { return []; }
}

function saveHistory(query: string) {
  const h = loadHistory().filter(x => x !== query);
  h.unshift(query);
  localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(h.slice(0, MAX_HISTORY)));
}

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

const JOB_TYPES: Record<string,string> = { search:'搜索笔记', note_detail:'笔记详情', comment:'获取评论' };
const JOB_COLORS: Record<string,string> = { search:'blue', note_detail:'green', comment:'orange' };
const sortOpts = [{value:0,label:'综合'},{value:1,label:'最新'},{value:2,label:'最热'},{value:3,label:'最多评论'},{value:4,label:'最多收藏'}];
const typeOpts = [{value:0,label:'全部'},{value:1,label:'视频'},{value:2,label:'图文'}];
const timeOpts = [{value:0,label:'不限'},{value:1,label:'一天内'},{value:2,label:'一周内'},{value:3,label:'半年内'}];

interface XhsUser {
  user_id: string;
  nickname: string;
  avatar: string;
  fans: number;
  notes: number;
  desc: string;
}

export default function CrawlJobsPage() {
  interface CrawlTask { id:string; type:string; params:any; status:string; result:any; created_at:string; }
  const [tasks, setTasks] = useState<CrawlTask[]>([]);
  const [activeTab, setActiveTab] = useState('tasks');
  const [selectedNotes, setSelectedNotes] = useState<NoteCardData[] | null>(null);
  const [browsingQuery, setBrowsingQuery] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchProgress, setSearchProgress] = useState(0);
  const [detailNote, setDetailNote] = useState<NoteCardData | null>(null);
  const [sortType, setSortType] = useState(0);
  const [noteType, setNoteType] = useState(0);
  const [timeRange, setTimeRange] = useState(0);
  const [crawlLimit, setCrawlLimit] = useState(20);
  const [searchHistory, setSearchHistory] = useState<string[]>(loadHistory());
  const [showHistory, setShowHistory] = useState(false);
  const [userSearchHistory, setUserSearchHistory] = useState<string[]>(loadUserHistory());
  const [showUserHistory, setShowUserHistory] = useState(false);

  // 搜索博主
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
  const [analysisData, setAnalysisData] = useState<any | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [analysisStatus, setAnalysisStatus] = useState('');

  const fetchTasks = async () => {
    try { const res = await (await import('../services/api')).default.get('/crawl-jobs'); setTasks(res.data.running || []); }
    catch { /* silent poll */ }
  };
  useEffect(() => { fetchTasks(); const t = setInterval(fetchTasks,3000); return () => clearInterval(t); }, []);

  const handleQuickSearch = async (query?: string) => {
    const q = query || browsingQuery;
    if (!q.trim()) return;
    saveHistory(q);
    setSearchHistory(loadHistory());
    setSearchLoading(true); setSearchProgress(0);
    const timer = setInterval(() => setSearchProgress(p => Math.min(p + 5, 90)), 500);
    try {
      const api = (await import('../services/api')).default;
      const res = await api.post('/notes/search', { query: q, limit: crawlLimit, sort: sortType, note_type: noteType, time_range: timeRange });
      if (res.data.items) { setSelectedNotes(res.data.items); setActiveTab('results'); }
      setSearchProgress(100);
      message.success('搜索完成');
      setTimeout(() => setSearchProgress(0), 1500);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || '未知错误';
      message.error('搜索失败: ' + detail, 5);
      setSearchProgress(0);
    }
    finally { clearInterval(timer); setSearchLoading(false); setShowHistory(false); }
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

  const handleAnalyzeUser = async (u: XhsUser) => {
    setAnalysisUser(u); setAnalysisData(null); setAnalysisLoading(true); setAnalysisProgress(0);
    setAnalysisStatus('正在创建分析任务...'); setActiveTab('analysis');
    try {
      const api = (await import('../services/api')).default;
      const res = await api.post(`/notes/users/${u.user_id}/analysis-tasks`, { nickname: u.nickname, fans: u.fans }, { timeout: 60000 });
      if (res.data.passed_prescreen === false) {
        setAnalysisStatus('未通过粗筛：' + (res.data.reason || ''));
        setAnalysisLoading(false);
        message.warning('未通过粗筛：' + (res.data.reason || ''), 6);
        return;
      }
      const taskId = res.data.id;
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
              setAnalysisStatus(t.status === 'partial' ? '分析完成（部分数据）' : '分析完成');
              setAnalysisProgress(100);
              message.success(t.status === 'partial' ? '分析完成（部分数据）' : '分析完成');
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

  const showNoteResults = (task: any) => {
    if (task.result?.data && Array.isArray(task.result.data)) {
      setSelectedNotes(task.result.data.map((d:any) => parseNote(d)));
      setActiveTab('results');
    }
  };

  const taskColumns = [
    { title:'ID', dataIndex:'id', key:'id', render:(v:string) => v.slice(0,8)+'...' },
    { title:'类型', dataIndex:'type', key:'type', render:(t:string) => <Tag color={JOB_COLORS[t]}>{JOB_TYPES[t]||t}</Tag> },
    { title:'关键词', key:'params', render:(_:any, r:any) => r.params?.query||'-' },
    { title:'状态', dataIndex:'status', key:'status', render:(s:string) => <Tag color={s==='success'?'success':s==='running'?'processing':'error'}>{s}</Tag> },
    { title:'结果', key:'result', render:(_:any, r:any) => r.result?.stats?.count!=null ? r.result.stats.count+' 条' : r.result?.error?'失败':'-' },
    { title:'时间', dataIndex:'created_at', key:'created_at', render:(v:string) => v?v.slice(11,19):'-' },
    { title:'操作', key:'actions', render:(_:any, r:any) => r.result?.data ? <Button type='link' size='small' onClick={() => showNoteResults(r)}>查看笔记</Button> : <span>-</span> },
  ];

  return (
    <div>
      <Title level={3} style={{ margin:0, marginBottom:16 }}>爬虫管理</Title>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        { key:'tasks', label:'任务列表', children: <>
          <div style={{ marginBottom:12, display:'flex', gap:8, flexWrap:'wrap', alignItems:'center' }}>
            <div style={{ position:'relative' }}>
              <Input.Search
                placeholder='搜索小红书...'
                value={browsingQuery}
                onChange={e => { setBrowsingQuery(e.target.value); setShowHistory(true); }}
                onFocus={() => setShowHistory(searchHistory.length > 0)}
                onBlur={() => setTimeout(() => setShowHistory(false), 200)}
                onSearch={handleQuickSearch}
                enterButton={<><SearchOutlined /> 搜索</>}
                loading={searchLoading}
                style={{ width:260 }}
              />
              {showHistory && searchHistory.length > 0 && (
                <div style={{ position:'absolute', top:'100%', left:0, right:0, zIndex:10, background:'#fff', border:'1px solid #d9d9d9', borderRadius:4, marginTop:2, maxHeight:200, overflow:'auto', boxShadow:'0 2px 8px rgba(0,0,0,0.1)' }}>
                  <div style={{ padding:'4px 8px', fontSize:12, color:'#999', display:'flex', justifyContent:'space-between' }}>
                    <span><HistoryOutlined /> 搜索历史</span>
                    <span style={{ cursor:'pointer' }} onClick={() => { localStorage.removeItem(SEARCH_HISTORY_KEY); setSearchHistory([]); }}>清除</span>
                  </div>
                  {searchHistory.map((h,i) => (
                    <div key={i} style={{ padding:'6px 12px', cursor:'pointer', fontSize:13 }} onClick={() => { setBrowsingQuery(h); handleQuickSearch(h); }}
                      onMouseEnter={e => (e.target as HTMLElement).style.background='#f5f5f5'}
                      onMouseLeave={e => (e.target as HTMLElement).style.background='transparent'}
                    >{h}</div>
                  ))}
                </div>
              )}
            </div>
            <Select value={sortType} onChange={setSortType} style={{ width:100 }} options={sortOpts} />
            <Select value={noteType} onChange={setNoteType} style={{ width:80 }} options={typeOpts} />
            <Select value={timeRange} onChange={setTimeRange} style={{ width:90 }} options={timeOpts} />
            <InputNumber value={crawlLimit} onChange={v => setCrawlLimit(v || 20)} min={1} max={100} style={{ width:90 }} addonBefore='条' />
          </div>
          {searchProgress > 0 && searchProgress < 100 && <Progress percent={searchProgress} size='small' style={{ marginBottom:12 }} />}
          <Table dataSource={tasks} columns={taskColumns} rowKey='id' pagination={false} />
        </> },
        { key:'search-users', label:'搜索博主', children: <>
          <div style={{ marginBottom:12, display:'flex', gap:8, alignItems:'center', flexWrap:'wrap' }}>
            <div style={{ position:'relative' }}>
              <Input.Search
                placeholder='输入博主昵称，如：泡芙味的女孩子'
                value={userQuery}
                onChange={e => { setUserQuery(e.target.value); setShowUserHistory(true); }}
                onFocus={() => setShowUserHistory(userSearchHistory.length > 0)}
                onBlur={() => setTimeout(() => setShowUserHistory(false), 200)}
                onSearch={handleSearchUsers}
                enterButton='搜索博主'
                loading={usersLoading}
                style={{ width:320 }}
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
          </div>
          {users.length === 0 ? (
            <div style={{ padding:48, textAlign:'center', color:'#999' }}>搜索博主昵称查看账号信息</div>
          ) : (
            <Row gutter={[12,12]}>
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
                    </Space>
                  </div>
                </Col>
              ))}
            </Row>
          )}
        </> },
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
        { key:'results', label: '浏览结果 ' + (selectedNotes ? selectedNotes.length + ' 条' : ''), children: selectedNotes ? (
          <>
            <div style={{ marginBottom:12, display:'flex', gap:8, alignItems:'center' }}>
              <span style={{ fontSize:13, color:'#666' }}>筛选排序：</span>
              <Select value={null} onChange={(v:number) => {
                if (!selectedNotes) return;
                const sorted = [...selectedNotes];
                if (v === 1) sorted.sort((a,b) => b.stats.liked - a.stats.liked);
                else if (v === 2) sorted.sort((a,b) => b.stats.comments - a.stats.comments);
                else if (v === 3) sorted.sort((a,b) => b.stats.collected - a.stats.collected);
                setSelectedNotes(sorted);
              }} style={{ width:130 }} options={[{value:0,label:'默认排序'},{value:1,label:'最多点赞'},{value:2,label:'最多评论'},{value:3,label:'最多收藏'}]} placeholder='默认排序' allowClear />
              <Button size='small' onClick={() => {
                const saved = JSON.parse(localStorage.getItem('aistro_browsed') || '[]');
                const merged = [...saved, ...(selectedNotes||[])].filter((v:any,i:number,a:any[]) => a.findIndex((x:any) => x.platform_note_id === v.platform_note_id) === i).slice(0, 100);
                localStorage.setItem('aistro_browsed', JSON.stringify(merged));
                message.success('已保存 ' + selectedNotes!.length + ' 条到浏览历史');
              }}>{'保存到历史'}</Button>
              <Button size='small' onClick={() => {
                const saved = JSON.parse(localStorage.getItem('aistro_browsed') || '[]');
                if (saved.length === 0) { message.info('暂无浏览历史'); return; }
                setSelectedNotes(saved.map((d:any) => d));
                message.success('已加载 ' + saved.length + ' 条历史');
              }}>{'历史记录'}</Button>
              <Button size='small' icon={<DatabaseOutlined />} onClick={() => saveNotesToKnowledge(selectedNotes || [], 'search')}>加入知识库</Button>
            </div>
            <Row gutter={[16,16]}>{selectedNotes.map((n,i) => <Col key={i} xs={24} sm={12} md={8} lg={6}><div onClick={() => setDetailNote(n)} style={{cursor:'pointer'}}><NoteCardView note={n} /></div></Col>)}</Row>
          </>
        ) : <div style={{ padding:48, textAlign:'center', color:'#999' }}>选择一个已完成的任务查看结果</div>
        },
        { key:'analysis', label: analysisUser ? '博主分析 · ' + analysisUser.nickname : '博主分析', children: analysisLoading ? (
          <div style={{ padding: 24, textAlign: 'center' }}>
            <Progress percent={analysisProgress} status="active" style={{ maxWidth: 480, margin: '0 auto' }} />
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>{analysisStatus || '正在分析...'}</Text>
          </div>
        ) : <UserAnalysisPanel user={analysisUser} data={analysisData} onOpenNote={(n) => setDetailNote(n)} /> },
        { key:'subscriptions', label:'博主订阅', children: <SubscriptionsPage /> },
        { key:'knowledge', label:'知识库', children: <KnowledgeBasePanel /> },
        { key:'pool', label:'采集配置', children: <CrawlerPoolPanel /> },
      ]} />
      <NoteDetail open={!!detailNote} note={detailNote} onClose={() => setDetailNote(null)} />
    </div>
  );
}
