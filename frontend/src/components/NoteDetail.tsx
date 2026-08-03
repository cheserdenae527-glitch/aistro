import { useState } from 'react';
import { Modal, Image, Typography, Row, Col, Space, Tag } from 'antd';
import { HeartOutlined, MessageOutlined, StarOutlined } from '@ant-design/icons';
import type { NoteCardData } from './NoteCard';
const { Text, Paragraph } = Typography;
const px = (url: string, size = 0) => '/api/v1/images/proxy?url=' + encodeURIComponent(url) + '&size=' + size;

export default function NoteDetail({ open, note, onClose }: { open: boolean; note: NoteCardData | null; onClose: () => void }) {
  const [cur, setCur] = useState(0);
  if (!note) return null;
  const imgs = note.image_urls.map(u => u.replace(/^http:/, 'https:'));
  return (
    <Modal open={open} onCancel={onClose} footer={null} width={900} title={note.title.slice(0, 45)}>
      <Row gutter={24}>
        <Col xs={24} md={14}>
          {imgs.length > 0 ? (<>
            <Image src={px(imgs[cur], 1200)} style={{ width: '100%', maxHeight: 500, objectFit: 'contain', background: '#f5f5f5', borderRadius: 8 }} />
            {imgs.length > 1 && <div style={{ marginTop: 8, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {imgs.map((url, i) => <img key={i} src={px(url)} onClick={() => setCur(i)}
                style={{ width: 52, height: 52, borderRadius: 4, cursor: 'pointer', objectFit: 'cover', border: i === cur ? '2px solid #1677ff' : '2px solid transparent' }} />)}
            </div>}
            <Text type='secondary' style={{ fontSize: 12, display: 'block', marginTop: 6 }}>共 {imgs.length} 张 · 点击图片可放大</Text>
          </>) : <div style={{ height:300, background:'#f5f5f5', display:'flex', alignItems:'center', justifyContent:'center', borderRadius:8 }}>无图片</div>}
        </Col>
        <Col xs={24} md={10}>
          <Space>
            {note.author.avatar ? <img src={px(note.author.avatar.replace(/^http:/,'https:'))} style={{ width:32, height:32, borderRadius:'50%' }} /> : null}
            <Text strong>{note.author.nickname}</Text>
          </Space>
          {note.desc && <Paragraph style={{ marginTop:8, fontSize:13, whiteSpace:'pre-wrap' }}>{note.desc}</Paragraph>}
          <Space style={{ marginBottom:12, marginTop:8 }}>
            <Tag icon={<HeartOutlined />}>{note.stats.liked}</Tag>
            <Tag icon={<MessageOutlined />}>{note.stats.comments}</Tag>
            <Tag icon={<StarOutlined />}>{note.stats.collected}</Tag>
          </Space>
          {note.tags.length > 0 && <div>{note.tags.map((t,i) => <Tag key={i}>{t}</Tag>)}</div>}
        </Col>
      </Row>
    </Modal>
  );
}
