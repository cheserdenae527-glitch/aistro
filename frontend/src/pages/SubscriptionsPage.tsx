import { useEffect, useState } from 'react';
import { Button, Form, Input, message, Modal, Table, Typography, Popconfirm, Space, Row, Col, Spin, Tag } from 'antd';
import { DownloadOutlined, PlusOutlined, ReloadOutlined, BarChartOutlined } from '@ant-design/icons';
import { NoteCardView, type NoteCardData } from '../components/NoteCard';
import NoteDetail from '../components/NoteDetail';
import UserAnalysisPanel from '../components/UserAnalysisPanel';
import { subService, type Subscription } from '../services/subscriptions';
import { listAnalysisTasks, exportAnalysisReport, AnalysisTaskPayload } from '../services/analysis';
const { Title, Text } = Typography;

const REC_RANK: Record<string, number> = { priority: 0, ok: 1, caution: 2, not_recommended: 3, insufficient_data: 4 };
const REC_TAG: Record<string, { color: string; label: string }> = {
  priority: { color: 'green', label: '优先合作' },
  ok: { color: 'blue', label: '可合作' },
  caution: { color: 'orange', label: '谨慎' },
  not_recommended: { color: 'red', label: '不合作' },
  insufficient_data: { color: 'default', label: '数据不足' },
};

function rowRank(t: AnalysisTaskPayload): number {
  return REC_RANK[(t.result?.decision?.recommendation) || 'insufficient_data'] ?? 4;
}
function rowCost(t: AnalysisTaskPayload): number {
  return (t.result?.dimensions?.cost_effectiveness?.score) ?? -1;
}
function rowOverall(t: AnalysisTaskPayload): number {
  return t.result?.overall?.score ?? -1;
}

interface ViewingAnalysis {
  user: { user_id: string; nickname: string; fans: number };
  data: any;
  taskId: string | null;
  loading: boolean;
}

export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [notesModal, setNotesModal] = useState(false);
  const [viewingNotes, setViewingNotes] = useState([]);
  const [notesLoading, setNotesLoading] = useState(false);
  const [detailNote, setDetailNote] = useState<NoteCardData | null>(null);
  const [viewingNickname, setViewingNickname] = useState("");

  // 长期分析结果列表
  const [results, setResults] = useState<AnalysisTaskPayload[]>([]);
  const [resultsLoading, setResultsLoading] = useState(false);
  // 分析详情（从订阅行发起 或 结果列表点击查看，均不重复爬取）
  const [viewing, setViewing] = useState<ViewingAnalysis | null>(null);

  const fetchSubs = async () => { setLoading(true); try { const r = await subService.list(); setSubs(r.data); } catch { message.error("加载订阅失败"); } finally { setLoading(false); } };
  useEffect(() => { fetchSubs(); }, []);

  const loadResults = async () => {
    setResultsLoading(true);
    try {
      const res = await listAnalysisTasks({ limit: 500 });
      const latest = new Map<string, AnalysisTaskPayload>();
      for (const t of (res.items || [])) {
        if (!['success', 'partial'].includes(t.status)) continue;
        const prev = latest.get(t.xhs_user_id);
        if (!prev || (t.finished_at || '') > (prev.finished_at || '')) latest.set(t.xhs_user_id, t);
      }
      const rows = Array.from(latest.values());
      // 可合作档位 → 性价比降序 → 总分降序（与导出一致）
      rows.sort((a, b) => (rowRank(a) - rowRank(b)) || (rowCost(b) - rowCost(a)) || (rowOverall(b) - rowOverall(a)));
      setResults(rows);
    } catch { message.error('分析结果加载失败'); } finally { setResultsLoading(false); }
  };
  useEffect(() => { loadResults(); }, []);

  const handleExport = async () => {
    try {
      const blob = await exportAnalysisReport();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `博主分析对比_${new Date().toISOString().slice(0, 16).replace('T', '_')}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('已导出分析报告（按可合作/性价比排序）');
    } catch { message.error('导出失败，请稍后重试'); }
  };

  const openViewer = (user: ViewingAnalysis['user'], data: any, taskId: string | null) => {
    setViewing({ user, data, taskId, loading: false });
  };

  const handleAnalyzeSub = async (sub: { xhs_user_id: string; nickname: string; follower_count?: number }) => {
    const u = { user_id: sub.xhs_user_id, nickname: sub.nickname, fans: sub.follower_count || 0 };
    setViewing({ user: u, data: null, taskId: null, loading: true });
    try {
      const api = (await import('../services/api')).default;
      // 订阅入口：不传 refresh → 复用最近结果（默认 7 天缓存），长期可看
      const res = await api.post(`/notes/users/${sub.xhs_user_id}/analysis-tasks`, { nickname: sub.nickname, fans: sub.follower_count || 0, with_comments: false }, { timeout: 60000 });
      if (res.data.passed_prescreen === false) {
        message.warning('未通过粗筛：' + (res.data.reason || ''));
        setViewing({ user: u, data: null, taskId: null, loading: false });
        return;
      }
      const taskId = res.data.id;
      if (res.data.from_cache) {
        setViewing({ user: u, data: res.data.result, taskId, loading: false });
        message.success('已复用最近分析结果');
        return;
      }
      setViewing({ user: u, data: null, taskId, loading: true });
      const poll = setInterval(async () => {
        try {
          const r = await api.get(`/notes/users/${sub.xhs_user_id}/analysis-tasks/${taskId}`);
          const t = r.data;
          if (['success', 'partial', 'failed', 'cancelled'].includes(t.status)) {
            clearInterval(poll);
            const ok = t.status === 'success' || t.status === 'partial';
            setViewing({ user: u, data: ok ? t.result : null, taskId, loading: false });
            if (!ok) message.error('分析失败：' + (t.error || t.status));
            loadResults();
          }
        } catch { clearInterval(poll); setViewing({ user: u, data: null, taskId, loading: false }); }
      }, 3000);
    } catch (e: any) {
      message.error('分析失败：' + (e?.response?.data?.detail || e?.message || ''));
      setViewing({ user: u, data: null, taskId: null, loading: false });
    }
  };

  const handleAdd = async () => { const v = await form.validateFields(); try { await subService.create({ xhs_user_id: v.xhs_user_id, nickname: v.nickname, avatar: v.avatar }); message.success('已订阅'); setModalOpen(false); form.resetFields(); fetchSubs(); } catch (e: any) { message.error(e?.response?.data?.detail || '失败'); } };

  const handleRefresh = async (id: string) => {
    try {
      const r = await subService.refresh(id);
      const status = r.data?.refresh_status;
      if (status === 'failed') message.error('刷新失败: ' + (r.data?.refresh_error || '未知错误'), 5);
      else if (status === 'partial') message.warning('部分数据未更新: ' + (r.data?.refresh_error || ''), 5);
      else message.success('已刷新');
      fetchSubs();
    } catch { message.error('刷新失败'); }
  };

  const handleViewNotes = async (sub: Subscription) => {
    setNotesLoading(true); setViewingNickname(sub.nickname);
    try { const api = (await import("../services/api")).default; const res = await api.post("/notes/search", { query: sub.nickname, limit: 20 }); setViewingNotes(res.data.items||[]); setNotesModal(true); }
    catch { message.error("获取笔记失败"); } finally { setNotesLoading(false); }
  };

  const handleDelete = async (id: string) => { try { await subService.delete(id); message.success('已取消订阅'); fetchSubs(); } catch { message.error('删除失败'); } };

  const columns = [
    { title:'昵称', dataIndex:'nickname', key:'nickname', render:(v:string, r:Subscription) => <Space>{r.avatar ? <img src={r.avatar} style={{width:24,height:24,borderRadius:'50%'}}/> : null}<span>{v}</span></Space> },
    { title:'XHS ID', dataIndex:'xhs_user_id', key:'xhs_user_id', render:(v:string) => v.slice(0,12)+'...' },
    { title:'笔记数', dataIndex:'note_count', key:'note_count' },
    { title:'粉丝', dataIndex:'follower_count', key:'follower_count' },
    { title:'最后更新', dataIndex:'last_crawled_at', key:'last_crawled_at', render:(v:string) => v ? v.slice(0,16).replace('T',' ') : '-' },
    { title:'有更新', key:'has_update', render:(_:any, r:Subscription) => r.note_count > (r.notified_note_count ?? 0) ? <Tag color='red'>有更新</Tag> : <Tag>无</Tag> },
    { title:'操作', key:'actions', render:(_:any, r:Subscription) => <Space>
      <Button type='link' size='small' icon={<BarChartOutlined />} onClick={() => handleAnalyzeSub(r)}>分析</Button>
      <Button type='link' size='small' onClick={() => handleViewNotes(r)}>笔记</Button>
      <Button type='link' size='small' icon={<ReloadOutlined />} onClick={() => handleRefresh(r.id)}>刷新</Button>
      {r.note_count > (r.notified_note_count ?? 0) ? <Button type='link' size='small' onClick={async () => { try { await subService.ack(r.id); message.success('已标记为已查看'); fetchSubs(); } catch { message.error('操作失败'); } }}>标记已读</Button> : null}
      <Popconfirm title='取消订阅？' onConfirm={() => handleDelete(r.id)}><Button type='link' size='small' danger>取消</Button></Popconfirm>
    </Space> },
  ];

  const resultColumns = [
    { title:'昵称', dataIndex:'nickname', key:'nickname', width:180, render:(v:string, t:AnalysisTaskPayload) => v || t.xhs_user_id.slice(0,10) },
    { title:'粉丝', dataIndex:'follower_count', key:'fans', width:90, render:(v:number) => v.toLocaleString('zh-CN') },
    { title:'总分', key:'overall', width:70, render:(_:any, t:AnalysisTaskPayload) => { const s = t.result?.overall?.score; return s != null ? <Text strong>{s}</Text> : <Tag>数据不足</Tag>; } },
    { title:'等级', key:'level', width:70, render:(_:any, t:AnalysisTaskPayload) => t.result?.overall?.level || '-' },
    { title:'性价比', key:'cost', width:70, render:(_:any, t:AnalysisTaskPayload) => { const s = t.result?.dimensions?.cost_effectiveness?.score; return s != null ? s : '-'; } },
    { title:'可合作', key:'rec', width:90, render:(_:any, t:AnalysisTaskPayload) => { const r = (t.result?.decision?.recommendation) || 'insufficient_data'; const tag = REC_TAG[r] || { color: 'default', label: r }; return <Tag color={tag.color}>{tag.label}</Tag>; } },
    { title:'建议报价', key:'bid', width:180, render:(_:any, t:AnalysisTaskPayload) => { const d = t.result?.dimensions?.cost_effectiveness?.detail || {}; const p = d.suggested_bid_picture, v = d.suggested_bid_video; if (p == null && v == null) return '-'; return `图文 ${p != null ? '¥' + p : '-'} / 视频 ${v != null ? '¥' + v : '-'}`; } },
    { title:'阶段', key:'stage', width:80, render:(_:any, t:AnalysisTaskPayload) => t.result?.stage?.label || '-' },
    { title:'受众', key:'aud', width:110, render:(_:any, t:AnalysisTaskPayload) => { const a = t.result?.audience; return a?.dominant_level || '-'; } },
    { title:'分析时间', dataIndex:'finished_at', key:'finished_at', width:140, render:(v:string) => v ? v.slice(0,16).replace('T',' ') : '-' },
    { title:'操作', key:'actions', width:90, render:(_:any, t:AnalysisTaskPayload) => <Button type='link' size='small' onClick={() => openViewer({ user_id: t.xhs_user_id, nickname: t.nickname || t.xhs_user_id, fans: t.follower_count || 0 }, t.result, t.id)}>查看详情</Button> },
  ];

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <Title level={3} style={{ margin:0 }}>博主订阅</Title>
        <Button type='primary' icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>添加订阅</Button>
      </div>
      <Table dataSource={subs} columns={columns} rowKey='id' loading={loading} pagination={false} />

      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', margin: '24px 0 12px' }}>
        <Title level={3} style={{ margin:0 }}>分析结果（长期保存，点击查看无需重新分析）</Title>
        <Button icon={<DownloadOutlined />} onClick={handleExport} disabled={results.length === 0}>批量导出报告（Excel）</Button>
      </div>
      <Table
        dataSource={results}
        columns={resultColumns}
        rowKey='id'
        loading={resultsLoading}
        size="small"
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t:number) => `共 ${t} 位博主` }}
        onRow={(t: AnalysisTaskPayload) => ({ style: { cursor: 'pointer' }, onClick: () => openViewer({ user_id: t.xhs_user_id, nickname: t.nickname || t.xhs_user_id, fans: t.follower_count || 0 }, t.result, t.id) })}
      />

      <Modal title='添加订阅' open={modalOpen} onOk={handleAdd} onCancel={() => setModalOpen(false)} okText='订阅' cancelText='取消'>
        <Form form={form} layout='vertical'>
          <Form.Item label='小红书用户ID' name='xhs_user_id' rules={[{required:true,message:'请输入用户ID'}]}><Input placeholder='在小红书用户主页URL中 /user/profile/ 后面的部分' /></Form.Item>
          <Form.Item label='昵称' name='nickname' rules={[{required:true}]}><Input placeholder='博主昵称' /></Form.Item>
          <Form.Item label='头像URL（选填）' name='avatar'><Input placeholder='https://...' /></Form.Item>
        </Form>
      </Modal>
      <Modal title={viewingNickname + " 的笔记"} open={notesModal} onCancel={() => setNotesModal(false)} footer={null} width={1000}>
        {notesLoading ? <Spin style={{ display:"block", margin:"48px auto" }} /> : viewingNotes.length > 0 ? <Row gutter={[12,12]}>{viewingNotes.map((n:any,i:number) => <Col key={i} xs={24} sm={12} md={8}><div key={i} onClick={() => setDetailNote(n)} style={{cursor:"pointer"}}><NoteCardView note={n} /></div></Col>)}</Row> : <div style={{ padding:48, textAlign:"center", color:"#999" }}>暂无笔记</div>}
      </Modal>
      <Modal title={viewing ? (viewing.user.nickname || '博主') + ' 分析报告' : '分析报告'} open={!!viewing} onCancel={() => setViewing(null)} footer={null} width={1100} destroyOnClose>
        {viewing ? (
          viewing.loading ? (
            <div style={{ padding: 48, textAlign: 'center' }}><Spin /> <Text type="secondary" style={{ marginLeft: 8 }}>正在分析（可复用最近结果，最长约 1 分钟）...</Text></div>
          ) : viewing.data ? (
            <UserAnalysisPanel user={viewing.user} data={viewing.data} taskId={viewing.taskId} onOpenNote={(n) => setDetailNote(n)} onAnalyzeUser={(u) => handleAnalyzeSub({ xhs_user_id: u.user_id, nickname: u.nickname, follower_count: u.fans })} />
          ) : (
            <div style={{ padding: 48, textAlign: 'center', color: '#999' }}>暂无分析结果（未通过粗筛或分析失败）</div>
          )
        ) : null}
      </Modal>
      <NoteDetail open={!!detailNote} note={detailNote} onClose={() => setDetailNote(null)} />
    </div>
  );
}
