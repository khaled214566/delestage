import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createPlan,
  editSlot,
  getPlan,
  getSlotRevisions,
  importCsv,
  listPlans,
  validatePlan,
  type DeficitPlan,
  type DeficitSlot,
  type OrderMode,
} from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import '../../App.css';

// Exact worked example from the documentation, section 12, UC1 — gives
// 300, 350, 250, 100, 0 MW.
const DEMO_DATE = '2026-09-19';
const DEMO_CSV =
  'slot,demandMW,generationMW,importsMW,marginMW\n' +
  '19:00-19:30,4350,3800,200,50\n' +
  '19:30-20:00,4400,3800,200,50\n' +
  '20:00-20:30,4300,3800,200,50\n' +
  '20:30-21:00,4150,3800,200,50\n' +
  '21:00-21:30,4000,3800,200,50\n';

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
      <tr>
        <td>{slotLabel(slot)}</td>
        {EDITABLE_FIELDS.map((field) => (
          <td key={field}>
            <input
              type="number"
              className="slot-input"
              value={draft[field]}
              disabled={save.isPending}
              onChange={(e) => setDraft((d) => ({ ...d, [field]: Number(e.target.value) }))}
            />
          </td>
        ))}
        <td className={slot.deficit_mw > 0 ? 'deficit-value' : 'deficit-value deficit-zero'}>
          {fmt(slot.deficit_mw)}
        </td>
        <td className="slot-actions">
          <button className="btn-small" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? '…' : 'Enregistrer'}
          </button>
          <button className="btn-small btn-ghost" onClick={() => setShowHistory((s) => !s)}>
            Historique
          </button>
        </td>
      </tr>
      {showHistory && (
        <tr className="revision-row">
          <td colSpan={6}>
            <RevisionHistory planId={plan.id} slotId={slot.id} />
          </td>
        </tr>
      )}
    </>
  );
}

export default function DeficitPlanner() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isDispatcher = user?.role === 'DISPATCHER';

  const { data: plans } = useQuery({ queryKey: ['deficit-plans'], queryFn: listPlans, enabled: isDispatcher });
  const [planId, setPlanId] = useState<number | null>(null);
  const [date, setDate] = useState(DEMO_DATE);
  const [mode, setMode] = useState<OrderMode>('J-1');
  const [csvError, setCsvError] = useState<string | null>(null);

  const { data: plan } = useQuery({
    queryKey: ['deficit-plan', planId],
    queryFn: () => getPlan(planId as number),
    enabled: planId !== null,
  });

  const createMutation = useMutation({
    mutationFn: () => createPlan(date, mode),
    onSuccess: (created) => {
      setPlanId(created.id);
      queryClient.invalidateQueries({ queryKey: ['deficit-plans'] });
    },
  });

  const demoMutation = useMutation({
    mutationFn: async () => {
      const created = await createPlan(DEMO_DATE, 'J-1');
      await importCsv(created.id, DEMO_CSV);
      return created.id;
    },
    onSuccess: (id) => {
      setCsvError(null);
      setPlanId(id);
      queryClient.invalidateQueries({ queryKey: ['deficit-plans'] });
      queryClient.invalidateQueries({ queryKey: ['deficit-plan', id] });
    },
  });

  const csvMutation = useMutation({
    mutationFn: (file: File) => file.text().then((text) => importCsv(planId as number, text)),
    onSuccess: () => {
      setCsvError(null);
      queryClient.invalidateQueries({ queryKey: ['deficit-plan', planId] });
    },
    onError: (err: unknown) => setCsvError(extractErrorDetail(err) ?? "Échec de l'import CSV"),
  });

  const validateMutation = useMutation({
    mutationFn: () => validatePlan(planId as number),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['deficit-plan', planId] }),
  });

  if (!isDispatcher) {
    return (
      <div className="info deficit-planner">
        <h2>Calcul du déficit (UC1)</h2>
        <p className="module-sub">Réservé au rôle Dispatcher.</p>
      </div>
    );
  }

  return (
    <div className="info deficit-planner">
      <h2>Calcul du déficit (UC1)</h2>

      <div className="deficit-toolbar">
        <select
          value={planId ?? ''}
          onChange={(e) => setPlanId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">— Choisir un plan —</option>
          {plans?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.date} ({p.mode}) — {p.status} — {p.slots.length} créneaux
            </option>
          ))}
        </select>

        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <select value={mode} onChange={(e) => setMode(e.target.value as OrderMode)}>
          <option value="J-1">J-1</option>
          <option value="REAL_TIME">Temps réel</option>
        </select>
        <button className="btn-small" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
          Créer / ouvrir
        </button>
        <button
          className="btn-small btn-primary"
          onClick={() => demoMutation.mutate()}
          disabled={demoMutation.isPending}
        >
          {demoMutation.isPending ? 'Chargement…' : 'Charger le scénario de démo'}
        </button>
      </div>

      {createMutation.isError && (
        <div className="status error">
          Impossible de créer le plan ({extractErrorDetail(createMutation.error) ?? 'existe peut-être déjà et est validé'}).
        </div>
      )}

      {plan && (
        <>
          <div className="plan-meta">
            <span>
              Plan du {plan.date} ({plan.mode}) — statut : <strong>{plan.status}</strong>
            </span>
            <label className="csv-upload">
              Importer un CSV
              <input
                type="file"
                accept=".csv"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) csvMutation.mutate(file);
                  e.target.value = '';
                }}
              />
            </label>
            <button
              className="btn-small"
              onClick={() => validateMutation.mutate()}
              disabled={plan.status === 'VALIDATED' || plan.slots.length === 0 || validateMutation.isPending}
            >
              Valider le plan
            </button>
          </div>

          {csvError && <div className="status error">{csvError}</div>}

          {plan.slots.length === 0 ? (
            <p className="module-sub">Aucun créneau. Importez un CSV ou chargez le scénario de démo.</p>
          ) : (
            <table className="deficit-table">
              <thead>
                <tr>
                  <th>Créneau</th>
                  <th>Demande (MW)</th>
                  <th>Production (MW)</th>
                  <th>Imports (MW)</th>
                  <th>Marge (MW)</th>
                  <th>Déficit (MW)</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {plan.slots.map((slot) => (
                  <SlotRow key={slot.id} plan={plan} slot={slot} />
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
