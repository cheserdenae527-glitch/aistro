// frontend/src/services/pgy.ts — 蒲公英（JustOneAPI）官方补充数据
import api from './api';

export interface PgyContentTag {
  taxonomy1Tag?: string;
  taxonomy2Tags?: string[];
}

export interface PgyCreatorProfile {
  userId?: string;
  name?: string;
  redId?: string;
  headPhoto?: string;
  location?: string;
  gender?: string;
  fansCount?: number;
  likeCollectCountInfo?: number;
  businessNoteCount?: number;
  picturePrice?: number;
  videoPrice?: number;
  lowerPrice?: number;
  contentTags?: PgyContentTag[];
  featureTags?: string[];
  tradeType?: string;
  currentLevel?: number;
  clickMidNum?: number;
  interMidNum?: number;
  travelAreaList?: string[];
  videoFinishRate?: number | null;
  totalNoteCount?: number | null;
}

export interface PgyFansSummary {
  fansNum?: number;
  fansIncreaseNum?: number;
  fansGrowthRate?: string;
  fansGrowthBeyondRate?: string;
  activeFansL28?: number;
  activeFansRate?: string;
  activeFansBeyondRate?: string;
  engageFansRate?: string;
  engageFansL30?: number;
  engageFansBeyondRate?: string;
  readFansIn30?: number;
  readFansRate?: string;
  readFansBeyondRate?: string;
  payFansUserRate30d?: string;
  payFansUserNum30d?: number;
}

export type PgySimilarKol = PgyCreatorProfile;

export interface PgyResponse<T> {
  ok: boolean;
  data: T | null;
  error?: string;
  cached?: boolean;
}

export async function fetchCreatorProfile(userId: string): Promise<PgyResponse<PgyCreatorProfile>> {
  return (await api.get(`/pgy/users/${userId}/creator-profile`)).data;
}

export async function fetchFansSummary(userId: string): Promise<PgyResponse<PgyFansSummary>> {
  return (await api.get(`/pgy/users/${userId}/fans-summary`)).data;
}

export async function fetchSimilarKol(userId: string, pageNum = 1): Promise<PgyResponse<{ kols: PgySimilarKol[] }>> {
  return (await api.get(`/pgy/users/${userId}/similar`, { params: { pageNum } })).data;
}
