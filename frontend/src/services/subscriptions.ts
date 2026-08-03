import api from './api';
export interface Subscription { id:string; xhs_user_id:string; nickname:string; avatar:string|null; note_count:number; follower_count:number; following_count:number; last_crawled_at:string|null; created_at:string; }
export const subService = { list: () => api.get<Subscription[]>('/subscriptions'), create: (data:{ xhs_user_id:string; nickname:string; avatar?:string }) => api.post<Subscription>('/subscriptions', data), refresh: (id:string) => api.post<Subscription>('/subscriptions/'+id+'/refresh'), delete: (id:string) => api.delete('/subscriptions/'+id) };
