import { Alert, Card, Col, Empty, Row, Space, Statistic, Table, Tag, Typography } from 'antd';
import { TrophyOutlined } from '@ant-design/icons';
import {
  CartesianGrid, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, Radar, RadarChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import SubscribeButton from './SubscribeButton';

const { Title, Text } = Typography;

const DIMENSION_LABELS: Record<string, string> = {
  seeding_depth: '种草深度',
  verticality: '内容垂直度',
  stable_output: '稳定产出',
  sustained_operation: '持续经营',
  growth_trend: '增长趋势',
};

const CONFIDENCE_TEXT: Record<string, string> = { high: '高', medium: '中', low: '低' };
const CONFIDENCE_COLOR: Record<string, string> = { high: 'green', medium: 'gold', low: 'red' };
const ANOMALY_TEXT: Record<string, string> = {
  fake_engagement: '疑似刷量',
  interaction_inversion: '粉丝互动倒挂',
  stale: '发布停滞',
};

function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return '-';
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: digits });
}

function fmtDate(v: string | null | undefined): string {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function weighted(stats: any): number {
  return (stats?.liked || 0) * 1 + (stats?.collected || 0) * 4 + (stats?.comments || 0) * 5 + (stats?.shared || 0) * 6;
}

export default function UserAnalysisPanel({ user, data, onOpenNote }: {
  user: { user_id?: string; nickname: string; fans: number } | null;
  data: any;
  onOpenNote: (note: any) => void;
}) {
  if (!data) return <Empty style={{ padding: '64px 0' }} description="尚未生成分析结果" />;

  const cov = data.coverage || {};
  const dims = Object.entries(data.dimensions || {}).map(([key, v]: [string, any]) => ({
    key,
    name: DIMENSION_LABELS[key] || key,
    value: Number(v?.score || 0),
    confidence: v?.confidence || 'high',
    detail: v?.detail || {},
  }));
  const timeline = (data.timeline?.items || []).map((it: any) => ({ ...it, label: it.label || it.key }));
  const overall = data.overall;
  const anomalies = data.anomalies || [];
  const insights = data.insights || [];
  const fh = data.follower_history || null;

  const columns = [
    { title: '标题', dataIndex: 'title', key: 'title', width: 240, render: (v: string) => <Text strong style={{ display: 'block', maxWidth: 240 }} ellipsis={{ tooltip: v }}>{v || '无标题'}</Text> },
    { title: '发布时间', dataIndex: 'published_at', key: 'published_at', width: 120, render: (v: string) => fmtDate(v) },
    { title: '类型', dataIndex: 'type', key: 'type', width: 70, render: (v: string) => <Tag>{v === 'video' ? '视频' : '图文'}</Tag> },
    { title: '点赞', dataIndex: ['stats', 'liked'], key: 'liked', width: 80, render: (v: number) => fmtNum(v) },
    { title: '收藏', dataIndex: ['stats', 'collected'], key: 'collected', width: 80, render: (v: number) => fmtNum(v) },
    { title: '评论', dataIndex: ['stats', 'comments'], key: 'comments', width: 80, render: (v: number) => fmtNum(v) },
    { title: '分享', dataIndex: ['stats', 'shared'], key: 'shared', width: 80, render: (v: number) => fmtNum(v) },
    { title: '加权互动', key: 'weighted', width: 90, render: (_: any, r: any) => <Text strong>{fmtNum(weighted(r.stats))}</Text> },
  ];

  const sd = (data.dimensions?.seeding_depth?.detail || {});
  const v = (data.dimensions?.verticality?.detail || {});
  const so = (data.dimensions?.sustained_operation?.detail || {});
  const gt = (data.dimensions?.growth_trend?.detail || {});
  const statCards = [
    { title: '已验证样本', value: cov.fetched_notes, suffix: `/${cov.sample_size || cov.total_notes || 0}`, color: '#1677ff' },
    { title: '覆盖率', value: cov.coverage_rate ? (cov.coverage_rate * 100).toFixed(1) : 0, suffix: '%', color: '#1677ff' },
    { title: '种草深度', value: data.dimensions?.seeding_depth?.score, suffix: '', color: '#eb2f96' },
    { title: '内容垂直度', value: data.dimensions?.verticality?.score, suffix: '', color: '#52c41a' },
    { title: '稳定产出', value: data.dimensions?.stable_output?.score, suffix: '', color: '#fa8c16' },
    { title: '持续经营', value: data.dimensions?.sustained_operation?.score, suffix: '', color: '#722ed1' },
    { title: '增长趋势', value: data.dimensions?.growth_trend?.score, suffix: '', color: '#13c2c2' },
    { title: '篇均收藏率', value: sd.collect_rate_percent, suffix: '%', color: '#f5222d' },
    { title: '美食占比', value: v.food_ratio != null ? (v.food_ratio * 100).toFixed(0) : undefined, suffix: '%', color: '#52c41a' },
    { title: '最新发布距今', value: so.freshness_days, suffix: '天', color: '#fa541c' },
  ];
  if (gt.has_snapshot && gt.growth_rate != null) {
    statCards.push({ title: '涨粉率(月)', value: (gt.growth_rate * 100).toFixed(1), suffix: '%', color: '#13c2c2' });
  }

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', marginBottom: 16, padding: 16, background: '#fff', border: '1px solid #f0f0f0', borderRadius: 8 }}>
        <Space size={16}>
          <div style={{ width: 64, height: 64, borderRadius: 8, background: '#f0f5ff', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#1677ff' }}>
            <TrophyOutlined style={{ fontSize: 28 }} />
          </div>
          <div>
            <Space size={8}>
              <Title level={4} style={{ margin: 0 }}>{user?.nickname || data.nickname || '博主分析'}</Title>
              {user?.user_id ? <SubscribeButton user={{ xhs_user_id: user.user_id, nickname: user.nickname }} showText={false} /> : null}
            </Space>
            <div style={{ marginTop: 4 }}>
              <Text type="secondary">粉丝 {fmtNum(user?.fans || 0)} · 已验证 {cov.fetched_notes || 0}/{cov.sample_size || cov.total_notes || 0} 篇{cov.sample_size && cov.total_notes && cov.sample_size !== cov.total_notes ? `（共 ${cov.total_notes} 篇，抽样分析）` : ''}</Text>
              <Tag color={CONFIDENCE_COLOR[data.confidence] || 'default'} style={{ marginLeft: 8 }}>可信度 {CONFIDENCE_TEXT[data.confidence] || data.confidence}</Tag>
            </div>
          </div>
        </Space>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          {overall ? (
            <>
              <div style={{ fontSize: 40, fontWeight: 700, lineHeight: 1.1, color: '#1677ff' }}>{overall.score}</div>
              <Tag color={overall.level === '卓越' ? 'magenta' : overall.level === '优秀' ? 'gold' : overall.level === '良好' ? 'green' : 'default'} style={{ marginTop: 4 }}>{overall.level}</Tag>
            </>
          ) : (
            <Tag color="red">数据不足，暂不评分</Tag>
          )}
        </div>
      </div>

      {anomalies.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="资格闸门命中"
          description={<ul style={{ margin: 0, paddingLeft: 18 }}>{anomalies.map((a: any, i: number) => <li key={i}>{ANOMALY_TEXT[a.type] || a.type}：{a.detail}</li>)}</ul>}
        />
      )}

      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        {statCards.map((c) => (
          <Col key={c.title} xs={12} sm={8} md={6} lg={4}>
            <Card size="small" styles={{ body: { padding: '12px 16px' } }}>
              <Statistic title={c.title} value={c.value} suffix={c.suffix} valueStyle={{ color: c.color, fontWeight: 600 }} />
            </Card>
          </Col>
        ))}
      </Row>

      {data.decision && (
        <Card size="small" style={{ marginBottom: 12, borderLeft: `4px solid ${recColor(data.decision.recommendation)}` }}>
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Space>
              <Text strong style={{ fontSize: 16 }}>{recLabel(data.decision.recommendation)}</Text>
              {data.stage && (
                <Tag color={stageColor(data.stage.label)}>
                  {data.stage.label}
                  {data.stage.confidence === 'low' ? '（推断）' : ''}
                </Tag>
              )}
              {data.overall_score_suppressed || data.overall?.score_suppressed ? <Tag color="red">已抑制评分</Tag> : null}
            </Space>
            <Text type="secondary">{data.decision.summary}</Text>
            {data.decision.reasons?.length > 0 && (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {data.decision.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            )}
            {data.decision.red_flags?.length > 0 && (
              <Alert type="warning" showIcon message="红旗"
                description={<ul style={{ margin: 0, paddingLeft: 18 }}>{data.decision.red_flags.map((f: any, i: number) => <li key={i}>{f.detail}</li>)}</ul>} />
            )}
          </Space>
        </Card>
      )}

      {insights.length > 0 && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }} message="分析洞察"
          description={<ul style={{ margin: 0, paddingLeft: 18 }}>{insights.map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>} />
      )}

      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col xs={24} xl={14}>
          <Card size="small" title="真实互动趋势" extra={<Text type="secondary" style={{ fontSize: 12 }}>{timeline.length ? '按周' : '暂无时间数据'}</Text>}>
            {timeline.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={timeline} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(value: any, name: any) => [fmtNum(Number(value)), name]} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="likes" name="点赞" stroke="#eb2f96" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="comments" name="评论" stroke="#fa8c16" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="collects" name="收藏" stroke="#722ed1" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="engagement" name="加权互动" stroke="#1677ff" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无时间数据" style={{ padding: 24 }} />}
          </Card>
        </Col>
        <Col xs={24} md={12} xl={10}>
          <Card size="small" title="五维评分" extra={<Text type="secondary" style={{ fontSize: 12 }}>满分 100</Text>}>
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={dims} outerRadius="72%">
                <PolarGrid />
                <PolarAngleAxis dataKey="name" tick={{ fontSize: 11 }} />
                <Radar name="评分" dataKey="value" stroke="#1677ff" fill="#1677ff" fillOpacity={0.35} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
            <Row gutter={[8, 4]}>
              {dims.map((d: any) => (
                <Col span={12} key={d.key} style={{ fontSize: 12 }}>
                  <Space size={6}>
                    <Text type="secondary">{d.name}</Text>
                    <Text strong>{d.value}</Text>
                    {d.confidence === 'low' ? <Tag style={{ fontSize: 10 }}>低置信</Tag> : null}
                  </Space>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>

      {fh?.series?.length >= 2 && (
        <Card size="small" title="平台历史涨粉" style={{ marginBottom: 12 }}
          extra={<Text type="secondary" style={{ fontSize: 12 }}>{fh.points} 个数据点 · {fh.source === 'justoneapi' ? '蒲公英官方数据' : fh.platform_points > 0 ? '官方+本地快照' : '本地快照'}</Text>}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={fh.series.map((p: any) => ({ date: String(p.snapshot_at || '').slice(0, 10), fans: p.fans }))} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value: any, name: any) => [fmtNum(Number(value)), name]} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="fans" name="粉丝数" stroke="#13c2c2" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      <Card size="small" title="全部真实笔记（点击行查看详情）">
        <Table
          rowKey={(r: any) => r.platform_note_id || r.id || Math.random().toString()}
          columns={columns}
          dataSource={data.notes || []}
          size="small"
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          onRow={(r: any) => ({
            onClick: () => { if (r.image_urls?.length || r.cover_url) onOpenNote(r); },
            style: { cursor: r.image_urls?.length || r.cover_url ? 'pointer' : 'default' },
          })}
        />
      </Card>
    </div>
  );
}

function recLabel(r: string): string {
  return { priority: '优先合作', ok: '可合作', caution: '谨慎', not_recommended: '不合作', insufficient_data: '数据不足' }[r] || r;
}
function recColor(r: string): string {
  return { priority: '#52c41a', ok: '#1677ff', caution: '#fa8c16', not_recommended: '#f5222d', insufficient_data: '#8c8c8c' }[r] || '#1677ff';
}
function stageColor(s: string): string {
  return { 冷启动: 'blue', 成长: 'green', 成熟: 'gold', 衰退: 'red' }[s] || 'default';
}

