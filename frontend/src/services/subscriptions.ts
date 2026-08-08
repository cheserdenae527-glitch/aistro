import api from './api';
export interface Subscription { id:string; xhs_user_id:string; nickname:string; avatar:string|null; note_count:number; follower_count:number; following_count:number; notified_note_count:number; last_crawled_at:string|null; created_at:string; refresh_status?: "success"|"partial"|"failed"|null; refresh_error?: string|null; }
export interface SubStatus { subscribed:boolean; subscription_id:string|null; has_update:boolean; }
export const subService = {
  list: () => api.get<Subscription[]>('/subscriptions'),
  create: (data:{ xhs_user_id:string; nickname:string; avatar?:string }) => api.post<Subscription>('/subscriptions', data),
  refresh: (id:string) => api.post<Subscription>('/subscriptions/'+id+'/refresh'),
  delete: (id:string) => api.delete('/subscriptions/'+id),
  status: (xhsUserId:string) => api.get<SubStatus>('/subscriptions/status', { params: { xhs_user_id: xhsUserId } }),
  statusBatch: (xhsUserIds:string[]) => api.post<{ items: Record<string, SubStatus> }>('/subscriptions/status/batch', { xhs_user_ids: xhsUserIds }),
  ack: (id:string) => api.post<Subscription>('/subscriptions/'+id+'/ack'),
};
