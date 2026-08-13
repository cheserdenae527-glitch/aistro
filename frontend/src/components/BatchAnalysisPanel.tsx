// frontend/src/components/BatchAnalysisPanel.tsx
// 批量真实分析面板：粘贴博主主页链接/user_id 入队 -> 一键批量发起 -> 实时进度（每博主独立进度条）。
import { useEffect, useRef, useState } from 'react';
import { Button, Card, Input, message, Progress, Space, Tag, Typography } from 'antd';
import { ClearOutlined, DeleteOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { createAnalysisTasksBatch, listAnalysisTasks } from '../services/analysis';

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

interface TaskProgress {
  status: string;
  fetched?: number;
  target?: number;
}

// 每行提取一个 user_id：裸 ID 整行须为纯字母数字；主页链接支持带/不带协议头、带前缀文字。
export function parseUserId(line: string): string {
  const s = line.trim();
  if (!s) return '';
  if (/^[0-9a-zA-Z]+$/.test(s)) return s;
  const m = s.match(/(?:https?:\/\/)?(?:www\.)?xiaohongshu\.com\/user\/profile\/([0-9a-zA-Z]+)/);
  return m ? m[1] : '';
}

// 是否为 xhslink 短链（App 分享默认格式，需展开后才能解析出博主主页）
export function isShortLink(line: string): boolean {
  return /https?:\/\/(?:www\.)?xhslink\.(?:com|cn)\/\S+/i.test(line.trim());
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
  withComments,
}: BatchAnalysisPanelProps) {
  const [pastedText, setPastedText] = useState('');
  const [running, setRunning] = useState(false);
  const [progressMap, setProgressMap] = useState<Record<string, TaskProgress>>({});
  const aliveRef = useRef(true);
  useEffect(() => () => { aliveRef.current = false; }, []);

  const expandShortLink = async (line: string): Promise<string> => {
    try {
      const api = (await import('../services/api')).default;
      const r = await api.post('/notes/unshorten', { url: line.trim() });
      return (r.data?.url || line).trim();
    } catch { return line; }
  };

  const parsePasted = async (): Promise<BatchQueueItem[]> => {
    const seen = new Set<string>();
    const items: BatchQueueItem[] = [];
    for (const line of pastedText.split('\n')) {
      const s = line.trim();
      if (!s) continue;
      let id = parseUserId(s);
      if (!id && isShortLink(s)) {
        const expanded = await expandShortLink(s);
        id = parseUserId(expanded);
      }
      if (id && !seen.has(id)) {
        seen.add(id);
        items.push({ user_id: id, nickname: id, fans: 0 });
      }
    }
    return items;
  };

  const handleAddParsed = async () => {
    const items = await parsePasted();
    if (items.length === 0) {
      message.info('未解析到有效的博主主页链接或 user_id（xhslink 短链会自动展开）');
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
    setProgressMap({});
    try {
      const res = await createAnalysisTasksBatch(
        queue.map((q) => ({ user_id: q.user_id, nickname: q.nickname, fans: q.fans, with_comments: withComments })),
      );
      const next: Record<string, TaskProgress> = {};
      const taskIdByUser = new Map<string, string>();
      const createdTaskIds: string[] = [];
      for (const c of res.created) {
        next[c.xhs_user_id] = { status: '分析中' };
        taskIdByUser.set(c.xhs_user_id, c.task_id);
        createdTaskIds.push(c.task_id);
      }
      for (const r of res.rejected) next[r.xhs_user_id] = { status: '已拒绝：' + r.reason };
      setProgressMap({ ...next });
      if (res.rejected.length > 0) {
        message.warning(`批量发起完成：创建 ${res.created.length} 个任务，${res.rejected.length} 个未通过粗筛`);
      } else {
        message.success(`批量发起完成：已创建 ${res.created.length} 个分析任务`);
      }
      if (Object.keys(next).length === 0) return;
      const allRejected = Object.values(next).every((v) => v.status.startsWith('已拒绝'));
      if (allRejected) return;

      const startTime = Date.now();
      const timeoutMs = 10 * 60 * 1000;
      let consecutiveErrors = 0;
      let terminal = false;
      while (!terminal && Date.now() - startTime < timeoutMs) {
        await sleep(3000);
        if (!aliveRef.current) return;
        try {
          const pollRes = createdTaskIds.length > 0
            ? await listAnalysisTasks({ ids: createdTaskIds })
            : await listAnalysisTasks({ limit: 500 });
          if (!aliveRef.current) return;
          const items = pollRes.items || [];
          const upd: Record<string, TaskProgress> = {};
          let allTerminal = true;
          for (const id of Object.keys(next)) {
            if (next[id].status.startsWith('已拒绝')) { upd[id] = next[id]; continue; }
            const taskId = taskIdByUser.get(id);
            const t = taskId ? items.find((x) => x.id === taskId) : undefined;
            if (!t) { upd[id] = { status: '分析中' }; allTerminal = false; continue; }
            const st = taskStatusText(t.status);
            upd[id] = {
              status: st.text,
              fetched: t.fetched_notes ?? undefined,
              target: t.target_notes || t.total_notes || undefined,
            };
            if (!st.terminal) allTerminal = false;
          }
          setProgressMap({ ...upd });
          consecutiveErrors = 0;
          terminal = allTerminal;
        } catch (err: unknown) {
          consecutiveErrors += 1;
          if (consecutiveErrors >= 3) {
            message.error('批量进度刷新连续失败，已停止轮询：' + errorDetail(err, '未知错误'), 5);
            return;
          }
        }
      }
      if (!terminal) message.warning('批量分析仍在进行（已超过约 10 分钟），可稍后在「博主订阅」页的分析结果中查看最新结果', 5);
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
          placeholder="每行一个小红书博主主页链接或 user_id，如 https://www.xiaohongshu.com/user/profile/xxxxxx、App 分享的 xhslink.com 短链，或 xxxxxx"
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
        <Tag color={withComments ? 'purple' : 'default'} style={{ marginLeft: 8 }}>评论分析：{withComments ? '开' : '关'}</Tag>
        <Text type="secondary" style={{ marginLeft: 8 }}>
          {running ? '正在发起并实时跟踪进度...' : queue.length > 0 ? `队列 ${queue.length} 个博主，将执行真实粗筛+分析` : '队列为空'}
        </Text>
      </div>

      <Card size="small" title={<Title level={5} style={{ margin: 0 }}>实时进度</Title>} style={{ marginTop: 12 }}>
        {Object.keys(progressMap).length === 0 ? (
          <Text type="secondary">暂无进行中的批量分析</Text>
        ) : (
          <div>
            {Object.entries(progressMap).map(([userId, p]) => {
              const q = queue.find((x) => x.user_id === userId);
              const pct = p.target ? Math.min(100, Math.round(((p.fetched || 0) / p.target) * 100)) : (p.status === '分析中' ? 10 : 100);
              return (
                <div key={userId} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0', borderBottom: '1px solid #f5f5f5' }}>
                  <Text strong style={{ width: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q?.nickname || userId}</Text>
                  <div style={{ flex: 1, maxWidth: 360 }}>
                    <Progress percent={pct} size="small" status={p.status === '失败' ? 'exception' : p.status === '完成' ? 'success' : 'active'} />
                  </div>
                  <Text type="secondary" style={{ fontSize: 12, width: 120 }}>
                    {p.status === '完成' ? '完成' : p.status === '失败' ? '失败' : p.target ? `抓取 ${p.fetched || 0}/${p.target}` : '分析中'}
                  </Text>
                  <Tag color={statusColor(p.status)} style={{ minWidth: 60, textAlign: 'center' }}>{p.status.replace(/^已拒绝：/, '已拒绝')}</Tag>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
