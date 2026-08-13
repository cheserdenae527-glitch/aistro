import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Form, Input, message, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd';
import { DeleteOutlined, DisconnectOutlined, EditOutlined, PauseCircleOutlined, PlayCircleOutlined, PlusOutlined, QrcodeOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { crawlerPoolService, type CookiePoolItem, type CookiePoolStats, type CrawlCallRecord, type ProxyPoolStats } from '../services/crawlerPool';

const { Title, Text } = Typography;

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  available: { text: '可用', color: 'green' },
  cooling: { text: '冷却中', color: 'orange' },
  invalid: { text: '已失效', color: 'red' },
  paused: { text: '已暂停', color: 'default' },
};

const SOURCE_LABELS: Record<string, string> = {
  tunnel: '隧道代理',
  short_proxy: '短效代理',
  static: '静态代理',
  none: '未配置',
};

const JOB_LABELS: Record<string, string> = {
  search: '搜索',
  search_users: '搜索博主',
  note_detail: '笔记详情',
  comment: '评论',
  blogger: '博主信息',
};

const RESULT_COLORS: Record<string, string> = {
  ok: 'green',
  risk_signal: 'red',
  http_error: 'orange',
  network_error: 'orange',
  circuit_open: 'purple',
};

function fmtTime(v?: number | string | null) {
  if (!v) return '-';
  const d = typeof v === 'number' ? new Date(v * 1000) : new Date(v);
  if (isNaN(d.getTime())) return String(v);
  return d.toLocaleString('zh-CN', { hour12: false });
}

function fmtTs(v?: number | null) {
  if (!v) return '-';
  const d = new Date(v);
  return d.toLocaleString('zh-CN', { hour12: false });
}

export default function CrawlerPoolPanel() {
  const [cookies, setCookies] = useState<CookiePoolItem[]>([]);
  const [stats, setStats] = useState<CookiePoolStats | null>(null);
  const [proxy, setProxy] = useState<ProxyPoolStats | null>(null);
  const [calls, setCalls] = useState<CrawlCallRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [proxyLoading, setProxyLoading] = useState(false);
  const [callsLoading, setCallsLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [editItem, setEditItem] = useState<CookiePoolItem | null>(null);
  const [addForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const fetch = useCallback(async (silent = false) => {
    setLoading(true);
    try {
      const res = await crawlerPoolService.listCookies();
      setCookies(res.data.items || []);
      setStats(res.data.stats || null);
    } catch (e: any) {
      if (!silent) message.error('加载 Cookie 池失败: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, []);

  const handleScanLogin = async () => {
    const desk = (window as any).aistroDesktop;
    if (!desk || typeof desk.login !== 'function') {
      message.warning('扫码登录仅桌面端可用，请在 AiRestro 桌面端操作');
      return;
    }
    setLoginLoading(true);
    try {
      const token = localStorage.getItem('token') || '';
      const r = await desk.login(token);
      if (r && r.ok) {
        const ev = r.evicted ? `（已淘汰 Cookie ${String(r.evicted).slice(0, 8)}）` : '';
        message.success(r.action === 'replaced' ? `已替换刷新该账号 Cookie${ev}` : `已新增 Cookie${ev}`, 5);
      } else {
        const reason = r?.reason;
        let msg = '';
        switch (r?.action) {
          case 'cancel': msg = '已取消扫码'; break;
          case 'timeout': msg = '扫码超时，请重试'; break;
          case 'token_expired': msg = '系统登录已过期，请先重新登录'; break;
          case 'verify_failed': msg = reason === 'network_error' ? '验证服务异常，请稍后重试' : reason === 'no_permission' ? '该账号无搜索权限（新号或被限制），请更换有搜索权限的账号扫码' : '登录态不完整，请重新扫码'; break;
          case 'pool_full': msg = 'Cookie 池已满且均在占用，请先移除一条'; break;
          default: msg = '扫码登录失败';
        }
        message.error(msg + (r?.error ? `：${r.error}` : ''), 6);
      }
      fetch(false);
    } catch (e: any) {
      message.error('扫码登录失败：' + (e?.message || e), 6);
    } finally {
      setLoginLoading(false);
    }
  };

  const fetchProxy = useCallback(async () => {
    setProxyLoading(true);
    try {
      const res = await crawlerPoolService.proxyStatus();
      setProxy(res.data);
    } catch {
      /* 轮询失败保持旧数据 */
    } finally {
      setProxyLoading(false);
    }
  }, []);

  const fetchCalls = useCallback(async () => {
    setCallsLoading(true);
    try {
      const res = await crawlerPoolService.recentCalls(50);
      setCalls(res.data.items || []);
    } catch {
      /* 轮询失败保持旧数据 */
    } finally {
      setCallsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch(true);
    fetchProxy();
    fetchCalls();
    const t = setInterval(() => {
      fetch(true);
      fetchCalls();
    }, 10000);
    return () => clearInterval(t);
  }, [fetch, fetchProxy, fetchCalls]);

  const addCookie = async () => {
    const v = await addForm.validateFields();
    try {
      await crawlerPoolService.addCookie(v.cookie, v.label || '');
      message.success('已添加 Cookie');
      setAddOpen(false);
      addForm.resetFields();
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message);
    }
  };

  const openEdit = (item: CookiePoolItem) => {
    setEditItem(item);
    editForm.setFieldsValue({ label: item.label, status: item.status, cookie: item.cookie });
  };

  const saveEdit = async () => {
    if (!editItem) return;
    const v = await editForm.validateFields();
    try {
      await crawlerPoolService.updateCookie(editItem.id, {
        label: v.label,
        status: v.status,
        cookie: v.cookie || undefined,
      });
      message.success('已更新');
      setEditItem(null);
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message);
    }
  };

  const setStatus = async (item: CookiePoolItem, status: string) => {
    try {
      await crawlerPoolService.updateCookie(item.id, { status });
      message.success(status === 'available' ? '已启用' : '已暂停');
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message);
    }
  };

  const removeCookie = async (id: string) => {
    try {
      await crawlerPoolService.deleteCookie(id);
      message.success('已删除');
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message);
    }
  };

  const unbind = async (item: CookiePoolItem) => {
    try {
      await crawlerPoolService.unbindCookie(item.id);
      message.success('已解绑代理');
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message);
    }
  };

  const rebind = async (item: CookiePoolItem) => {
    try {
      await crawlerPoolService.rebindCookie(item.id);
      message.success('已重新绑定代理');
      fetch();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message);
    }
  };

  const refreshProxy = async () => {
    try {
      const res = await crawlerPoolService.refreshProxies();
      setProxy(res.data);
      message.success('代理池已刷新');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message);
    }
  };

  const cookieColumns = [
    {
      title: '名称',
      dataIndex: 'label',
      width: 140,
      render: (v: string) => <Text strong>{v || '-'}</Text>,
    },
    {
      title: '最近成功',
      dataIndex: 'last_success',
      width: 120,
      render: (v: number | null) => {
        if (!v) return <Text type="secondary">-</Text>;
        const mins = Math.floor(Date.now() / 1000 - v);
        const hours = Math.floor(mins / 60);
        const txt = hours > 0 ? `${hours} 小时前` : `${Math.max(0, mins)} 分钟前`;
        return hours >= 24 ? <Tag color="orange">即将过期（{txt}）</Tag> : <Text>{txt}</Text>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 85,
      render: (v: string) => {
        const s = STATUS_LABELS[v] || STATUS_LABELS.paused;
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
    {
      title: '总使用',
      dataIndex: 'use_count',
      width: 70,
      render: (v: number) => <Text>{v ?? 0}</Text>,
    },
    {
      title: '成功',
      dataIndex: 'success_count',
      width: 60,
      render: (v: number) => <Text type="success">{v ?? 0}</Text>,
    },
    {
      title: '失败',
      dataIndex: 'fail_count',
      width: 60,
      render: (v: number) => <Text type="danger">{v ?? 0}</Text>,
    },
    {
      title: '连续失败',
      dataIndex: 'continuous_fail',
      width: 80,
      render: (v: number) => (
        <Text type={v >= (stats?.config.max_continuous_fail || 2) ? 'danger' : undefined}>{v ?? 0}</Text>
      ),
    },
    {
      title: '绑定代理',
      dataIndex: 'proxy',
      width: 180,
      render: (v: { http?: string } | null) => {
        if (!v?.http) return '-';
        const s = v.http.includes('@') ? v.http.split('@')[1] : v.http;
        return <Text style={{ fontSize: 12 }}>{s}</Text>;
      },
    },
    {
      title: '绑定到期',
      dataIndex: 'proxy_expires_at',
      width: 150,
      render: (v: number | null) => (v ? <Text type="secondary">{fmtTime(v)}</Text> : '-'),
    },
    {
      title: '最近错误',
      dataIndex: 'last_error',
      ellipsis: true,
      render: (v: string) => (v ? <Text type="danger" style={{ fontSize: 12 }}>{v}</Text> : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, r: CookiePoolItem) => (
        <Space size={4} wrap>
          {r.status === 'available' ? (
            <Button size="small" icon={<PauseCircleOutlined />} onClick={() => setStatus(r, 'paused')}>暂停</Button>
          ) : (
            <Button size="small" type="primary" ghost icon={<PlayCircleOutlined />} onClick={() => setStatus(r, 'available')}>启用</Button>
          )}
          {r.proxy ? (
            <Button size="small" icon={<DisconnectOutlined />} onClick={() => unbind(r)}>解绑</Button>
          ) : null}
          <Button size="small" icon={<SyncOutlined />} onClick={() => rebind(r)}>重绑</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title="删除该 Cookie？" onConfirm={() => removeCookie(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const proxyColumns = [
    { title: '出口地址', dataIndex: 'label', ellipsis: true },
    {
      title: '来源',
      dataIndex: 'source',
      width: 120,
      render: (v: string) => <Tag>{SOURCE_LABELS[v] || v}</Tag>,
    },
  ];

  const callColumns = [
    {
      title: '时间',
      dataIndex: 'ts_ms',
      width: 160,
      render: (v: number) => <Text type="secondary">{fmtTs(v)}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'job_type',
      width: 100,
      render: (v: string) => <Tag>{JOB_LABELS[v] || v}</Tag>,
    },
    {
      title: '目标',
      dataIndex: 'target',
      ellipsis: true,
      render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: 'Cookie',
      dataIndex: 'cookie_label',
      width: 90,
      render: (v: string, r: CrawlCallRecord) => v || (r.cookie_id ? r.cookie_id.slice(0, 8) : '-'),
    },
    {
      title: '代理出口',
      dataIndex: 'proxy_used',
      width: 170,
      render: (v: string | null) => (v ? <Text style={{ fontSize: 12 }}>{v}</Text> : '-'),
    },
    {
      title: '结果',
      dataIndex: 'result',
      width: 110,
      render: (v: string) => <Tag color={RESULT_COLORS[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '错误',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (v: string | null) => (v ? <Text type="danger" style={{ fontSize: 12 }}>{v}</Text> : '-'),
    },
  ];

  const cfg = stats?.config;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <Title level={5} style={{ margin: 0 }}>Cookie 池</Title>
        <Text type="secondary">
          {stats
            ? `共 ${stats.total} 个 · 可用 ${stats.counts.available} · 冷却 ${stats.counts.cooling} · 失效 ${stats.counts.invalid} · 暂停 ${stats.counts.paused}`
            : '加载中'}
        </Text>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => fetch(false)}>刷新</Button>
        <Button icon={<QrcodeOutlined />} loading={loginLoading} onClick={handleScanLogin}>扫码登录刷新 Cookie</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>添加 Cookie</Button>
      </div>

      {stats && stats.counts.available === 0 && stats.total > 0 && (
        <Alert type="error" showIcon style={{ marginBottom: 12 }}
          message="Cookie 池无可用 Cookie（可能已过期）"
          description="请点右上角「扫码登录刷新 Cookie」扫码补充，或手动添加。" />
      )}

      {cfg && (
        <div style={{ marginBottom: 12, fontSize: 12, color: '#888' }}>
          每小时上限 {cfg.max_use_per_hour} 次 · 连续失败 {cfg.max_continuous_fail} 次冷却 {Math.round(cfg.cooling_seconds / 60)} 分钟 · 总失败 {cfg.max_total_fail} 次淘汰 · 代理 session {Math.round(cfg.proxy_session_seconds / 60)} 分钟 · 代理失败 {cfg.max_proxy_failures} 次解绑
        </div>
      )}

      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={cookieColumns}
        dataSource={cookies}
        pagination={cookies.length > 8 ? { pageSize: 8, showSizeChanger: false } : false}
        style={{ marginBottom: 28 }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <Title level={5} style={{ margin: 0 }}>IP 代理池</Title>
        <Tag color={proxy?.source === 'none' ? 'red' : 'blue'}>{SOURCE_LABELS[proxy?.source || 'none']}</Tag>
        <Text type="secondary">
          {proxy ? `当前 ${proxy.count} 条` : '加载中'}
          {proxy?.tunnel_sids?.length ? ` · sid: ${proxy.tunnel_sids.join(', ')}` : ''}
          {proxy?.tunnel_period_seconds ? ` · 周期 ${proxy.tunnel_period_seconds}s` : ''}
          {proxy?.tunnel_pool ? ` · 池 ${proxy.tunnel_pool}` : ''}
        </Text>
        <Button size="small" icon={<ReloadOutlined />} loading={proxyLoading} onClick={refreshProxy}>刷新代理</Button>
      </div>

      <Table
        rowKey="label"
        size="small"
        loading={proxyLoading}
        columns={proxyColumns}
        dataSource={proxy?.entries || []}
        pagination={false}
        style={{ marginBottom: 28 }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <Title level={5} style={{ margin: 0 }}>最近调用</Title>
        <Text type="secondary">最近 {calls.length} 条 · 每 10 秒自动刷新</Text>
      </div>

      <Table
        rowKey={(r: CrawlCallRecord, i?: number) => `${r.ts_ms}-${i ?? 0}-${r.target}`}
        size="small"
        loading={callsLoading}
        columns={callColumns}
        dataSource={calls}
        pagination={calls.length > 10 ? { pageSize: 10, showSizeChanger: false } : false}
      />

      <Modal
        title="添加 Cookie"
        open={addOpen}
        onOk={addCookie}
        onCancel={() => setAddOpen(false)}
        okText="添加"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={addForm} layout="vertical" initialValues={{ label: '', cookie: '' }}>
          <Form.Item name="label" label="名称">
            <Input placeholder="例如：账号 1" maxLength={40} />
          </Form.Item>
          <Form.Item
            name="cookie"
            label="Cookie"
            rules={[{ required: true, message: '请粘贴完整 Cookie' }]}
          >
            <Input.TextArea rows={6} placeholder="粘贴小红书网页版完整 Cookie" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑 Cookie"
        open={!!editItem}
        onOk={saveEdit}
        onCancel={() => setEditItem(null)}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="label" label="名称">
            <Input maxLength={40} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              options={[
                { value: 'available', label: '可用' },
                { value: 'cooling', label: '冷却' },
                { value: 'invalid', label: '已失效' },
                { value: 'paused', label: '暂停' },
              ]}
            />
          </Form.Item>
          <Form.Item name="cookie" label="Cookie">
            <Input.TextArea rows={6} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
