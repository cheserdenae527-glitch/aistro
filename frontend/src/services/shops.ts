import api from "./api";


export interface Shop {
  id: string;
  merchant_id: string;
  name: string;
  address: string | null;
  phone: string | null;
  category: string | null;
  status: string;
  created_at: string;
}

export interface PlatformShop {
  id: string;
  shop_id: string;
  platform: string;
  platform_shop_id: string | null;
  shop_name: string | null;
  rating: number | null;
  monthly_sales: number | null;
  total_reviews: number | null;
  last_synced_at: string | null;
  created_at: string;
}

export const shopService = {
  listByMerchant: (mid: string) =>
    api.get<Shop[]>(`/merchants/${mid}/shops`),

  create: (mid: string, data: { name: string; address?: string; phone?: string; category?: string }) =>
    api.post<Shop>(`/merchants/${mid}/shops`, data),

  get: (sid: string) =>
    api.get<Shop>(`/shops/${sid}`),

  update: (sid: string, data: { name?: string; address?: string; phone?: string; category?: string; status?: string }) =>
    api.patch<Shop>(`/shops/${sid}`, data),

  delete: (sid: string) =>
    api.delete(`/shops/${sid}`),
};

