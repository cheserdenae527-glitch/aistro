import api from './api';
import type { SubStatus } from './subscriptions';

const TTL = 60_000;
const cache = new Map<string, { expires: number; value: SubStatus }>();
let queue: string[] = [];
const resolvers = new Map<string, (v: SubStatus) => void>();
let timer: ReturnType<typeof setTimeout> | null = null;

async function flush() {
  const ids = [...new Set(queue)];
  queue = [];
  timer = null;
  if (ids.length === 0) return;
  try {
    const res = await api.post<{ items: Record<string, SubStatus> }>('/subscriptions/status/batch', { xhs_user_ids: ids });
    const items = res.data.items || {};
    for (const id of ids) {
      const value: SubStatus = items[id] || { subscribed: false, subscription_id: null, has_update: false };
      cache.set(id, { expires: Date.now() + TTL, value });
      resolvers.get(id)?.(value);
      resolvers.delete(id);
    }
  } catch {
    for (const id of ids) {
      resolvers.get(id)?.({ subscribed: false, subscription_id: null, has_update: false });
      resolvers.delete(id);
    }
  }
}

export function getSubStatus(xhsUserId: string): Promise<SubStatus> {
  const hit = cache.get(xhsUserId);
  if (hit && hit.expires > Date.now()) return Promise.resolve(hit.value);
  queue.push(xhsUserId);
  if (!timer) timer = setTimeout(flush, 40);
  return new Promise((resolve) => resolvers.set(xhsUserId, resolve));
}

export function invalidateSubStatus(xhsUserId: string) {
  cache.delete(xhsUserId);
}
