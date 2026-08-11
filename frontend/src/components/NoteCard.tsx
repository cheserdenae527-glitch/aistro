import { Card, Tag, Typography, Row, Col, Space, Statistic } from 'antd';
import SubscribeButton from './SubscribeButton';
import { HeartOutlined, MessageOutlined, StarOutlined, PictureOutlined, ShareAltOutlined } from '@ant-design/icons';
const { Text, Title } = Typography;

export interface NoteCardData {
  xsec_token: string;
  title: string;
  author: { id?: string; nickname: string; avatar: string };
  stats: { liked: number; collected: number; comments: number; shared?: number };
  image_urls: string[];
  cover_url: string;
  tags: string[];
  platform_note_id: string;
  desc: string;
  type?: string;
  full_stats?: boolean;
}

export function parseNote(raw: any): NoteCardData {
  const nc = raw?.note_card ?? raw;
  const user = nc.user ?? {};
  const interact = nc.interact_info ?? {};
  const images: any[] = nc.image_list ?? [];
  const imageUrls: string[] = [];
  for (const img of images) {
    const infoList = img.info_list ?? [];
    const dft = infoList.find((i: any) => i.image_scene === 'WB_DFT');
    if (dft) imageUrls.push(dft.url); else if (infoList.length > 0) imageUrls.push(infoList[0].url);
  }
  return {
    title: nc.display_title || nc.title || '',
    author: { id: user.user_id || user.id || '', nickname: user.nickname || user.nick_name || '', avatar: user.avatar || '' },
    stats: { liked: Number(interact.liked_count) || 0, collected: Number(interact.collected_count) || 0, comments: Number(interact.comment_count) || 0, shared: Number(interact.shared_count) || 0 },
    image_urls: imageUrls,
    cover_url: nc.cover?.url_default || imageUrls[0] || '',
    tags: (nc.corner_tag_info ?? []).map((t: any) => t.text),
    platform_note_id: raw.id || '',
    xsec_token: raw.xsec_token || "",
    desc: nc.desc || '',
    type: nc.type || raw.type || '',
    full_stats: raw.full_stats,
  };
}

const proxyImage = (url: string, size = 0) =>
  '/api/v1/images/proxy?url=' + encodeURIComponent(url.replace(/^http:/, 'https:')) + '&size=' + size;

export function NoteCardView({ note }: { note: NoteCardData }) {
  const cover = note.cover_url
    ? proxyImage(note.cover_url.replace(/!nc_n_webp_mw_1.*$/, '!nc_n_webp_mw_1'), 800)
    : '';
  return (
    <Card hoverable style={{ borderRadius: 8, overflow: 'hidden' }}
      cover={cover ? (
        <div style={{ height: 200, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f0f0' }}>
          <img alt={note.title} src={cover} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
      ) : (
        <div style={{ height: 200, background: '#f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <PictureOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
        </div>
      )}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Title level={5} style={{ margin: 0, fontSize: 14, flex: 1 }} ellipsis={{ rows: 2 }}>{note.title}</Title>
        {note.type === 'video' ? <Tag color="red" style={{ fontSize: 10, margin: 0 }}>视频</Tag> : null}
        {note.full_stats === false ? <Tag color="orange" style={{ fontSize: 10, margin: 0 }}>部分数据</Tag> : null}
      </div>
      <Space style={{ marginTop: 8 }} wrap>
        {note.author.avatar ? <img src={proxyImage(note.author.avatar, 64)} alt='' style={{ width: 20, height: 20, borderRadius: '50%' }} /> : null}
        <Text type='secondary' style={{ fontSize: 12 }}>{note.author.nickname}</Text>
        {note.author.id ? <span onClick={(e) => e.stopPropagation()}><SubscribeButton user={{ xhs_user_id: note.author.id, nickname: note.author.nickname, avatar: note.author.avatar }} showText={false} /></span> : null}
      </Space>
      <Row gutter={8} style={{ marginTop: 8 }}>
        <Col span={6}><Statistic value={note.stats.liked} prefix={<HeartOutlined />} valueStyle={{ fontSize: 13 }} /></Col>
        <Col span={6}><Statistic value={note.stats.comments} prefix={<MessageOutlined />} valueStyle={{ fontSize: 13 }} /></Col>
        <Col span={6}><Statistic value={note.stats.collected} prefix={<StarOutlined />} valueStyle={{ fontSize: 13 }} /></Col>
        <Col span={6}><Statistic value={note.stats.shared ?? 0} prefix={<ShareAltOutlined />} valueStyle={{ fontSize: 13 }} /></Col>
      </Row>
      {note.image_urls.length > 1 && <div style={{ marginTop:4, fontSize:11, color:"#999" }}>{note.image_urls.length + " 张图片"}</div>}
      {note.tags.length > 0 && <div style={{ marginTop: 6 }}>{note.tags.map((t, i) => <Tag key={i} style={{ fontSize: 10 }}>{t}</Tag>)}</div>}
    </Card>
  );
}
