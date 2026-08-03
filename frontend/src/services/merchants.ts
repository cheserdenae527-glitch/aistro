import api from "./api";
import type { Shop } from "./shops";

export interface Merchant {
  id: string;
  user_id: string;
  name: string;
  contact_name: string | null;
  contact_phone: string | null;
  tier: string;
  notes: string | null;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface MerchantWithShops {
  merchant: Merchant;
  shops: Shop[];
}

export const merchantService = {
  list: (params?: { page?: number; size?: number; name?: string }) =>
    api.get<PaginatedResponse<Merchant>>("/merchants", { params }),

  listWithShops: () =>
    api.get<MerchantWithShops[]>("/profile/merchants-with-shops"),

  create: (data: { name: string; contact_name?: string; contact_phone?: string; tier?: string; notes?: string }) =>
    api.post<Merchant>("/merchants", data),

  get: (id: string) =>
    api.get<Merchant>(`/merchants/${id}`),

  update: (id: string, data: { name?: string; contact_name?: string; contact_phone?: string; tier?: string; notes?: string }) =>
    api.patch<Merchant>(`/merchants/${id}`, data),

  delete: (id: string) =>
    api.delete(`/merchants/${id}`),
};
