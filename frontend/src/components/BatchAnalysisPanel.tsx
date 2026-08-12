// frontend/src/components/BatchAnalysisPanel.tsx
// 批量真实分析面板：粘贴博主主页链接/user_id 入队 -> 一键批量发起 -> 轮询进度 -> 结果进筛选表。
import { useEffect, useRef, useState } from 'react';
import { Button, Card, Input, message, Space, Tag, Typography } from 'antd';
import { ClearOutlined, DeleteOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
import BloggerScreeningPanel from './BloggerScreeningPanel';
import { AnalysisTaskPayload, createAnalysisTasksBatch, listAnalysisTasks, ScreeningRow } from '../services/analysis';

const { Text, Title } = Typography;

export interface BatchQueueItem {
  user_id: string;
  nickname: string;
  fans: number;
}

interface BatchAnalysisPanelProps {
  queue: BatchQueueItem[];
  onRemoveFromQueue: (userId: string) => void;
  onAddFromQueue: (items: BatchQueueItem[]) => void;
  screeningRows: ScreeningRow[];
  screeningLoading: boolean;
  onRefreshScreening: () => void;
  withComments: boolean;
}

const STATUS_COLOR: Record<string, string> = {
  分析中: 'blue',
  完成: 'green',
  失败: 'red',
  已取消: 'default',
};

function statusColor(status: string): string {
  if (status.startsWith('已拒绝')) return 'orange';
  return STATUS_COLOR[status] || 'default';
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

// 每行提取一个 user_id：裸 ID 直接取；主页链接剥掉协议/域名后按规格正则取 user/profile/ 后的 ID。
function parseUserId(line: string): string {
  const s = line.trim();
  if (!s) return '';
  if (/^[0-9a-zA-Z]+$/.test(s)) return s;
  const stripped = s.replace(/^https?:\/\//, '').replace(/^[^/]+\//, '');
  const m = stripped.match(/(?:user\/profile\/)?([0-9a-zA-Z]+)/);
  return m ? m[1] : '';
}

function errorDetail(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e?.response?.data?.detail || e?.message || fallback;
}

function taskStatusText(status: string): { text: string; terminal: boolean } {
  switch (status) {
    case 'success':
    case 'partial':
      return { text: '完成', terminal: true };
    case 'failed':
      return { text: '失败', terminal: true };
    case 'cancelled':
      return { text: '已取消', terminal: true };
    case 'pending':
    case 'running':
      return { text: '分析中', terminal: false };
    default:
      return { text: '分析中', terminal: false };
  }
}

export default function BatchAnalysisPanel({
  queue,
  onRemoveFromQueue,
  onAddFromQueue,
  screeningRows,
  screeningLoading,
  onRefreshScreening,
  withComments,
}: BatchAnalysisPanelProps) {
  const [pastedText, setPastedText] = useState('');
  const [running, setRunning] = useState(false);
  const [statusMap, setStatusMap] = useState<Record<string, string>>({});
  const aliveRef = useRef(true);
  useEffect(() => () => { aliveRef.current = false; }, []);

  const parsePasted = (): BatchQueueItem[] => {
    const seen = new Set<string>();
    const items: BatchQueueItem[] = [];
    for (const line of pastedText.split('\n')) {
      const id = parseUserId(line);
      if (id && !seen.has(id)) {
        seen.add(id);
        items.push({ user_id: id, nickname: id, fans: 0 });
      }
    }
    return items;
  };

  const handleAddParsed = () => {
    const items = parsePasted();
    if (items.length === 0) {
      message.info('未解析到有效的博主主页链接或 user_id');
      return;
    }
    onAddFromQueue(items);
    setPastedText('');
  };

  const handleClearQueue = () => {
    setPastedText('');
    queue.forEach((q) => onRemoveFromQueue(q.user_id));
    message.success('已清空批量分析队列');
  };

  const handleStart = async () => {
    if (running || queue.length === 0) return;
    setRunning(true);
    setStatusMap({});
    try {
      const res = await createAnalysisTasksBatch(
        queue.map((q) => ({ user_id: q.user_id, nickname: q.nickname, fans: q.fans, with_comments: withComments })),
      );
      const next: Record<string, string> = {};
      for (const c of res.created) next[c.xhs_user_id] = '分析中';
      for (const r of res.rejected) next[r.xhs_user_id] = '已拒绝：' + r.reason;
      setStatusMap({ ...next });
      if (res.rejected.length > 0) {
        message.warning(`批量发起完成：创建 ${res.created.length} 个任务，${res.rejected.length} 个未通过粗筛`);
      } else {
        message.success(`批量发起完成：已创建 ${res.created.length} 个分析任务`);
      }
      if (Object.keys(next).length === 0) return;
      // 全部被粗筛拒绝则无需轮询
      const allRejected = Object.values(next).every((v) => v.startsWith('已拒绝'));
      if (allRejected) return;

      const startTime = Date.now();
      const timeoutMs = 3 * 60 * 1000;
      let terminal = false;
      while (!terminal && Date.now() - startTime < timeoutMs) {
        await sleep(3000);
        if (!aliveRef.current) return;
        try {
          const pollRes = await listAnalysisTasks({ limit: 200 });
          const items = pollRes.items || [];
          // 每个 user_id 取最新一条任务（按完成时间）
          const latest = new Map<string, AnalysisTaskPayload>();
          for (const t of items) {
            const prev = latest.get(t.xhs_user_id);
            if (!prev || (t.finished_at || '') > (prev.finished_at || '')) latest.set(t.xhs_user_id, t);
          }
          const upd: Record<string, string> = {};
          let allTerminal = true;
          for (const id of Object.keys(next)) {
            if (next[id].startsWith('已拒绝')) { upd[id] = next[id]; continue; }
            const t = latest.get(id);
            if (!t) { upd[id] = '分析中'; allTerminal = false; continue; }
            const st = taskStatusText(t.status);
            upd[id] = st.text;
            if (!st.terminal) allTerminal = false;
          }
          setStatusMap({ ...upd });
          onRefreshScreening();
          terminal = allTerminal;
        } catch (err: unknown) {
          message.error('批量进度刷新失败：' + errorDetail(err, '未知错误'), 5);
          break;
        }
      }
      if (!terminal) message.warning('批量分析仍在进行（已超过约 3 分钟），请稍后在筛选表查看最新结果', 5);
    } catch (err: unknown) {
      message.error('批量发起失败：' + errorDetail(err, '未知错误'), 6);
    } finally {
      if (aliveRef.current) setRunning(false);
    }
  };

  return (
    <div>
      <Card size="small" title={<Title level={5} style={{ margin: 0 }}>批量发起</Title>}>
        <Input.TextArea
          rows={4}
          value={pastedText}
          onChange={(e) => setPastedText(e.target.value)}
          placeholder="每行一个小红书博主主页链接或 user_id，如 https://www.xiaohongshu.com/user/profile/xxxxxx 或 xxxxxx"
        />
        <Space style={{ marginTop: 8 }}>
          <Button icon={<PlusOutlined />} onClick={handleAddParsed}>加入队列</Button>
          <Button icon={<ClearOutlined />} onClick={handleClearQueue}>清空队列</Button>
          <Text type="secondary">也可在「搜索博主」结果卡片点击「加入批量分析」</Text>
        </Space>
      </Card>

      <Card size="small" title={<Title level={5} style={{ margin: 0 }}>批量队列（{queue.length}）</Title>} style={{ marginTop: 12 }}>
        {queue.length === 0 ? (
          <Text type="secondary">队列为空：粘贴博主主页链接/user_id，或从「搜索博主」结果加入</Text>
        ) : (
          <div>
            {queue.map((q) => (
              <div key={q.user_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #f5f5f5' }}>
                <Space>
                  <Text strong>{q.nickname || q.user_id}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>ID: {q.user_id}</Text>
                  {q.fans > 0 && <Text type="secondary" style={{ fontSize: 12 }}>粉丝 {q.fans}</Text>}
                </Space>
                <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => onRemoveFromQueue(q.user_id)}>移除</Button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div style={{ marginTop: 12 }}>
        <Button type="primary" icon={<PlayCircleOutlined />} loading={running} disabled={running || queue.length === 0} onClick={handleStart}>
          开始批量分析
        </Button>
        <Text type="secondary" style={{ marginLeft: 8 }}>
          {running ? '正在发起并轮询进度...' : queue.length > 0 ? `队列 ${queue.length} 个博主，将执行真实粗筛+分析` : '队列为空'}
        </Text>
      </div>

      <Card size="small" title={<Title level={5} style={{ margin: 0 }}>分析进度</Title>} style={{ marginTop: 12 }}>
        {Object.keys(statusMap).length === 0 ? (
          <Text type="secondary">暂无进行中的批量分析</Text>
        ) : (
          <Space wrap>
            {Object.entries(statusMap).map(([userId, status]) => {
              const q = queue.find((x) => x.user_id === userId);
              return (
                <Tag key={userId} color={statusColor(status)}>
                  {q?.nickname || userId}：{status}
                </Tag>
              );
            })}
          </Space>
        )}
      </Card>

      <div style={{ marginTop: 12 }}>
        <BloggerScreeningPanel rows={screeningRows} loading={screeningLoading} onRefresh={onRefreshScreening} />
      </div>
    </div>
  );
}
