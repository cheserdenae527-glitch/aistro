import { useEffect, useState } from 'react';
import { Button, Form, Input, message, Modal, Table, Typography, Popconfirm, Space, Row, Col, Spin } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { NoteCardView, type NoteCardData } from '../components/NoteCard';
import NoteDetail from '../components/NoteDetail';
import { subService, type Subscription } from '../services/subscriptions';
const { Title } = Typography;

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

  const fetchSubs = async () => { setLoading(true); try { const r = await subService.list(); setSubs(r.data); } catch { message.error("加载订阅失败"); } finally { setLoading(false); } };
  useEffect(() => { fetchSubs(); }, []);

  const handleAdd = async () => { const v = await form.validateFields(); try { await subService.create({ xhs_user_id: v.xhs_user_id, nickname: v.nickname, avatar: v.avatar }); message.success('已订阅'); setModalOpen(false); form.resetFields(); fetchSubs(); } catch (e: any) { message.error(e?.response?.data?.detail || '失败'); } };

  const handleRefresh = async (id: string) => { try { await subService.refresh(id); message.success('已刷新'); fetchSubs(); } catch { message.error('刷新失败'); } };

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
    { title:'操作', key:'actions', render:(_:any, r:Subscription) => <Space>
      <Button type='link' size='small' onClick={() => handleViewNotes(r)}>笔记</Button><Button type='link' size='small' icon={<ReloadOutlined />} onClick={() => handleRefresh(r.id)}>刷新</Button>
      <Popconfirm title='取消订阅？' onConfirm={() => handleDelete(r.id)}><Button type='link' size='small' danger>取消</Button></Popconfirm>
    </Space> },
  ];

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <Title level={3} style={{ margin:0 }}>博主订阅</Title>
        <Button type='primary' icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>添加订阅</Button>
      </div>
      <Table dataSource={subs} columns={columns} rowKey='id' loading={loading} pagination={false} />
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
      <NoteDetail open={!!detailNote} note={detailNote} onClose={() => setDetailNote(null)} />
    </div>
  );
}




