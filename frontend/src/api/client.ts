import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to attach JWT token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for auth errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

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

// --- Deficit computation (M3 / UC1) — mirrors backend/app/schemas/deficit.py ---

export type DeficitPlanStatus = 'DRAFT' | 'VALIDATED';
export type OrderMode = 'J-1' | 'REAL_TIME';

export interface DeficitSlot {
  id: number;
  plan_id: number;
  slot_start: string;
  slot_end: string;
  demand_mw: number;
  generation_mw: number;
  imports_mw: number;
  margin_mw: number;
  deficit_mw: number;
  updated_at: string;
}

export interface DeficitPlan {
  id: number;
  date: string;
  mode: OrderMode;
  status: DeficitPlanStatus;
  created_by: number;
  created_at: string;
  validated_by: number | null;
  validated_at: string | null;
  slots: DeficitSlot[];
}

export interface DeficitRevision {
  id: number;
  slot_id: number;
  changed_by: number;
  changed_at: string;
  old_values: Record<string, number>;
  new_values: Record<string, number>;
}

export interface CsvImportResult {
  created: number;
  updated: number;
  slots: DeficitSlot[];
}

export const listPlans = async (): Promise<DeficitPlan[]> => {
  const { data } = await apiClient.get<DeficitPlan[]>('/deficit/plans');
  return data;
};

export const createPlan = async (date: string, mode: OrderMode): Promise<DeficitPlan> => {
  const { data } = await apiClient.post<DeficitPlan>('/deficit/plans', { date, mode });
  return data;
};

export const getPlan = async (planId: number): Promise<DeficitPlan> => {
  const { data } = await apiClient.get<DeficitPlan>(`/deficit/plans/${planId}`);
  return data;
};

export const editSlot = async (
  planId: number,
  slotId: number,
  patch: Partial<Pick<DeficitSlot, 'demand_mw' | 'generation_mw' | 'imports_mw' | 'margin_mw'>>,
): Promise<DeficitSlot> => {
  const { data } = await apiClient.patch<DeficitSlot>(`/deficit/plans/${planId}/slots/${slotId}`, patch);
  return data;
};

export const importCsv = async (planId: number, csvText: string): Promise<CsvImportResult> => {
  const form = new FormData();
  form.append('file', new Blob([csvText], { type: 'text/csv' }), 'import.csv');
  // The instance default is 'application/json' (see apiClient above); for a
  // FormData body that must be unset, not overridden, so the browser can
  // generate 'multipart/form-data; boundary=...' itself — a hardcoded
  // Content-Type here would have the wrong (missing) boundary and the
  // server would fail to parse the body.
  const { data } = await apiClient.post<CsvImportResult>(`/deficit/plans/${planId}/import-csv`, form, {
    headers: { 'Content-Type': undefined },
  });
  return data;
};

export const validatePlan = async (planId: number): Promise<DeficitPlan> => {
  const { data } = await apiClient.post<DeficitPlan>(`/deficit/plans/${planId}/validate`);
  return data;
};

export const getSlotRevisions = async (planId: number, slotId: number): Promise<DeficitRevision[]> => {
  const { data } = await apiClient.get<DeficitRevision[]>(`/deficit/plans/${planId}/slots/${slotId}/revisions`);
  return data;
};

// --- Shed Orders & Allocation (M4+M5) ---

export type OrderStatus = 'DRAFT' | 'ALLOCATED' | 'VALIDATED' | 'ACTIVE' | 'COMPLETED' | 'CANCELLED';
export type AllocationLevel = 'NATIONAL' | 'CRC' | 'BCC';

export interface FeederAssignment {
  id: number;
  feeder_id: string;
  feeder_name: string;
  assigned_mw: number;
  priority: string;
  fairness_score: number;
  is_manual: boolean;
  assigned_at: string;
  assigned_by: number;
}

export interface AllocationNode {
  id: number;
  level: AllocationLevel;
  entity_id: string;
  target_mw: number;
  achieved_mw: number;
  shortfall_mw: number;
  is_partial: boolean;
  children: AllocationNode[];
  feeder_assignments: FeederAssignment[];
}

export interface ShedOrder {
  id: number;
  plan_id: number;
  status: OrderStatus;
  total_deficit_mw: number;
  created_by: number;
  created_at: string;
  allocated_at: string | null;
  validated_by: number | null;
  validated_at: string | null;
  activated_at: string | null;
  completed_at: string | null;
  cancelled_by: number | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  allocation_nodes: AllocationNode[];
}

export interface OrderListItem {
  id: number;
  plan_id: number;
  plan_date: string;
  plan_mode: string;
  status: OrderStatus;
  total_deficit_mw: number;
  created_at: string;
  shortfall_count: number;
}

export const listOrders = async (): Promise<OrderListItem[]> => {
  const { data } = await apiClient.get<OrderListItem[]>('/orders');
  return data;
};

export const createOrder = async (planId: number): Promise<ShedOrder> => {
  const { data } = await apiClient.post<ShedOrder>('/orders', { plan_id: planId });
  return data;
};

export const getOrder = async (orderId: number): Promise<ShedOrder> => {
  const { data } = await apiClient.get<ShedOrder>(`/orders/${orderId}`);
  return data;
};

export const allocateOrder = async (orderId: number): Promise<ShedOrder> => {
  const { data } = await apiClient.post<ShedOrder>(`/orders/${orderId}/allocate`);
  return data;
};

export const validateOrder = async (orderId: number): Promise<ShedOrder> => {
  const { data } = await apiClient.post<ShedOrder>(`/orders/${orderId}/validate`);
  return data;
};

export const cancelOrder = async (orderId: number, reason: string): Promise<ShedOrder> => {
  const { data } = await apiClient.post<ShedOrder>(`/orders/${orderId}/cancel`, { reason });
  return data;
};

export const addFeederOverride = async (orderId: number, nodeId: number, feederId: string): Promise<ShedOrder> => {
  const { data } = await apiClient.post<ShedOrder>(`/orders/${orderId}/allocate/nodes/${nodeId}/feeders`, { feeder_id: feederId });
  return data;
};

export const removeFeederOverride = async (orderId: number, assignmentId: number): Promise<ShedOrder> => {
  const { data } = await apiClient.delete<ShedOrder>(`/orders/${orderId}/allocate/assignments/${assignmentId}`);
  return data;
};

// --- Real-time Monitoring & Telemetry (M6) ---

export interface ShedEventOut {
  id: number;
  order_id: number;
  feeder_id: string;
  feeder_name: string;
  bcc_id: string;
  open_time: string;
  close_time: string | null;
  mw_actual: number;
  duration_min: number;
  ens_mwh: number;
  status: string;
  alarm_level: 'GREEN' | 'AMBER' | 'RED';
}

export interface RegionalSummary {
  entity_id: string;
  name: string;
  target_mw: number;
  actual_mw: number;
  gap_mw: number;
  open_feeders: number;
}

export interface MonitoringSummary {
  timestamp: string;
  order_id: number | null;
  target_mw: number;
  actual_mw: number;
  gap_mw: number;
  open_feeders_count: number;
  active_bccs_count: number;
  max_duration_min: number;
  total_ens_mwh: number;
  amber_alarms_count: number;
  red_alarms_count: number;
  crc_breakdown: RegionalSummary[];
  bcc_breakdown: RegionalSummary[];
  active_events: ShedEventOut[];
}

export const getMonitoringSummary = async (): Promise<MonitoringSummary> => {
  const { data } = await apiClient.get<MonitoringSummary>('/monitoring/summary');
  return data;
};

export const simulateToggle = async (feederId: string, openState: boolean): Promise<{ status: string; event_id: number }> => {
  const { data } = await apiClient.post('/monitoring/simulate', { feeder_id: feederId, open_state: openState });
  return data;
};

// --- BCC Execution (M7) ---

export interface FeederExecutionItem {
  feeder_id: string;
  feeder_name: string;
  substation_name: string;
  priority: string;
  is_critical: boolean;
  avg_mw: number;
  status: string;
  is_eligible: boolean;
  ineligibility_reason: string | null;
  rest_time_left_min: number | null;
  is_planned_in_order: boolean;
  current_event_id: number | null;
  open_time: string | null;
  elapsed_minutes: number | null;
  alarm_level: string | null;
}

export interface BccExecutionDashboard {
  bcc_id: string;
  bcc_name: string;
  target_mw: number;
  actual_mw: number;
  gap_mw: number;
  open_feeders_count: number;
  feeders: FeederExecutionItem[];
}

export interface ConfirmOpenPayload {
  order_id: number;
  feeder_id: string;
  open_time?: string;
  mw_actual: number;
  justification?: string;
}

export const getBccDashboard = async (bccId: string): Promise<BccExecutionDashboard> => {
  const { data } = await apiClient.get<BccExecutionDashboard>(`/execution/bcc/${bccId}`);
  return data;
};

export const confirmOpen = async (body: ConfirmOpenPayload): Promise<{ status: string; event_id: number }> => {
  const { data } = await apiClient.post('/execution/open', body);
  return data;
};

export const confirmClose = async (eventId: number, closeTime?: string): Promise<{ status: string; event_id: number }> => {
  const { data } = await apiClient.post(`/execution/events/${eventId}/close`, { close_time: closeTime });
  return data;
};

// --- Rotation Engine (M8 - UC6) ---

export interface ReplacementCandidate {
  feeder_id: string;
  feeder_name: string;
  substation_name: string;
  priority: string;
  avg_mw: number;
  delta_mw: number;
  fairness_score: number;
  cumulative_minutes: number;
  rest_time_left_min: number | null;
  is_eligible: boolean;
  ineligibility_reason: string | null;
}

export interface RotationProposal {
  outgoing_event_id: number;
  outgoing_feeder_id: string;
  outgoing_feeder_name: string;
  substation_name: string;
  bcc_id: string;
  bcc_name: string;
  open_time: string;
  elapsed_minutes: number;
  max_duration_minutes: number;
  elapsed_ratio: number;
  alarm_level: 'AMBER' | 'RED';
  outgoing_mw: number;
  recommended_replacement: ReplacementCandidate | null;
  alternatives: ReplacementCandidate[];
}

export interface ExecuteRotationRequest {
  outgoing_event_id: number;
  replacement_feeder_id: string;
  replacement_mw?: number;
  justification?: string;
}

export interface ExecuteRotationResponse {
  status: string;
  outgoing_feeder_id: string;
  replacement_feeder_id: string;
  opened_event_id: number;
  restored_event_id: number;
  outgoing_mw: number;
  replacement_mw: number;
  delta_mw: number;
  ens_mwh: number;
  duration_min: number;
  rotations_count: number;
  message: string;
}

export const getRotationProposals = async (bccId?: string): Promise<RotationProposal[]> => {
  const params = bccId ? { bcc_id: bccId } : {};
  const { data } = await apiClient.get<RotationProposal[]>('/rotation/proposals', { params });
  return data;
};

export const executeRotation = async (payload: ExecuteRotationRequest): Promise<ExecuteRotationResponse> => {
  const { data } = await apiClient.post<ExecuteRotationResponse>('/rotation/execute', payload);
  return data;
};

// ─── M9 Admin ──────────────────────────────────────────────────────────────────

export interface ParametersData {
  id: number;
  max_duration_min: number;
  rest_time_min: number;
  slot_size_min: number;
  rotation_warn_pct: number;
  regional_key: Record<string, number>;
}

export interface UserData {
  id: number;
  username: string;
  name: string;
  role: string;
  scope_type: string;
  scope_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface UserCreatePayload {
  username: string;
  name: string;
  password: string;
  role: string;
  scope_type: string;
  scope_id: string | null;
}

export interface AuditLogEntry {
  seq: number;
  timestamp: string;
  actor_id: string;
  actor_name: string;
  action: string;
  entity_type: string;
  entity_id: string;
  payload: unknown;
  prev_hash: string;
  hash: string;
}

export interface AuditListResponse {
  total: number;
  page: number;
  page_size: number;
  items: AuditLogEntry[];
}

export interface ChainVerifyResponse {
  ok: boolean;
  total_checked: number;
  broken_at_seq: number | null;
}

export const getParameters = async (): Promise<ParametersData> => {
  const { data } = await apiClient.get<ParametersData>('/admin/parameters');
  return data;
};

export const patchParameters = async (patch: Partial<Omit<ParametersData, 'id' | 'regional_key'>>): Promise<ParametersData> => {
  const { data } = await apiClient.patch<ParametersData>('/admin/parameters', patch);
  return data;
};

export const getUsers = async (): Promise<UserData[]> => {
  const { data } = await apiClient.get<UserData[]>('/admin/users');
  return data;
};

export const createUser = async (payload: UserCreatePayload): Promise<UserData> => {
  const { data } = await apiClient.post<UserData>('/admin/users', payload);
  return data;
};

export const toggleUser = async (userId: number): Promise<UserData> => {
  const { data } = await apiClient.patch<UserData>(`/admin/users/${userId}/toggle`);
  return data;
};

export const getAuditLogs = async (page = 1, pageSize = 50, action?: string, actor?: string): Promise<AuditListResponse> => {
  const params: Record<string, unknown> = { page, page_size: pageSize };
  if (action) params.action = action;
  if (actor) params.actor = actor;
  const { data } = await apiClient.get<AuditListResponse>('/admin/audit', { params });
  return data;
};

export const verifyAuditChain = async (): Promise<ChainVerifyResponse> => {
  const { data } = await apiClient.get<ChainVerifyResponse>('/admin/audit/verify');
  return data;
};

export const exportAuditCsv = (action?: string, actor?: string): string => {
  const params = new URLSearchParams();
  if (action) params.set('action', action);
  if (actor) params.set('actor', actor);
  // Return URL for direct download link (browser handles file)
  const base = '/api/admin/audit/export.csv';
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
};

// ─── M10 Public Citizen ────────────────────────────────────────────────────────

export interface CitizenEvent {
  started_at: string | null;
  estimated_end: string | null;
  alarm_level: string;
  duration_min: number;
  feeders_affected: number;
}

export interface CitizenZone {
  zone_id: string;
  display_name: string;
  status: 'SHEDDING' | 'NORMAL';
  events: CitizenEvent[];
  feeders_affected: number;
}

export interface CitizenStatusResponse {
  generated_at: string;
  total_zones: number;
  currently_shedding: number;
  zones: CitizenZone[];
}

export const getCitizenStatus = async (): Promise<CitizenStatusResponse> => {
  const { data } = await apiClient.get<CitizenStatusResponse>('/public/status');
  return data;
};

// ─── M11 Simulator ─────────────────────────────────────────────────────────────

export interface SimulatorStatus {
  open_events: number;
  is_demo_running: boolean;
  message: string;
}

export interface BeatResult {
  beat?: number;
  label?: string;
  status: string;
  message: string;
  [key: string]: unknown;
}

export const getSimulatorStatus = async (): Promise<SimulatorStatus> => {
  const { data } = await apiClient.get<SimulatorStatus>('/simulator/status');
  return data;
};

export const triggerBeat = async (beatNumber: number): Promise<BeatResult> => {
  const { data } = await apiClient.post<BeatResult>(`/simulator/beat/${beatNumber}`);
  return data;
};

export const resetSimulator = async (): Promise<BeatResult> => {
  const { data } = await apiClient.post<BeatResult>('/simulator/reset');
  return data;
};

// ─── M12 Evaluation & Benchmarks ───────────────────────────────────────────────

export interface BenchmarkScenario {
  engine_name: string;
  description: string;
  gini_index: number;
  p0_violations: number;
  max_duration_min: number;
  target_achievement_pct: number;
  ens_mwh: number;
  avg_rotations_per_feeder: number;
  fairness_advantage_pct: number;
}

export interface BenchmarkResponse {
  days_simulated: number;
  scenarios: BenchmarkScenario[];
}

export interface GridFairnessMetrics {
  total_feeders: number;
  live_gini_index: number;
  total_ens_mwh: number;
  total_rotations: number;
  p0_protected_count: number;
  bcc_breakdown: Record<string, { feeders: number; total_minutes: number; rotations: number }>;
}

export const getBenchmark = async (days = 7): Promise<BenchmarkResponse> => {
  const { data } = await apiClient.get<BenchmarkResponse>('/evaluation/benchmark', { params: { days } });
  return data;
};

export const getGridFairnessMetrics = async (): Promise<GridFairnessMetrics> => {
  const { data } = await apiClient.get<GridFairnessMetrics>('/evaluation/metrics');
  return data;
};

