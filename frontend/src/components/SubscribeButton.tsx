import { useEffect, useState } from 'react';
import { Button, message, Popconfirm } from 'antd';
import { BellOutlined, CheckOutlined, PlusOutlined } from '@ant-design/icons';
import { subService, type SubStatus } from '../services/subscriptions';
import { getSubStatus, invalidateSubStatus } from '../services/subStatusCache';

export default function SubscribeButton({ user, size = 'small', showText = true }: {
  user: { xhs_user_id: string; nickname?: string; avatar?: string };
  size?: 'small' | 'middle';
  showText?: boolean;
}) {
  const [status, setStatus] = useState<SubStatus | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user.xhs_user_id) return;
    let active = true;
    getSubStatus(user.xhs_user_id).then((s) => { if (active) setStatus(s); });
    return () => { active = false; };
  }, [user.xhs_user_id]);

  const refreshStatus = async () => {
    const s = await subService.status(user.xhs_user_id);
    setStatus(s.data);
    return s.data;
  };

  const handleSubscribe = async () => {
    setLoading(true);
    try {
      await subService.create({ xhs_user_id: user.xhs_user_id, nickname: user.nickname || '小红书博主', avatar: user.avatar });
      invalidateSubStatus(user.xhs_user_id);
      const s = await refreshStatus();
      setStatus(s);
      message.success('已订阅');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '订阅失败');
    } finally { setLoading(false); }
  };

  const handleUnsubscribe = async () => {
    if (!status?.subscription_id) return;
    setLoading(true);
    try {
      await subService.delete(status.subscription_id);
      invalidateSubStatus(user.xhs_user_id);
      setStatus({ subscribed: false, subscription_id: null, has_update: false });
      message.success('已取消订阅');
    } catch { message.error('取消失败'); }
    finally { setLoading(false); }
  };

  const handleAck = async () => {
    if (!status?.subscription_id) return;
    try {
      await subService.ack(status.subscription_id);
      invalidateSubStatus(user.xhs_user_id);
      setStatus({ ...status, has_update: false });
      message.success('已标记为已查看');
    } catch { message.error('操作失败'); }
  };

  if (!user.xhs_user_id) return null;
  if (status?.subscribed) {
    if (status.has_update && status.subscription_id) {
      return <Button size={size} icon={<BellOutlined />} onClick={handleAck} loading={loading}>{showText ? '已订阅·有更新' : null}</Button>;
    }
    return (
      <Popconfirm title="取消订阅？" onConfirm={handleUnsubscribe}>
        <Button size={size} icon={<CheckOutlined />} loading={loading}>{showText ? '已订阅' : null}</Button>
      </Popconfirm>
    );
  }
  return <Button size={size} type="primary" ghost icon={<PlusOutlined />} onClick={handleSubscribe} loading={loading}>{showText ? '订阅' : null}</Button>;
}
