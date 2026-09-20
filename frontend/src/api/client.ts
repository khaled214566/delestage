export default apiClient;

// Health check API — mirrors backend/app/schemas/health.py::HealthResponse.
// feeder_count and sheddable_mw are the M1 signal: they come straight from
// the seeded grid tables and the v_sheddable_feeders view, so a nonzero
// value here is live proof that M1's schema + seed data are working.
export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
  db_connected: boolean;
  feeder_count: number;
  sheddable_mw: number;
}

export const checkHealth = async (): Promise<HealthResponse> => {
  const { data } = await apiClient.get<HealthResponse>('/health');
  return data;
};