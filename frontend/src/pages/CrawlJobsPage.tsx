import { useEffect, useState } from 'react';
import { Button, Form, Input, InputNumber, message, Modal, Select, Progress, Table, Tag, Typography, Tabs, Row, Col } from 'antd';
import { PlusOutlined, SearchOutlined, HistoryOutlined } from '@ant-design/icons';
import { NoteCardView, parseNote, type NoteCardData } from '../components/NoteCard';
import NoteDetail from '../components/NoteDetail';

const { Title } = Typography;

const SEARCH_HISTORY_KEY = 'aistro_xhs_history';
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

const JOB_TYPES: Record<string,string> = { search:'搜索笔记', note_detail:'笔记详情', comment:'获取评论' };
const JOB_COLORS: Record<string,string> = { search:'blue', note_detail:'green', comment:'orange' };
const sortOpts = [{value:0,label:'综合'},{value:1,label:'最新'},{value:2,label:'最热'},{value:3,label:'最多评论'},{value:4,label:'最多收藏'}];
const typeOpts = [{value:0,label:'全部'},{value:1,label:'视频'},{value:2,label:'图文'}];
const timeOpts = [{value:0,label:'不限'},{value:1,label:'一天内'},{value:2,label:'一周内'},{value:3,label:'半年内'}];

const saveNotesToHistory = (items: NoteCardData[]) => {
    const saved = JSON.parse(localStorage.getItem('aistro_browsed') || '[]');
    const merged = [...items, ...saved].filter((v:any, i:number, a:any[]) => a.findIndex((x:any) => x.platform_note_id === v.platform_note_id) === i).slice(0, 200);
    localStorage.setItem('aistro_browsed', JSON.stringify(merged));
  };

export default function CrawlJobsPage() {
  interface CrawlTask { id:string; type:string; params:any; status:string; result:any; created_at:string; }
const [tasks, setTasks] = useState<CrawlTask[]>([]);
  
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
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

  const fetchTasks = async () => {
    try { const res = await (await import('../services/api')).default.get('/crawl-jobs'); setTasks(res.data.running || []); }
    catch {} // silent poll
  };
  useEffect(() => { fetchTasks(); const t = setInterval(fetchTasks,3000); return () => clearInterval(t); }, []);

  const handleCreate = async () => {
    const v = await form.validateFields();
    try {
      const api = (await import('../services/api')).default;
      await api.post('/crawl-jobs', { job_type: v.job_type, params: { query: v.query, limit: v.limit||20, note_url: v.note_url } });
      message.success('任务已启动');
      setModalOpen(false); form.resetFields(); fetchTasks();
    } catch { message.error('启动失败'); }
  };

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
      if (res.data.items) { setSelectedNotes(res.data.items); setActiveTab('results');
      saveNotesToHistory(res.data.items); }
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

  const showNoteResults = (task: any) => {
    if (task.result?.data && Array.isArray(task.result.data)) {
      setSelectedNotes(task.result.data.map((d:any) => parseNote(d))); setActiveTab('results');
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
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <Title level={3} style={{ margin:0 }}>爬虫管理</Title>
        <Button type='primary' icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建任务</Button>
      </div>
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
        { key:'results', label: '查看结果 ' + (selectedNotes ? selectedNotes.length + ' 条' : ''), children: selectedNotes ? (
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
                const parsed = saved.map((d:any) => parseNote(d));
                setSelectedNotes(parsed);
                message.success('已加载 ' + parsed.length + ' 条历史');
              }}>{'历史记录'}</Button>
            </div>
            <Row gutter={[16,16]}>{selectedNotes.map((n,i) => <Col key={i} xs={24} sm={12} md={8} lg={6}><div onClick={() => setDetailNote(n)}><NoteCardView note={n} /></div></Col>)}</Row>
          </>
        ) : <div style={{ padding:48, textAlign:'center', color:'#999' }}>{'选择一个已完成的任务查看结果'}</div>
        },
      ]} />
      <Modal title='新建爬虫任务' open={modalOpen} onOk={handleCreate} onCancel={() => setModalOpen(false)} okText='启动' cancelText='取消'>
        <Form form={form} layout='vertical' initialValues={{ job_type:'search', limit:20 }}>
          <Form.Item label='任务类型' name='job_type'><Select><Select.Option value='search'>搜索笔记</Select.Option><Select.Option value='note_detail'>笔记详情</Select.Option><Select.Option value='comment'>获取评论</Select.Option></Select></Form.Item>
          <Form.Item label='搜索关键词' name='query'><Input placeholder='如：重庆火锅' /></Form.Item>
          <Form.Item label='笔记 URL' name='note_url'><Input placeholder='https://...' /></Form.Item>
          <Form.Item label='数量限制' name='limit'><InputNumber min={1} max={100} style={{ width:'100%' }} /></Form.Item>
        </Form>
      </Modal>
      <NoteDetail open={!!detailNote} note={detailNote} onClose={() => setDetailNote(null)} />
    </div>
  );
}
