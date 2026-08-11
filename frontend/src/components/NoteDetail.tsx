import { useEffect, useState } from 'react';
import { Modal, Image, Typography, Row, Col, Space, Tag, Spin, message, Button } from 'antd';
import { HeartOutlined, MessageOutlined, StarOutlined, ShareAltOutlined, DownloadOutlined } from '@ant-design/icons';
import type { NoteCardData } from './NoteCard';
import SubscribeButton from './SubscribeButton';
const { Text, Paragraph } = Typography;
const px = (url: string, size = 0) => '/api/v1/images/proxy?url=' + encodeURIComponent(url) + '&size=' + size;

export default function NoteDetail({ open, note, onClose }: { open: boolean; note: NoteCardData | null; onClose: () => void }) {
  const [cur, setCur] = useState(0);
  const [detail, setDetail] = useState<NoteCardData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !note) return;
    setCur(0);
    setDetail(note);
    setLoading(true);
    let active = true;
    (async () => {
      try {
        // 列表已是完整数据时不再重复请求，避免空详情覆盖真实互动数据
        if (note.full_stats === true) return;
        const api = (await import('../services/api')).default;
        const res = await api.get(`/notes/${note.platform_note_id}`, { params: { xsec_token: note.xsec_token || '' } });
        if (!active) return;
        const merged = { ...res.data };
        const freshStats = merged.stats || {};
        const oldStats = note.stats || {};
        const hasFresh = Object.values(freshStats).some((v) => Number(v) > 0);
        if (!hasFresh && Object.values(oldStats).some((v) => Number(v) > 0)) {
          merged.stats = oldStats;
          merged.full_stats = note.full_stats;
        }
        setDetail(merged);
      } catch {
        // 详情失败时保留列表数据展示
        if (active) message.warning('完整数据加载失败，已展示当前数据', 2);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [open, note]);

  const data: any = detail || note;
  if (!note) return null;
  const imgs = (data.image_urls || []).map((u: string) => u.replace(/^http:/, 'https:'));
  const stats = data.stats || {};
  const hasFullStats = data.full_stats !== false || (stats.comments || stats.collected || stats.shared);

  return (
    <Modal open={open} onCancel={onClose} footer={null} width={900} title={data.title ? data.title.slice(0, 45) : '笔记详情'}>
      <Spin spinning={loading} tip="正在加载完整数据...">
        <Row gutter={24}>
          <Col xs={24} md={14}>
            {data.video_url ? (
              <>
                <video controls src={'/api/v1/images/video-proxy?url=' + encodeURIComponent(data.video_url)} style={{ width: '100%', maxHeight: 500, background: '#000', borderRadius: 8 }} />
                <Space style={{ marginTop: 8 }}>
                  <a href={'/api/v1/images/video-proxy?url=' + encodeURIComponent(data.video_url) + '&download=1'} download="xhs_video.mp4">
                    <Button size="small" icon={<DownloadOutlined />}>下载视频</Button>
                  </a>
                </Space>
              </>
            ) : imgs.length > 0 ? (function() {
              const main = imgs[cur] || imgs[0];
              return (<>
                <Image src={px(main, 1200)} style={{ width: '100%', maxHeight: 500, objectFit: 'contain', background: '#f5f5f5', borderRadius: 8 }} />
                {imgs.length > 1 && <div style={{ marginTop: 8, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {imgs.map((url: string, i: number) => <img key={i} src={px(url, 160)} onClick={() => setCur(i)}
                    style={{ width: 52, height: 52, borderRadius: 4, cursor: 'pointer', objectFit: 'cover', border: i === cur ? '2px solid #1677ff' : '2px solid transparent' }} />)}
                </div>}
                <Text type='secondary' style={{ fontSize: 12, display: 'block', marginTop: 6 }}>共 {imgs.length} 张 · 点击图片可放大</Text>
              </>);
            })() : <div style={{ height:300, background:'#f5f5f5', display:'flex', alignItems:'center', justifyContent:'center', borderRadius:8 }}>无图片</div>}
          </Col>
          <Col xs={24} md={10}>
            <Space wrap>
              {data.author?.avatar ? <img src={px(data.author.avatar.replace(/^http:/,'https:'))} style={{ width:32, height:32, borderRadius:'50%' }} /> : null}
              <Text strong>{data.author?.nickname || ''}</Text>
              {data.author?.id ? <SubscribeButton user={{ xhs_user_id: data.author.id, nickname: data.author.nickname, avatar: data.author.avatar }} showText={false} /> : null}
            </Space>
            {data.desc ? <Paragraph style={{ marginTop:8, fontSize:13, whiteSpace:'pre-wrap' }}>{data.desc}</Paragraph> : null}
            {data.published_at ? <Text type='secondary' style={{ display:'block', fontSize:12, marginTop:4 }}>发布时间：{new Date(data.published_at).toLocaleString('zh-CN')}</Text> : null}
            <Space style={{ marginBottom:12, marginTop:8 }}>
              <Tag icon={<HeartOutlined />}>{stats.liked ?? 0}</Tag>
              <Tag icon={<MessageOutlined />}>{stats.comments ?? 0}</Tag>
              <Tag icon={<StarOutlined />}>{stats.collected ?? 0}</Tag>
              <Tag icon={<ShareAltOutlined />}>{stats.shared ?? 0}</Tag>
              {hasFullStats ? <Tag color="green">完整数据</Tag> : <Tag color="orange">部分数据</Tag>}
            </Space>
            {(data.tags || []).length > 0 && <div>{(data.tags as string[]).map((t,i) => <Tag key={i}>{t}</Tag>)}</div>}
          </Col>
        </Row>
      </Spin>
    </Modal>
  );
}
