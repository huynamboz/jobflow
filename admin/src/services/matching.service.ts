import { apiClient } from "@/lib/api-client";
import type { CVMatchData, MatchResponse } from "@/types/matching.types";

const MATCH_TIMEOUT = 180_000; // engine cold-start can take ~2 min

class MatchingService {
  async matchText(text: string, topK = 10): Promise<CVMatchData> {
    const res = await apiClient.post<MatchResponse>("/matching/cv/", { text, top_k: topK }, { timeout: MATCH_TIMEOUT });
    return res.data.data;
  }

  async matchFile(file: File, topK = 10): Promise<CVMatchData> {
    const form = new FormData();
    form.append("file", file);
    form.append("top_k", String(topK));
    const res = await apiClient.post<MatchResponse>("/matching/cv/upload/", form, { timeout: MATCH_TIMEOUT });
    return res.data.data;
  }
}

export const matchingService = new MatchingService();
