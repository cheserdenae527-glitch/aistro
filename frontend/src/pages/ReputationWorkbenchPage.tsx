import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  DatePicker,
  Drawer,
  Input,
  List,
  message,
  Pagination,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { TableProps } from "antd";
import {
  ArrowLeftOutlined,
  AuditOutlined,
  CheckOutlined,
  CommentOutlined,
  CopyOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  reputationService,
  type AlertReason,
  type ReplyStatus,
  type Review,
  type ReviewFilters,
  type ReputationSummary,
} from "../services/reputation";
import { showApiError } from "../utils/errors";
import {
  buildReviewParams,
  MAX_BATCH_ANALYZE,
  replyStatusMeta,
  sentimentMeta,
  toggleSelection,
} from "../utils/reputation";

const { Title, Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;

const REPLY_STATUS_OPTIONS: { label: string; value: ReplyStatus }[] = [
  { label: "未回复", value: "unreplied" },
  { label: "AI 草稿", value: "ai_replied" },
  { label: "已回复", value: "manual_replied" },
];

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  return dayjs(value).format("YYYY-MM-DD HH:mm");
}

function sentimentTag(sentiment: Review["sentiment"]) {
  const meta = sentimentMeta(sentiment);
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

function replyStatusTag(status: ReplyStatus | null) {
  const meta = replyStatusMeta(status);
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

function alertReasonView(reason: AlertReason | null) {
  if (!reason) return <Text type="secondary">—</Text>;
  const typeColor = reason.type === "both" ? "volcano" : reason.type === "keyword" ? "orange" : "red";
  return (
    <Space size={4} wrap>
      <Tag color={typeColor}>{reason.type === "both" ? "双路径" : reason.type === "keyword" ? "关键词" : "负面情感"}</Tag>
      {reason.keywords.map((kw) => (
        <Tag key={kw}>{kw}</Tag>
      ))}
      {reason.sentiment && sentimentTag(reason.sentiment)}
    </Space>
  );
}

interface NoteCardProps {
  review: Review;
  expanded: boolean;
  comments: Review[];
  commentsLoading: boolean;
  selected: boolean;
  syncing: boolean;
  onSelect: () => void;
  onExpand: () => void;
  onSyncComments: () => void;
}

function NoteCardView({
  review,
  expanded,
  comments,
  commentsLoading,
  selected,
  syncing,
  onSelect,
  onExpand,
  onSyncComments,
}: NoteCardProps) {
  const stats = review.interact_stats || {};
  return (
    <Card size="small" style={{ marginBottom: 10 }} data-testid="note-card">
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <Checkbox checked={selected} onChange={onSelect} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", gap: 8, justifyContent: "space-between" }}>
            <Text strong ellipsis style={{ flex: 1, minWidth: 0 }}>
              {review.note_title || "未命名笔记"}
            </Text>
            {review.alert_status === "triggered" && <Tag color="red">差评预警</Tag>}
          </div>
          <Paragraph
            type="secondary"
            style={{ display: "block", fontSize: 12, marginTop: 2, marginBottom: 0 }}
            ellipsis={{ rows: 2 }}
          >
            {review.content || "无正文"}
          </Paragraph>
          <Space size={12} wrap style={{ marginTop: 6, fontSize: 12 }}>
            <Text type="secondary">{review.reviewer_name || "匿名"}</Text>
            <Text type="secondary">赞 {stats.liked ?? 0}</Text>
            <Text type="secondary">藏 {stats.collected ?? 0}</Text>
            <Text type="secondary">评 {stats.comments ?? 0}</Text>
            <Text type="secondary">转 {stats.shared ?? 0}</Text>
            {sentimentTag(review.sentiment)}
          </Space>
          <Space wrap style={{ marginTop: 8 }}>
            <Button size="small" icon={<CommentOutlined />} onClick={onExpand}>
              {expanded ? "收起评论" : "查看评论"}
            </Button>
            <Button
              size="small"
              icon={<SyncOutlined />}
              loading={syncing}
              onClick={onSyncComments}
            >
              同步评论
            </Button>
          </Space>
        </div>
      </div>
      {expanded && (
        <div style={{ marginTop: 10, borderTop: "1px solid #f0f0f0", paddingTop: 10 }}>
          {commentsLoading ? (
            <div style={{ textAlign: "center", padding: 16 }}>
              <Spin size="small" />
            </div>
          ) : comments.length === 0 ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              暂无评论，可先同步评论
            </Text>
          ) : (
            comments.map((comment) => (
              <CommentRowView key={comment.id} review={comment} />
            ))
          )}
        </div>
      )}
    </Card>
  );
}

interface CommentRowProps {
  review: Review;
  selected?: boolean;
  onSelect?: () => void;
  onOpenReply?: (review: Review) => void;
}

function CommentRowView({
  review,
  selected = false,
  onSelect,
  onOpenReply,
}: CommentRowProps) {
  return (
    <Card size="small" style={{ marginBottom: 10 }} data-testid="comment-row">
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        {onSelect && <Checkbox checked={selected} onChange={onSelect} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <Space size={8} wrap>
            <Text strong style={{ fontSize: 13 }}>{review.reviewer_name || "匿名用户"}</Text>
            {sentimentTag(review.sentiment)}
            {replyStatusTag(review.reply_status)}
            {review.alert_status === "triggered" && <Tag color="red">差评预警</Tag>}
          </Space>
          <div style={{ marginTop: 4, fontSize: 13, lineHeight: 1.6 }}>{review.content || "—"}</div>
          {onOpenReply && (
            <Space wrap style={{ marginTop: 8 }}>
              <Tooltip title="生成 AI 回复草稿">
                <Button
                  size="small"
                  icon={<ThunderboltOutlined />}
                  onClick={() => onOpenReply(review)}
                >
                  AI 回复
                </Button>
              </Tooltip>
              <Button
                size="small"
                icon={<CommentOutlined />}
                onClick={() => onOpenReply(review)}
              >
                {review.reply_status === "manual_replied" ? "编辑回复" : "回复"}
              </Button>
            </Space>
          )}
        </div>
      </div>
    </Card>
  );
}

function SummaryCards({ summary }: { summary: ReputationSummary | null }) {
  const cards = [
    { label: "笔记数", value: summary?.note_count ?? 0, color: "#1677ff" },
    { label: "评论数", value: summary?.comment_count ?? 0, color: "#13c2c2" },
    { label: "未回复", value: summary?.unreplied_count ?? 0, color: "#faad14" },
    { label: "差评预警", value: summary?.alert_count ?? 0, color: "#ff4d4f" },
  ];
  const sentiment = summary?.sentiment_counts || {};
  return (
    <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
      {cards.map((card) => (
        <Col xs={12} sm={6} md={4} key={card.label}>
          <Card size="small">
            <Text type="secondary" style={{ fontSize: 12 }}>{card.label}</Text>
            <div style={{ fontSize: 24, fontWeight: 600, color: card.color }}>
              {card.value}
            </div>
          </Card>
        </Col>
      ))}
      <Col xs={24} sm={12} md={8}>
        <Card size="small">
          <Text type="secondary" style={{ fontSize: 12 }}>情感分布</Text>
          <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
            <Text style={{ color: "#389e0d" }}>正面 {sentiment.positive ?? 0}</Text>
            <Text style={{ color: "#1677ff" }}>中性 {sentiment.neutral ?? 0}</Text>
            <Text style={{ color: "#d4380d" }}>负面 {sentiment.negative ?? 0}</Text>
            <Text type="secondary">未分析 {sentiment.unanalyzed ?? 0}</Text>
          </div>
        </Card>
      </Col>
    </Row>
  );
}

export default function ReputationWorkbenchPage() {
  const { shop_id } = useParams<{ shop_id: string }>();
  const shopId = shop_id!;
  const navigate = useNavigate();
  const started = useRef(false);

  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<ReputationSummary | null>(null);
  const [reviews, setReviews] = useState({ items: [] as Review[], total: 0 });
  const [alerts, setAlerts] = useState<Review[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filters, setFilters] = useState<ReviewFilters>({});

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeFailed, setAnalyzeFailed] = useState<string[]>([]);

  const [expandedNotes, setExpandedNotes] = useState<Set<string>>(new Set());
  const [commentsByNote, setCommentsByNote] = useState<Record<string, Review[]>>({});
  const [commentsLoading, setCommentsLoading] = useState<Set<string>>(new Set());
  const [syncingCommentsId, setSyncingCommentsId] = useState<string | null>(null);

  const [syncKeyword, setSyncKeyword] = useState("");
  const [syncLimit, setSyncLimit] = useState(20);
  const [syncingNotes, setSyncingNotes] = useState(false);

  const [replyTarget, setReplyTarget] = useState<Review | null>(null);
  const [draft, setDraft] = useState("");
  const [aiReplyLoading, setAiReplyLoading] = useState(false);
  const [submittingReply, setSubmittingReply] = useState(false);

  const loadReviews = useCallback(async () => {
    try {
      const params = buildReviewParams(filters, page, pageSize);
      const res = await reputationService.listReviews(shopId, params);
      setReviews({ items: res.data.items, total: res.data.total });
    } catch (e) {
      showApiError(e);
    }
  }, [shopId, filters, page, pageSize]);

  const loadSummary = useCallback(async () => {
    try {
      const res = await reputationService.getSummary(shopId);
      setSummary(res.data);
    } catch (e) {
      showApiError(e);
    }
  }, [shopId]);

  const loadAlerts = useCallback(async () => {
    try {
      const res = await reputationService.listAlerts(shopId);
      setAlerts(res.data);
    } catch (e) {
      showApiError(e);
    }
  }, [shopId]);

  const reloadAll = useCallback(async () => {
    await Promise.all([loadReviews(), loadSummary(), loadAlerts()]);
  }, [loadReviews, loadSummary, loadAlerts]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      await reloadAll();
      setLoading(false);
    })();
  }, [reloadAll]);

  const updateFilter = (patch: Partial<ReviewFilters>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
    setPage(1);
  };

  const handleSyncNotes = async () => {
    if (!syncKeyword.trim()) {
      message.warning("请输入同步关键词");
      return;
    }
    setSyncingNotes(true);
    try {
      const res = await reputationService.syncNotes(shopId, syncKeyword.trim(), syncLimit);
      message.success(`同步完成：新增 ${res.data.created} 条，跳过 ${res.data.skipped} 条`);
      setSyncKeyword("");
      await reloadAll();
    } catch (e) {
      if ((e as { response?: { status?: number } }).response?.status === 429) {
        message.warning("操作频繁，请 60 秒后重试");
      } else {
        showApiError(e);
      }
    } finally {
      setSyncingNotes(false);
    }
  };

  const loadNoteComments = useCallback(
    async (reviewId: string) => {
      setCommentsLoading((prev) => new Set(prev).add(reviewId));
      try {
        const res = await reputationService.listReviews(shopId, {
          parent_review_id: reviewId,
          size: 100,
        });
        setCommentsByNote((prev) => ({ ...prev, [reviewId]: res.data.items }));
      } catch (e) {
        showApiError(e);
      } finally {
        setCommentsLoading((prev) => {
          const next = new Set(prev);
          next.delete(reviewId);
          return next;
        });
      }
    },
    [shopId]
  );

  const toggleNote = (review: Review) => {
    setExpandedNotes((prev) => {
      const next = new Set(prev);
      if (next.has(review.id)) {
        next.delete(review.id);
      } else {
        next.add(review.id);
        if (!commentsByNote[review.id]) {
          loadNoteComments(review.id);
        }
      }
      return next;
    });
  };

  const handleSyncComments = async (review: Review) => {
    setSyncingCommentsId(review.id);
    try {
      const res = await reputationService.syncComments(shopId, review.id);
      message.success(`评论同步完成：新增 ${res.data.created} 条，跳过 ${res.data.skipped} 条`);
      await loadNoteComments(review.id);
      await loadReviews();
      await loadAlerts();
      await loadSummary();
    } catch (e) {
      if ((e as { response?: { status?: number } }).response?.status === 429) {
        message.warning("操作频繁，请 60 秒后重试");
      } else {
        showApiError(e);
      }
    } finally {
      setSyncingCommentsId(null);
    }
  };

  const handleToggleSelect = (id: string) => {
    const result = toggleSelection(selectedIds, id);
    if (result.rejected) {
      message.warning(`单次最多选择 ${MAX_BATCH_ANALYZE} 条`);
      return;
    }
    setSelectedIds(result.ids);
  };

  const handleBatchAnalyze = async (ids?: string[]) => {
    const target = ids ?? selectedIds;
    if (target.length === 0) return;
    setAnalyzing(true);
    try {
      const res = await reputationService.batchAnalyze(shopId, target);
      setAnalyzeFailed(res.data.failed);
      if (res.data.failed.length > 0) {
        message.warning(`分析完成：成功 ${res.data.success_count} 条，失败 ${res.data.failed_count} 条`);
      } else {
        message.success(`分析完成：${res.data.success_count} 条全部成功`);
      }
      if (!ids) setSelectedIds([]);
      await reloadAll();
    } catch (e) {
      if ((e as { response?: { status?: number } }).response?.status === 429) {
        message.warning("操作频繁，请 30 秒后重试");
      } else {
        showApiError(e);
      }
    } finally {
      setAnalyzing(false);
    }
  };

  const openReply = (review: Review) => {
    setReplyTarget(review);
    setDraft(review.reply_content || review.ai_reply || "");
  };

  const handleAiReply = async () => {
    if (!replyTarget) return;
    setAiReplyLoading(true);
    try {
      const res = await reputationService.aiReply(shopId, replyTarget.id);
      setDraft(res.data.ai_reply);
      setReplyTarget((prev) => (prev ? { ...prev, ai_reply: res.data.ai_reply, reply_status: res.data.reply_status } : prev));
      message.success("AI 草稿已生成");
    } catch (e) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 429) {
        message.warning("操作频繁，请 20 秒后重试");
      } else if (err.response?.status === 422) {
        message.error(err.response.data?.detail || "内容包含敏感词，请重新生成");
      } else {
        showApiError(e);
      }
    } finally {
      setAiReplyLoading(false);
    }
  };

  const handleCopyDraft = async () => {
    if (!draft.trim()) return;
    try {
      await navigator.clipboard.writeText(draft);
      message.success("已复制到剪贴板");
    } catch {
      message.error("复制失败");
    }
  };

  const handleSubmitReply = async () => {
    if (!replyTarget) return;
    if (!draft.trim()) {
      message.warning("回复内容不能为空");
      return;
    }
    setSubmittingReply(true);
    try {
      await reputationService.submitReply(shopId, replyTarget.id, draft.trim());
      message.success("已标记为已回复");
      setReplyTarget(null);
      await reloadAll();
    } catch (e) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      if (err.response?.status === 422) {
        message.error(err.response.data?.detail || "内容包含敏感词");
      } else {
        showApiError(e);
      }
    } finally {
      setSubmittingReply(false);
    }
  };

  const handleAck = async (review: Review) => {
    try {
      await reputationService.ackAlert(shopId, review.id);
      message.success("已标记处理");
      await loadAlerts();
      await loadSummary();
    } catch (e) {
      showApiError(e);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  const alertColumns: TableProps<Review>["columns"] = [
    {
      title: "内容",
      dataIndex: "content",
      key: "content",
      ellipsis: true,
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Text style={{ fontSize: 13 }}>
            {row.review_type === "note" ? row.note_title || "笔记" : row.content || "—"}
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{row.reviewer_name || "匿名"}</Text>
        </Space>
      ),
    },
    {
      title: "触发原因",
      key: "reason",
      width: 260,
      render: (_, row) => alertReasonView(row.alert_reason),
    },
    {
      title: "时间",
      dataIndex: "reviewed_at",
      key: "reviewed_at",
      width: 150,
      render: (value: string | null) => formatTime(value || null),
    },
    {
      title: "操作",
      key: "action",
      width: 190,
      render: (_, row) => (
        <Space wrap>
          {row.review_type === "comment" && (
            <Button size="small" icon={<CommentOutlined />} onClick={() => openReply(row)}>
              回复
            </Button>
          )}
          <Button
            size="small"
            type="primary"
            ghost
            icon={<CheckOutlined />}
            onClick={() => handleAck(row)}
          >
            标记处理
          </Button>
        </Space>
      ),
    },
  ];

  const tabItems = [
    {
      key: "reviews",
      label: "评价列表",
      children: (
        <div>
          <Card size="small" style={{ marginBottom: 12 }}>
            <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
              <Space wrap>
                <Input
                  placeholder="同步关键词"
                  value={syncKeyword}
                  maxLength={100}
                  style={{ width: 180 }}
                  onChange={(e) => setSyncKeyword(e.target.value)}
                  onPressEnter={handleSyncNotes}
                />
                <Select
                  value={syncLimit}
                  style={{ width: 90 }}
                  options={[10, 20, 30, 50].map((n) => ({ label: `${n} 条`, value: n }))}
                  onChange={setSyncLimit}
                />
                <Button
                  type="primary"
                  icon={<SyncOutlined />}
                  loading={syncingNotes}
                  onClick={handleSyncNotes}
                >
                  同步笔记
                </Button>
              </Space>
              <Space wrap>
                <Select
                  allowClear
                  placeholder="类型"
                  style={{ width: 110 }}
                  value={filters.review_type}
                  onChange={(v) => updateFilter({ review_type: v })}
                  options={[
                    { label: "笔记", value: "note" },
                    { label: "评论", value: "comment" },
                    { label: "平台评价", value: "rating_review" },
                  ]}
                />
                <Select
                  allowClear
                  placeholder="情感"
                  style={{ width: 100 }}
                  value={filters.sentiment}
                  onChange={(v) => updateFilter({ sentiment: v })}
                  options={[
                    { label: "正面", value: "positive" },
                    { label: "中性", value: "neutral" },
                    { label: "负面", value: "negative" },
                  ]}
                />
                <Select
                  allowClear
                  placeholder="回复状态"
                  style={{ width: 110 }}
                  value={filters.reply_status}
                  onChange={(v) => updateFilter({ reply_status: v })}
                  options={REPLY_STATUS_OPTIONS}
                />
                <Select
                  allowClear
                  placeholder="预警状态"
                  style={{ width: 110 }}
                  value={filters.alert_status}
                  onChange={(v) => updateFilter({ alert_status: v })}
                  options={[
                    { label: "未触发", value: "none" },
                    { label: "已触发", value: "triggered" },
                    { label: "已处理", value: "acknowledged" },
                  ]}
                />
                <Input
                  placeholder="关键词"
                  allowClear
                  style={{ width: 150 }}
                  value={filters.keyword}
                  onChange={(e) => updateFilter({ keyword: e.target.value })}
                  onPressEnter={() => loadReviews()}
                />
                <RangePicker
                  value={
                    filters.date_from && filters.date_to
                      ? [dayjs(filters.date_from), dayjs(filters.date_to)]
                      : null
                  }
                  onChange={(dates) =>
                    updateFilter({
                      date_from: dates?.[0]?.startOf("day").toISOString(),
                      date_to: dates?.[1]?.endOf("day").toISOString(),
                    })
                  }
                />
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => {
                    setFilters({});
                    setPage(1);
                  }}
                >
                  重置
                </Button>
              </Space>
            </Space>
          </Card>

          <Card size="small" style={{ marginBottom: 12 }}>
            <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
              <Space>
                <Checkbox
                  checked={reviews.items.length > 0 && selectedIds.length === reviews.items.length}
                  indeterminate={
                    selectedIds.length > 0 && selectedIds.length < reviews.items.length
                  }
                  onChange={(e) =>
                    setSelectedIds(
                      e.target.checked
                        ? reviews.items.slice(0, MAX_BATCH_ANALYZE).map((item) => item.id)
                        : []
                    )
                  }
                >
                  已选 {selectedIds.length} / {MAX_BATCH_ANALYZE}
                </Checkbox>
              </Space>
              <Button
                type="primary"
                icon={<ExperimentOutlined />}
                loading={analyzing}
                disabled={selectedIds.length === 0}
                onClick={() => handleBatchAnalyze()}
              >
                批量分析
              </Button>
            </Space>
            {analyzeFailed.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 10 }}
                message={`${analyzeFailed.length} 条分析失败，可重试`}
                action={
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    loading={analyzing}
                    onClick={() => handleBatchAnalyze(analyzeFailed)}
                  >
                    重试
                  </Button>
                }
              />
            )}
          </Card>

          <List
            dataSource={reviews.items}
            locale={{ emptyText: "暂无评价数据，先同步笔记" }}
            renderItem={(review) =>
              review.review_type === "note" ? (
                <NoteCardView
                  review={review}
                  expanded={expandedNotes.has(review.id)}
                  comments={commentsByNote[review.id] || []}
                  commentsLoading={commentsLoading.has(review.id)}
                  selected={selectedIds.includes(review.id)}
                  syncing={syncingCommentsId === review.id}
                  onSelect={() => handleToggleSelect(review.id)}
                  onExpand={() => toggleNote(review)}
                  onSyncComments={() => handleSyncComments(review)}
                />
              ) : review.review_type === "comment" ? (
                <CommentRowView
                  review={review}
                  selected={selectedIds.includes(review.id)}
                  onSelect={() => handleToggleSelect(review.id)}
                  onOpenReply={openReply}
                />
              ) : (
                <CommentRowView
                  review={review}
                  selected={selectedIds.includes(review.id)}
                  onSelect={() => handleToggleSelect(review.id)}
                  onOpenReply={openReply}
                />
              )
            }
          />
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={reviews.total}
              showSizeChanger
              pageSizeOptions={[10, 20, 50, 100]}
              onChange={(p, ps) => {
                setPage(p);
                setPageSize(ps);
              }}
            />
          </div>
        </div>
      ),
    },
    {
      key: "alerts",
      label: `差评预警${alerts.length > 0 ? ` (${alerts.length})` : ""}`,
      children: (
        <Table<Review>
          rowKey="id"
          columns={alertColumns}
          dataSource={alerts}
          pagination={false}
          locale={{ emptyText: "暂无差评预警" }}
        />
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12 }} align="center">
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/reputation")}>
          返回门店
        </Button>
        <Title level={4} style={{ marginBottom: 0 }}>
          口碑管理
        </Title>
        <AuditOutlined style={{ color: "#1677ff" }} />
      </Space>

      <SummaryCards summary={summary} />

      <Tabs defaultActiveKey="reviews" items={tabItems} />

      <Drawer
        title={replyTarget ? `回复评论 — ${replyTarget.reviewer_name || "匿名用户"}` : "回复评论"}
        width={480}
        open={!!replyTarget}
        onClose={() => setReplyTarget(null)}
        extra={
          <Space>
            <Button icon={<CopyOutlined />} onClick={handleCopyDraft}>
              复制
            </Button>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              loading={submittingReply}
              disabled={!draft.trim()}
              onClick={handleSubmitReply}
            >
              标记已回复
            </Button>
          </Space>
        }
      >
        {replyTarget && (
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            <Card size="small">
              <Space direction="vertical" size={4}>
                <Space wrap>
                  {sentimentTag(replyTarget.sentiment)}
                  {replyStatusTag(replyTarget.reply_status)}
                </Space>
                <Text style={{ lineHeight: 1.6 }}>{replyTarget.content || "—"}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {formatTime(replyTarget.reviewed_at)}
                </Text>
              </Space>
            </Card>
            <Button
              icon={<ThunderboltOutlined />}
              loading={aiReplyLoading}
              onClick={handleAiReply}
            >
              生成 AI 草稿
            </Button>
            <Input.TextArea
              rows={6}
              value={draft}
              maxLength={2000}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="编辑回复内容，确认后复制到小红书粘贴"
            />
          </Space>
        )}
      </Drawer>
    </div>
  );
}
