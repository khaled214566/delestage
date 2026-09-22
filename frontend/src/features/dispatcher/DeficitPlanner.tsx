import { useState, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createPlan,
  editSlot,
  getPlan,
  getSlotRevisions,
  importCsv,
  listPlans,
  validatePlan,
  createOrder,
  type DeficitPlan,
  type DeficitSlot,
} from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import '../../App.css';

// ─── Preset Scenario CSVs ────────────────────────────────────────────
// These represent realistic J-1 forecast files a dispatcher would prepare

const SCENARIO_CANICULE =
  'slot,demandMW,generationMW,importsMW,marginMW\n' +
  '19:00-19:30,4350,3800,200,50\n' +
  '19:30-20:00,4400,3800,200,50\n' +
  '20:00-20:30,4300,3800,200,50\n' +
  '20:30-21:00,4150,3800,200,50\n' +
  '21:00-21:30,4000,3800,200,50\n';

const SCENARIO_NOMINAL =
  'slot,demandMW,generationMW,importsMW,marginMW\n' +
  '19:00-19:30,4100,3800,200,50\n' +
  '19:30-20:00,4150,3800,250,50\n' +
  '20:00-20:30,4050,3800,200,50\n' +
  '20:30-21:00,3950,3800,200,50\n' +
  '21:00-21:30,3850,3800,200,50\n';

const SCENARIO_EOLIEN_BAS =
  'slot,demandMW,generationMW,importsMW,marginMW\n' +
  '19:00-19:30,4200,3600,150,50\n' +
  '19:30-20:00,4250,3600,150,50\n' +
  '20:00-20:30,4200,3600,150,50\n' +
  '20:30-21:00,4100,3600,150,50\n' +
  '21:00-21:30,3900,3600,150,50\n';

const PRESETS = [
  { label: 'Pic Canicule (~300 MW)', csv: SCENARIO_CANICULE, icon: '🔥' },
  { label: 'Nominal (~50 MW)', csv: SCENARIO_NOMINAL, icon: '✅' },
  { label: 'Éolien Bas (~400 MW)', csv: SCENARIO_EOLIEN_BAS, icon: '🌬️' },
];

// ─── Helpers ─────────────────────────────────────────────────────────

function tomorrow(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function formatDateLong(iso: string): string {
  const d = new Date(iso + 'T00:00:00');
  const s = d.toLocaleDateString('fr-FR', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function fmt(n: number) {
  return n.toLocaleString('fr-FR', { maximumFractionDigits: 1 });
}

function slotLabel(slot: DeficitSlot) {
  const opts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' };
  const start = new Date(slot.slot_start).toLocaleTimeString('fr-FR', opts);
  const end = new Date(slot.slot_end).toLocaleTimeString('fr-FR', opts);
  return `${start}–${end}`;
}

function extractErrorDetail(err: unknown): string | undefined {
  const maybe = err as { response?: { data?: { detail?: string } } };
  return maybe?.response?.data?.detail;
}

function downloadTemplateCsv() {
  const content =
    'slot,demandMW,generationMW,importsMW,marginMW\n' +
    '19:00-19:30,4000,3800,200,50\n' +
    '19:30-20:00,4000,3800,200,50\n';
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'gabarit_prevision_j1.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

// ─── Revision History ────────────────────────────────────────────────

function RevisionHistory({ planId, slotId }: { planId: number; slotId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['deficit-revisions', planId, slotId],
    queryFn: () => getSlotRevisions(planId, slotId),
  });

  if (isLoading) return <div className="revision-empty">Chargement…</div>;
  if (!data || data.length === 0) return <div className="revision-empty">Aucune modification</div>;

  return (
    <ul className="revision-list">
      {data.map((rev) => (
        <li key={rev.id}>
          {new Date(rev.changed_at).toLocaleString('fr-FR')} —{' '}
          {Object.keys(rev.new_values)
            .filter((k) => rev.old_values[k] !== rev.new_values[k])
            .map((k) => `${k}: ${fmt(rev.old_values[k])} → ${fmt(rev.new_values[k])}`)
            .join(', ')}
        </li>
      ))}
    </ul>
  );
}

// ─── Slot Row ────────────────────────────────────────────────────────

type EditableField = 'demand_mw' | 'generation_mw' | 'imports_mw' | 'margin_mw';
const EDITABLE_FIELDS: EditableField[] = ['demand_mw', 'generation_mw', 'imports_mw', 'margin_mw'];

function SlotRow({ plan, slot }: { plan: DeficitPlan; slot: DeficitSlot }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<EditableField, number>>({
    demand_mw: slot.demand_mw,
    generation_mw: slot.generation_mw,
    imports_mw: slot.imports_mw,
    margin_mw: slot.margin_mw,
  });
  const [showHistory, setShowHistory] = useState(false);
  const isValidated = plan.status === 'VALIDATED';

  const dirty = EDITABLE_FIELDS.some((f) => draft[f] !== slot[f]);

  const save = useMutation({
    mutationFn: () => editSlot(plan.id, slot.id, draft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deficit-plan', plan.id] });
      queryClient.invalidateQueries({ queryKey: ['deficit-revisions', plan.id, slot.id] });
    },
  });

  return (
    <>
      <tr className="slot-table-row">
        <td className="slot-col-time">{slotLabel(slot)}</td>
        {EDITABLE_FIELDS.map((field) => (
          <td key={field} className="slot-col-input">
            <input
              type="number"
              step="0.1"
              className="slot-input"
              value={draft[field]}
              disabled={save.isPending || isValidated}
              onChange={(e) => setDraft((d) => ({ ...d, [field]: Number(e.target.value) }))}
            />
          </td>
        ))}
        <td className="slot-col-deficit">
          <div className={slot.deficit_mw > 0 ? 'deficit-badge deficit-positive' : 'deficit-badge deficit-zero'}>
            {fmt(slot.deficit_mw)}
          </div>
        </td>
        <td className="slot-col-actions">
          <div className="slot-actions">
            {!isValidated && (
              <button
                className="btn-action-save"
                disabled={!dirty || save.isPending}
                onClick={() => save.mutate()}
                title="Enregistrer les modifications"
              >
                {save.isPending ? '…' : 'Enregistrer'}
              </button>
            )}
            <button
              type="button"
              className={`btn-action-history ${showHistory ? 'active' : ''}`}
              onClick={() => setShowHistory((s) => !s)}
              title="Historique des modifications"
            >
              <span>Historique</span>
              <span className={`switch-toggle ${showHistory ? 'checked' : ''}`}>
                <span className="switch-handle" />
              </span>
            </button>
          </div>
        </td>
      </tr>
      {showHistory && (
        <tr className="revision-row">
          <td colSpan={7}>
            <div className="revision-card">
              <span className="revision-card-title">Journal des révisions :</span>
              <RevisionHistory planId={plan.id} slotId={slot.id} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ─── Main Component ──────────────────────────────────────────────────

export default function DeficitPlanner() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isDispatcherOrAdmin = user?.role === 'DISPATCHER' || user?.role === 'ADMIN';

  // Target date is always tomorrow (J-1 planning)
  const targetDate = useMemo(() => tomorrow(), []);

  const { data: plans } = useQuery({
    queryKey: ['deficit-plans'],
    queryFn: listPlans,
    enabled: isDispatcherOrAdmin,
  });

  const [planId, setPlanId] = useState<number | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [showArchive, setShowArchive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: plan } = useQuery({
    queryKey: ['deficit-plan', planId],
    queryFn: () => getPlan(planId as number),
    enabled: planId !== null,
  });

  // Auto-create or open tomorrow's J-1 plan
  const initPlanMutation = useMutation({
    mutationFn: () => createPlan(targetDate, 'J-1'),
    onSuccess: (created) => {
      setPlanId(created.id);
      queryClient.invalidateQueries({ queryKey: ['deficit-plans'] });
    },
    onError: () => {
      // Plan might already exist — find it in the list
      const existing = plans?.find((p) => p.date === targetDate && p.mode === 'J-1');
      if (existing) {
        setPlanId(existing.id);
      }
    },
  });

  // CSV import that auto-creates tomorrow's plan if needed
  const csvUploadMutation = useMutation({
    mutationFn: async (csvText: string) => {
      let id = planId;
      if (!id) {
        const created = await createPlan(targetDate, 'J-1');
        id = created.id;
        setPlanId(id);
        queryClient.invalidateQueries({ queryKey: ['deficit-plans'] });
      }
      await importCsv(id, csvText);
      return id;
    },
    onSuccess: (id) => {
      setCsvError(null);
      queryClient.invalidateQueries({ queryKey: ['deficit-plan', id] });
      queryClient.invalidateQueries({ queryKey: ['deficit-plans'] });
    },
    onError: (err: unknown) => setCsvError(extractErrorDetail(err) ?? "Échec de l'import CSV"),
  });

  // Validate + create order in one step
  const validateAndCreateMutation = useMutation({
    mutationFn: async () => {
      await validatePlan(planId as number);
      const order = await createOrder(planId as number);
      return order;
    },
    onSuccess: (order) => {
      queryClient.invalidateQueries({ queryKey: ['deficit-plan', planId] });
      queryClient.invalidateQueries({ queryKey: ['deficit-plans'] });
      navigate(`/orders/${order.id}`);
    },
  });

  // Handle file upload (from input or drag-drop)
  const handleFileUpload = useCallback(
    (file: File) => {
      setCsvError(null);
      file.text().then((text) => csvUploadMutation.mutate(text));
    },
    [csvUploadMutation],
  );

  // Handle preset scenario
  const handlePreset = useCallback(
    (csv: string) => {
      setCsvError(null);
      csvUploadMutation.mutate(csv);
    },
    [csvUploadMutation],
  );

  // Drag & Drop handlers
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file && (file.name.endsWith('.csv') || file.type === 'text/csv')) {
        handleFileUpload(file);
      } else {
        setCsvError('Veuillez déposer un fichier CSV (.csv)');
      }
    },
    [handleFileUpload],
  );

  // Total deficit summary
  const totalDeficit = plan?.slots.reduce((sum, s) => sum + s.deficit_mw, 0) ?? 0;
  const slotsWithDeficit = plan?.slots.filter((s) => s.deficit_mw > 0).length ?? 0;

  // Formatted dates
  const tomorrowFormatted = formatDateLong(targetDate);

  // Archived past plans (excluding tomorrow's active plan)
  const archivedPlans = plans?.filter((p) => !(p.date === targetDate && p.mode === 'J-1')) ?? [];

  // Auto-open tomorrow's plan on first load
  const tomorrowPlan = plans?.find((p) => p.date === targetDate && p.mode === 'J-1');
  if (tomorrowPlan && planId === null) {
    setPlanId(tomorrowPlan.id);
  }

  if (!isDispatcherOrAdmin) {
    return (
      <div className="deficit-planner-container">
        <div className="deficit-card">
          <h1 className="page-main-title">Planification du Déficit J-1</h1>
          <p className="module-sub">Réservé aux rôles Dispatcher et Admin.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="deficit-planner-container">
      {/* ── Page Header ── */}
      <div className="page-header-row">
        <div>
          <h1 className="page-main-title">Planification du Déficit J-1</h1>
          <p className="page-subtitle">
            Prévision de délestage pour <strong>{tomorrowFormatted}</strong>
          </p>
        </div>
        <div className="page-header-actions">
          <button
            type="button"
            className="btn-archive-toggle"
            onClick={() => setShowArchive(!showArchive)}
          >
            {showArchive ? 'Masquer l\'historique' : 'Plans précédents'}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points={showArchive ? '18 15 12 9 6 15' : '6 9 12 15 18 9'}></polyline>
            </svg>
          </button>
        </div>
      </div>

      {/* ── Archive Dropdown ── */}
      {showArchive && archivedPlans.length > 0 && (
        <div className="deficit-card archive-card">
          <div className="card-caption-title">Plans précédents</div>
          <div className="archive-list">
            {archivedPlans.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`archive-item ${planId === p.id ? 'active' : ''}`}
                onClick={() => { setPlanId(p.id); setShowArchive(false); }}
              >
                <span className="archive-date">{formatDateLong(p.date)}</span>
                <span className={`archive-status-badge ${p.status === 'VALIDATED' ? 'validated' : 'draft'}`}>
                  {p.status}
                </span>
                <span className="archive-slots">{p.slots.length} créneaux</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Import Section: CSV Upload + Presets ── */}
      <div className="deficit-card import-card">
        <div className="import-card-layout">
          {/* Left: Drag & Drop Zone */}
          <div
            className={`csv-dropzone ${isDragging ? 'dragging' : ''} ${csvUploadMutation.isPending ? 'loading' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
                e.target.value = '';
              }}
            />
            {csvUploadMutation.isPending ? (
              <div className="dropzone-content">
                <div className="dropzone-spinner" />
                <span className="dropzone-text">Import en cours…</span>
              </div>
            ) : (
              <div className="dropzone-content">
                <svg className="dropzone-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                <span className="dropzone-text">
                  <strong>Glisser-déposer</strong> votre fichier CSV ici
                </span>
                <span className="dropzone-hint">ou cliquer pour parcourir</span>
              </div>
            )}
          </div>

          {/* Right: Presets + Template Download */}
          <div className="import-presets-panel">
            <div className="presets-title">Scénarios préconfigurés</div>
            <div className="presets-grid">
              {PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="preset-btn"
                  onClick={() => handlePreset(preset.csv)}
                  disabled={csvUploadMutation.isPending}
                >
                  <span className="preset-icon">{preset.icon}</span>
                  <span className="preset-label">{preset.label}</span>
                </button>
              ))}
            </div>
            <div className="presets-divider" />
            <button type="button" className="btn-download-template" onClick={downloadTemplateCsv}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
              Télécharger le gabarit CSV
            </button>
          </div>
        </div>

        {csvError && <div className="status error" style={{ marginTop: '0.75rem' }}>{csvError}</div>}
        {initPlanMutation.isError && (
          <div className="status error" style={{ marginTop: '0.75rem' }}>
            {extractErrorDetail(initPlanMutation.error) ?? 'Erreur lors de la création du plan'}
          </div>
        )}
      </div>

      {/* ── Plan Status Banner (if plan exists) ── */}
      {plan && (
        <div className={`deficit-card status-banner-card ${plan.status === 'VALIDATED' ? 'validated' : 'draft'}`}>
          <div className="status-banner-left">
            <span className={`status-dot ${plan.status === 'VALIDATED' ? 'dot-green' : 'dot-amber'}`} />
            <span className="status-banner-text">
              Plan du <strong>{formatDateLong(plan.date)}</strong> — Statut : <strong>{plan.status === 'VALIDATED' ? 'Validé ✓' : 'Brouillon'}</strong>
            </span>
          </div>
          {plan.slots.length > 0 && (
            <div className="status-banner-stats">
              <span className="stat-chip">
                <strong>{fmt(totalDeficit)}</strong> MW déficit total
              </span>
              <span className="stat-chip">
                <strong>{slotsWithDeficit}</strong>/{plan.slots.length} créneaux en déficit
              </span>
            </div>
          )}
        </div>
      )}

      {/* ── Table Section ── */}
      {plan && plan.slots.length > 0 && (
        <div className="deficit-card table-card">
          <div className="table-card-header">
            <div className="card-caption-title">Créneaux & Calcul du Déficit</div>
          </div>

          <div className="table-responsive-wrapper">
            <table className="modern-deficit-table">
              <thead>
                <tr>
                  <th>Créneau</th>
                  <th>Demande (MW)</th>
                  <th>Production (MW)</th>
                  <th>Imports (MW)</th>
                  <th>Marge (MW)</th>
                  <th>Déficit (MW)</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {plan.slots.map((slot) => (
                  <SlotRow key={slot.id} plan={plan} slot={slot} />
                ))}
              </tbody>
            </table>
          </div>

          {/* ── Validate & Create Order ── */}
          {plan.status !== 'VALIDATED' && (
            <div className="validate-footer">
              <button
                type="button"
                className="btn-validate-and-proceed"
                onClick={() => validateAndCreateMutation.mutate()}
                disabled={plan.slots.length === 0 || validateAndCreateMutation.isPending}
              >
                {validateAndCreateMutation.isPending ? (
                  'Validation & création en cours…'
                ) : (
                  <>
                    Valider le plan & Générer l'Ordre de Délestage
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="5" y1="12" x2="19" y2="12"></line>
                      <polyline points="12 5 19 12 12 19"></polyline>
                    </svg>
                  </>
                )}
              </button>
              {validateAndCreateMutation.isError && (
                <div className="status error" style={{ marginTop: '0.75rem' }}>
                  {extractErrorDetail(validateAndCreateMutation.error) ?? 'Erreur lors de la validation'}
                </div>
              )}
            </div>
          )}

          {plan.status === 'VALIDATED' && (
            <div className="validate-footer validated-notice">
              <span className="validated-check">✓ Plan validé et verrouillé</span>
            </div>
          )}
        </div>
      )}

      {/* Empty state — no plan yet */}
      {!plan && !tomorrowPlan && (
        <div className="deficit-card empty-state-card">
          <div className="empty-state-content">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
            </svg>
            <p className="empty-title">Aucun plan pour {tomorrowFormatted}</p>
            <p className="empty-hint">Importez un CSV de prévision ou choisissez un scénario ci-dessus pour démarrer la planification J-1.</p>
          </div>
        </div>
      )}
    </div>
  );
}
