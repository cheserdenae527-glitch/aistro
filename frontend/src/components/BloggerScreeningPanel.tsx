// frontend/src/components/BloggerScreeningPanel.tsx
import { useState } from 'react';
import { Button, Card, InputNumber, Space, Table, Tag, Typography } from 'antd';
import { ScreeningRow } from '../services/analysis';

const { Title, Text } = Typography;

const REC_TAG: Record<string, { color: string; label: string }> = {
  priority: { color: 'green', label: '优先合作' },
  ok: { color: 'blue', label: '可合作' },
  caution: { color: 'orange', label: '谨慎' },
  not_recommended: { color: 'red', label: '不合作' },
  insufficient_data: { color: 'default', label: '数据不足' },
};

export default function BloggerScreeningPanel({ rows, loading, onRefresh }: {
  rows: ScreeningRow[];
  loading: boolean;
  onRefresh: () => void;
}) {
  const [minScore, setMinScore] = useState<number | null>(0);
  const [minFood, setMinFood] = useState<number | null>(0);
  const [minFans, setMinFans] = useState<number | null>(0);

  const filtered = rows
    .filter((r): r is ScreeningRow & { overall_score: number } =>
      // 闸门命中直接排除
      !r.score_suppressed && r.overall_score != null
      && (minScore == null || r.overall_score >= minScore)
      && (minFood == null || (r.food_ratio ?? 0) * 100 >= minFood)
      && (minFans == null || r.fans >= minFans))
    .sort((a, b) => b.overall_score - a.overall_score);

  const columns = [
    { title: '昵称', dataIndex: 'nickname', key: 'nickname', width: 180, render: (v: string) => v || <Text type="secondary">未命名</Text> },
    { title: '粉丝数', dataIndex: 'fans', key: 'fans', width: 100, render: (v: number) => v.toLocaleString('zh-CN') },
    { title: '总分', dataIndex: 'overall_score', key: 'overall_score', width: 80, render: (v: number | null) => v ?? '-' },
    { title: '等级', dataIndex: 'level', key: 'level', width: 80 },
    { title: '建议', dataIndex: 'recommendation', key: 'recommendation', width: 100,
      render: (v: string) => { const t = REC_TAG[v] || { color: 'default', label: v }; return <Tag color={t.color}>{t.label}</Tag>; } },
    { title: '阶段', dataIndex: 'stage_label', key: 'stage_label', width: 110,
      render: (v: string, r: ScreeningRow) => <Tag>{v}{r.stage_confidence === 'low' ? '（推断）' : ''}</Tag> },
    { title: '收藏率', dataIndex: 'collect_rate', key: 'collect_rate', width: 90, render: (v: number | null) => v != null ? `${v}%` : '-' },
    { title: '美食占比', dataIndex: 'food_ratio', key: 'food_ratio', width: 90, render: (v: number | null) => v != null ? `${(v * 100).toFixed(0)}%` : '-' },
    { title: '红旗', dataIndex: 'red_flags', key: 'red_flags', render: (v: string[]) => v?.length ? v.map((f, i) => <Tag color="red" key={i}>{f}</Tag>) : <Text type="secondary">无</Text> },
  ];

  return (
    <Card size="small" title={<Title level={5} style={{ margin: 0 }}>博主批量筛选</Title>}
      extra={<Space>
        <InputNumber placeholder="总分≥" min={0} max={100} value={minScore} onChange={(v) => setMinScore(v ?? 0)} style={{ width: 90 }} />
        <InputNumber placeholder="美食%≥" min={0} max={100} value={minFood} onChange={(v) => setMinFood(v ?? 0)} style={{ width: 90 }} />
        <InputNumber placeholder="粉丝≥" min={0} value={minFans} onChange={(v) => setMinFans(v ?? 0)} style={{ width: 110 }} />
        <Button type="primary" onClick={onRefresh} loading={loading}>刷新</Button>
      </Space>}>
      <Table rowKey={(r) => r.user_id} columns={columns} dataSource={filtered} size="small"
        loading={loading}
        locale={{ emptyText: rows.length === 0 ? '暂无分析数据（先运行博主分析）' : '没有符合筛选条件的候选（含被闸门排除的账号）' }}
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 个候选` }} />
      <Text type="secondary">说明：被闸门命中（score 为空）的账号已排除出正常筛选；「优先合作」需账号已有 ≥2 次涨粉快照。</Text>
    </Card>
  );
}
