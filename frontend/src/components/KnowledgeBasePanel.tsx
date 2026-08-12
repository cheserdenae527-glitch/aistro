import { useEffect, useState } from 'react';
import { Button, Col, Empty, Image, Input, message, Modal, Popconfirm, Row, Select, Space, Statistic, Table, Tag, Typography } from 'antd';
import { DeleteOutlined, DownloadOutlined, HeartOutlined, LinkOutlined, MessageOutlined, PictureOutlined, ReloadOutlined, ShareAltOutlined, StarOutlined, VideoCameraOutlined } from '@ant-design/icons';
const { Text } = Typography;

interface KbEntry {
  id: string;
  platform_note_id: string;
  xhs_user_id: string;
  author_nickname: string;
  author_avatar: string;
  title: string;
  desc: string;
  note_type: string;
  cover_url: string;
  image_urls: string[];
  video_url: string;
  tags: string[];
  topics: string[];
  content_md: string | null;
  cover_local: string | null;
  image_urls_local: string[];
  video_local: string | null;
  stats: Record<string, number>;
  liked_count: number;
  collected_count: number;
  comments_count: number;
  shared_count: number;
  published_at: string | null;
  source: string;
  note_url: string;
  synced_at: string | null;
}

const SOURCE_LABELS: Record<string, string> = {
  manual: '手动',
  search: '搜索',
  user_notes: '作品',
  analysis: '分析',
  subscription: '订阅',
};

const TYPE_LABELS: Record<string, string> = { video: '视频', image: '图文', normal: '图文' };

function fmtNum(v?: number) {
  if (!v) return '0';
  if (v >= 10000) return (v / 10000).toFixed(1).replace(/\.0$/, '') + '万';
  if (v >= 1000) return (v / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(v);
}

const px = (url: string, size = 0) => '/api/v1/images/proxy?url=' + encodeURIComponent(url) + '&size=' + size;
const localMedia = (obj: string | null | undefined) => obj ? '/api/v1/media/' + obj : '';
const coverSrc = (r: KbEntry) => r.cover_local ? localMedia(r.cover_local) : (r.cover_url ? px(r.cover_url) : '');
const detailImages = (r: KbEntry) => r.image_urls_local && r.image_urls_local.length ? r.image_urls_local.map(localMedia) : (r.image_urls || []).map((u: string) => px(u, 1200));
const detailVideo = (r: KbEntry) => r.video_local ? localMedia(r.video_local) : (r.video_url ? '/api/v1/images/video-proxy?url=' + encodeURIComponent(r.video_url) : '');

export default function KnowledgeBasePanel() {
  const [entries, setEntries] = useState<KbEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [author, setAuthor] = useState('');
  const [noteType, setNoteType] = useState('');
  const [source, setSource] = useState('');
  const [topic, setTopic] = useState('');
  const [sort, setSort] = useState('hot');
  const [minLikes, setMinLikes] = useState<number | null>(null);
  const [detail, setDetail] = useState<KbEntry | null>(null);
  const [stats, setStats] = useState<any>({});
  const [mediaSyncing, setMediaSyncing] = useState(false);

  const fetchStats = async () => {
    try {
      const api = (await import('../services/api')).default;
      const res = await api.get('/knowledge/stats');
      setStats(res.data || {});
    } catch { /* keep old stats */ }
  };

  const fetchList = async (p = page, ps = pageSize) => {
    setLoading(true);
    try {
      const api = (await import('../services/api')).default;
      const res = await api.get('/knowledge', {
        params: {
          keyword: keyword || undefined,
          author: author || undefined,
          note_type: noteType || undefined,
          source: source || undefined,
          topic: topic || undefined,
          min_likes: minLikes || undefined,
          sort,
          page: p,
          page_size: ps,
        },
      });
      setEntries(res.data.items || []);
      setTotal(res.data.total || 0);
      setPage(p);
      setPageSize(ps);
    } catch (err: any) {
      message.error('加载知识库失败：' + (err?.response?.data?.detail || err?.message || ''), 5);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStats(); }, []);
  useEffect(() => { fetchList(1, pageSize); /* eslint-disable-next-line */ }, [noteType, source, topic, sort, minLikes, pageSize]);

  const handleSyncMedia = async () => {
    setMediaSyncing(true);
    try {
      const api = (await import('../services/api')).default;
      const res = await api.post('/knowledge/media/sync', {}, { timeout: 600000 });
      message.success(`本地媒体同步完成：更新 ${res.data?.updated ?? 0} 条，失败 ${res.data?.failed ?? 0} 条`);
      fetchStats();
      fetchList(page, pageSize);
    } catch (err: any) {
      message.error('同步媒体失败：' + (err?.response?.data?.detail || err?.message || ''), 5);
    } finally {
      setMediaSyncing(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const api = (await import('../services/api')).default;
      await api.delete(`/knowledge/${id}`);
      message.success('已从知识库删除');
      fetchStats();
      fetchList(page, pageSize);
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message || ''), 5);
    }
  };

  const statCards = [
    { title: '知识条目', value: stats.total ?? 0, suffix: '' },
    { title: '图文', value: stats.images ?? 0, suffix: '' },
    { title: '视频', value: stats.videos ?? 0, suffix: '' },
    { title: '累计点赞', value: stats.total_likes ?? 0, suffix: '' },
    { title: '累计收藏', value: stats.total_collected ?? 0, suffix: '' },
    { title: '累计评论', value: stats.total_comments ?? 0, suffix: '' },
  ];

  const columns = [
    {
      title: '笔记',
      dataIndex: 'title',
      key: 'title',
      width: 300,
      render: (_: string, r: KbEntry) => (
        <Space>
          {coverSrc(r) ? <img src={coverSrc(r)} alt="" style={{ width: 56, height: 56, borderRadius: 4, objectFit: 'cover' }} /> : <div style={{ width: 56, height: 56, borderRadius: 4, background: '#f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><PictureOutlined /></div>}
          <div style={{ maxWidth: 220 }}>
            <Text strong ellipsis={{ tooltip: r.title }} style={{ display: 'block' }}>{r.title || '无标题'}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>{r.author_nickname || '-'}</Text>
          </div>
        </Space>
      ),
    },
    { title: '类型', dataIndex: 'note_type', key: 'note_type', width: 70, render: (v: string) => <Tag color={v === 'video' ? 'red' : 'blue'}>{TYPE_LABELS[v] || v}</Tag> },
    {
      title: '数据',
      key: 'stats',
      width: 240,
      render: (_: any, r: KbEntry) => (
        <Space size={12} wrap>
          <span><HeartOutlined style={{ color: '#eb2f96' }} /> {fmtNum(r.liked_count)}</span>
          <span><StarOutlined style={{ color: '#faad14' }} /> {fmtNum(r.collected_count)}</span>
          <span><MessageOutlined style={{ color: '#1677ff' }} /> {fmtNum(r.comments_count)}</span>
          <span><ShareAltOutlined style={{ color: '#52c41a' }} /> {fmtNum(r.shared_count)}</span>
        </Space>
      ),
    },
    { title: '发布时间', dataIndex: 'published_at', key: 'published_at', width: 150, render: (v: string | null) => v ? new Date(v).toLocaleDateString('zh-CN') : '-' },
    { title: '来源', dataIndex: 'source', key: 'source', width: 80, render: (v: string) => <Tag>{SOURCE_LABELS[v] || v}</Tag> },
    { title: '话题', key: 'topics', width: 200, render: (_: any, r: KbEntry) => <Space wrap size={4}>{(r.topics || []).slice(0, 3).map((t, i) => <Tag key={i} style={{ fontSize: 10 }}>{t}</Tag>)}</Space> },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: any, r: KbEntry) => (
        <Space>
          <Button type="link" size="small" icon={<LinkOutlined />} onClick={() => setDetail(r)}>查看</Button>
          {r.note_url ? <a href={r.note_url} target="_blank" rel="noreferrer"><Button type="link" size="small" icon={<LinkOutlined />}>原文</Button></a> : null}
          <Popconfirm title="确认从知识库删除？" onConfirm={() => handleDelete(r.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {statCards.map((s, i) => (
          <Col key={i} xs={12} sm={8} md={6} lg={4}>
            <div style={{ background: '#fff', border: '1px solid #f0f0f0', borderRadius: 8, padding: '12px 16px' }}>
              <Statistic title={s.title} value={s.value} valueStyle={{ fontSize: 22 }} />
            </div>
          </Col>
        ))}
      </Row>

      <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <Input.Search placeholder="搜索标题/内容/作者" allowClear style={{ width: 220 }} onSearch={(v) => { setKeyword(v); fetchList(1, pageSize); }} />
        <Input placeholder="作者" allowClear style={{ width: 140 }} value={author} onChange={(e) => setAuthor(e.target.value)} onPressEnter={() => fetchList(1, pageSize)} />
        <Select placeholder="类型" allowClear style={{ width: 110 }} value={noteType || undefined} onChange={(v) => setNoteType(v || '')} options={[{ value: 'image', label: '图文' }, { value: 'video', label: '视频' }]} />
        <Select placeholder="来源" allowClear style={{ width: 110 }} value={source || undefined} onChange={(v) => setSource(v || '')} options={Object.entries(SOURCE_LABELS).map(([value, label]) => ({ value, label }))} />
<Select placeholder='话题分类' allowClear showSearch style={{ width: 180 }} value={topic || undefined} onChange={(v) => setTopic(v || '')} options={Object.entries(stats.topics || {}).slice(0, 50).map(([value, count]) => ({ value, label: value + ' (' + count + ')' }))} />
        <Select placeholder="排序" style={{ width: 120 }} value={sort} onChange={(v) => setSort(v)} options={[
          { value: 'hot', label: '综合热度' },
          { value: 'new', label: '最新' },
          { value: 'likes', label: '最多点赞' },
          { value: 'collected', label: '最多收藏' },
          { value: 'comments', label: '最多评论' },
          { value: 'shared', label: '最多分享' },
        ]} />
        <Input type="number" placeholder="最低点赞" style={{ width: 110 }} value={minLikes ?? ''} onChange={(e) => setMinLikes(e.target.value === '' ? null : Number(e.target.value))} onPressEnter={() => fetchList(1, pageSize)} />
        <Button icon={<ReloadOutlined />} onClick={() => { fetchStats(); fetchList(1, pageSize); }}>刷新</Button>
        <Button icon={<DownloadOutlined />} loading={mediaSyncing} onClick={handleSyncMedia}>同步本地媒体</Button>
      </div>

      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={entries}
        pagination={{ current: page, pageSize, total, showSizeChanger: true, showTotal: (t) => `共 ${t} 条`, onChange: (p, ps) => fetchList(p, ps) }}
        locale={{ emptyText: <Empty description="知识库为空，分析完成或订阅刷新后会自动同步；也可在达人寻觅的博主作品里手动加入" /> }}
      />

      <Modal open={!!detail} onCancel={() => setDetail(null)} footer={null} width={820} title={detail ? (detail.title || '笔记详情').slice(0, 45) : ''}>
        {detail ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Space align="start">
              {detail.author_avatar ? <img src={px(detail.author_avatar)} alt="" style={{ width: 40, height: 40, borderRadius: '50%' }} /> : null}
              <div>
                <Text strong>{detail.author_nickname || '-'}</Text>
                <div><Text type="secondary" style={{ fontSize: 12 }}>{detail.published_at ? new Date(detail.published_at).toLocaleString('zh-CN') : '发布时间未知'} · {SOURCE_LABELS[detail.source] || detail.source}</Text></div>
              </div>
            </Space>
            {detail.desc ? <Text style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{detail.desc}</Text> : null}
            {detailVideo(detail) ? (
              <video controls src={detailVideo(detail)} style={{ width: '100%', maxHeight: 480, background: '#000', borderRadius: 8 }} />
            ) : detailImages(detail).length > 0 ? (
              <Image.PreviewGroup>
                <Space wrap>
                  {detailImages(detail).map((u: string, i: number) => <Image key={i} src={u} width={180} height={180} style={{ objectFit: 'cover', borderRadius: 8 }} />)}
                </Space>
              </Image.PreviewGroup>
            ) : coverSrc(detail) ? <img src={coverSrc(detail)} alt="" style={{ maxWidth: '100%', borderRadius: 8 }} /> : null}
            <Space size={16}>
              <Tag icon={<HeartOutlined />}>{fmtNum(detail.liked_count)}</Tag>
              <Tag icon={<StarOutlined />}>{fmtNum(detail.collected_count)}</Tag>
              <Tag icon={<MessageOutlined />}>{fmtNum(detail.comments_count)}</Tag>
              <Tag icon={<ShareAltOutlined />}>{fmtNum(detail.shared_count)}</Tag>
              <Tag color={detail.note_type === 'video' ? 'red' : 'blue'}>{detail.note_type === 'video' ? <VideoCameraOutlined /> : <PictureOutlined />} {TYPE_LABELS[detail.note_type] || detail.note_type}</Tag>
            </Space>
            {detail.tags.length > 0 ? <Space wrap>{detail.tags.map((t, i) => <Tag key={i}>{t}</Tag>)}</Space> : null}
            {detail.topics && detail.topics.length > 0 ? <Space wrap>{detail.topics.map((t, i) => <Tag key={'t' + i} color="purple">{t}</Tag>)}</Space> : null}
            {detail.note_url ? <a href={detail.note_url} target="_blank" rel="noreferrer"><Button icon={<LinkOutlined />}>打开原文</Button></a> : null}
          </Space>
        ) : null}
      </Modal>
    </div>
  );
}


