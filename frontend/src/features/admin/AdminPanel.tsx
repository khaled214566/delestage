import { useState, useEffect, useCallback } from 'react';
import {
  getParameters, patchParameters,
  getUsers, createUser, toggleUser,
  getAuditLogs, verifyAuditChain, downloadAuditCsv,
  type ParametersData, type UserData, type AuditLogEntry, type ChainVerifyResponse,
  type UserCreatePayload,
} from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';

type Tab = 'params' | 'users' | 'audit';

// ─── Parameters Tab ──────────────────────────────────────────────────────────

function ParametersTab() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [params, setParams] = useState<ParametersData | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ max_duration_min: 45, rest_time_min: 180, slot_size_min: 30, rotation_warn_pct: 80 });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const d = await getParameters();
    setParams(d);
    setForm({ max_duration_min: d.max_duration_min, rest_time_min: d.rest_time_min, slot_size_min: d.slot_size_min, rotation_warn_pct: d.rotation_warn_pct });
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    setSaving(true);
    setMsg('');
    try {
      const updated = await patchParameters(form);
      setParams(updated);
      setForm({ max_duration_min: updated.max_duration_min, rest_time_min: updated.rest_time_min, slot_size_min: updated.slot_size_min, rotation_warn_pct: updated.rotation_warn_pct });
      setEditing(false);
      setMsg('✅ Paramètres sauvegardés et enregistrés dans le journal d\'audit.');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setMsg('❌ ' + (e.response?.data?.detail ?? 'Erreur de sauvegarde'));
    } finally {
      setSaving(false);
    }
  };

  if (!params) return <div className="admin-loading">Chargement…</div>;

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <div className="header-title-group">
          <h3>Paramètres Système</h3>
          {!isAdmin && (
            <span className="badge-readonly" title="Seuls les administrateurs peuvent modifier les paramètres">
              Lecture seule (Accès réservé ADMIN)
            </span>
          )}
        </div>
        {!editing && isAdmin && (
          <button className="btn-edit" onClick={() => { setEditing(true); setMsg(''); }}>
            Modifier
          </button>
        )}
      </div>

      {msg && <div className={`admin-msg ${msg.startsWith('✅') ? 'admin-msg-ok' : 'admin-msg-err'}`}>{msg}</div>}

      <div className="params-grid">
        <div className="param-card">
          <label>Durée max par tranche (min)</label>
          {editing ? (
            <input type="number" min={1} max={240} value={form.max_duration_min}
              onChange={e => setForm(f => ({ ...f, max_duration_min: +e.target.value }))} />
          ) : (
            <span className="param-value">{params.max_duration_min} min</span>
          )}
          <small>Plage : 1 – 240</small>
        </div>

        <div className="param-card">
          <label>Temps de repos minimum (min)</label>
          {editing ? (
            <input type="number" min={0} max={1440} value={form.rest_time_min}
              onChange={e => setForm(f => ({ ...f, rest_time_min: +e.target.value }))} />
          ) : (
            <span className="param-value">{params.rest_time_min} min</span>
          )}
          <small>Plage : 0 – 1440</small>
        </div>

        <div className="param-card">
          <label>Taille de tranche (min)</label>
          {editing ? (
            <select value={form.slot_size_min} onChange={e => setForm(f => ({ ...f, slot_size_min: +e.target.value }))}>
              <option value={15}>15</option>
              <option value={30}>30</option>
            </select>
          ) : (
            <span className="param-value">{params.slot_size_min} min</span>
          )}
          <small>15 ou 30 uniquement</small>
        </div>

        <div className="param-card">
          <label>Seuil alerte rotation (%)</label>
          {editing ? (
            <input type="number" min={1} max={100} value={form.rotation_warn_pct}
              onChange={e => setForm(f => ({ ...f, rotation_warn_pct: +e.target.value }))} />
          ) : (
            <span className="param-value">{params.rotation_warn_pct}%</span>
          )}
          <small>Plage : 1 – 100</small>
        </div>

        <div className="param-card param-card-wide">
          <label>Pondération régionale (JSON)</label>
          <div className="regional-key">
            {Object.entries(params.regional_key).map(([k, v]) => (
              <span key={k} className="regional-badge">{k}: {(v * 100).toFixed(0)}%</span>
            ))}
          </div>
          <small>Modifiable en base de données uniquement (V1)</small>
        </div>
      </div>

      {editing && (
        <div className="admin-actions">
          <button className="btn-save" onClick={handleSave} disabled={saving}>
            {saving ? 'Sauvegarde…' : '💾 Sauvegarder'}
          </button>
          <button className="btn-cancel" onClick={() => { setEditing(false); setMsg(''); load(); }}>
            Annuler
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Users Tab ───────────────────────────────────────────────────────────────

const ROLES = ['DISPATCHER', 'BCC_OPERATOR', 'CRC_OPERATOR', 'ADMIN'];

const CRC_OPTIONS = [
  { id: 'CRC_N', name: 'CRC Nord (Tunis, Nabeul, Sousse, Bizerte)' },
  { id: 'CRC_S', name: 'CRC Sud (Sfax, Gabès, Gafsa)' },
];

const BCC_OPTIONS = [
  { id: 'BCC1', name: 'BCC1 — Tunis (Grand Tunis)' },
  { id: 'BCC2', name: 'BCC2 — Nabeul (Cap Bon)' },
  { id: 'BCC3', name: 'BCC3 — Sousse (Sahel)' },
  { id: 'BCC4', name: 'BCC4 — Bizerte & Béja (Nord-Ouest)' },
  { id: 'BCC5', name: 'BCC5 — Sfax (Sfax)' },
  { id: 'BCC6', name: 'BCC6 — Gabès & Médenine (Sud-Est)' },
  { id: 'BCC7', name: 'BCC7 — Gafsa & Sud-Ouest' },
];

function UsersTab() {
  const { user: currentUser } = useAuth();
  const isAdmin = currentUser?.role === 'ADMIN';

  const [users, setUsers] = useState<UserData[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<UserCreatePayload>({
    username: '',
    name: '',
    password: '',
    role: 'BCC_OPERATOR',
    scope_type: 'bcc',
    scope_id: 'BCC1',
  });
  const [creating, setCreating] = useState(false);
  const [msg, setMsg] = useState('');

  const handleRoleChange = (newRole: string) => {
    let newScopeType = 'national';
    let newScopeId: string | null = null;

    if (newRole === 'BCC_OPERATOR') {
      newScopeType = 'bcc';
      newScopeId = 'BCC1';
    } else if (newRole === 'CRC_OPERATOR') {
      newScopeType = 'crc';
      newScopeId = 'CRC_N';
    } else {
      newScopeType = 'national';
      newScopeId = null;
    }

    setForm((f) => ({
      ...f,
      role: newRole,
      scope_type: newScopeType,
      scope_id: newScopeId,
    }));
  };

  const load = useCallback(async () => {
    try {
      setUsers(await getUsers());
    } catch {
      setMsg('❌ Accès réservé aux administrateurs.');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = async (id: number) => {
    try {
      const updated = await toggleUser(id);
      setUsers(us => us.map(u => u.id === id ? updated : u));
      setMsg(`✅ Utilisateur ${updated.username} ${updated.is_active ? 'activé' : 'désactivé'}.`);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setMsg('❌ ' + (e.response?.data?.detail ?? 'Erreur'));
    }
  };

  const handleCreate = async () => {
    setCreating(true);
    setMsg('');
    try {
      const user = await createUser(form);
      setUsers(us => [...us, user]);
      setShowCreate(false);
      setForm({
        username: '',
        name: '',
        password: '',
        role: 'BCC_OPERATOR',
        scope_type: 'bcc',
        scope_id: 'BCC1',
      });
      setMsg(`✅ Utilisateur "${user.username}" créé.`);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setMsg('❌ ' + (e.response?.data?.detail ?? 'Erreur de création'));
    } finally {
      setCreating(false);
    }
  };

  const roleBadge = (role: string) => {
    const colors: Record<string, string> = { ADMIN: '#e74c3c', DISPATCHER: '#3498db', CRC_OPERATOR: '#9b59b6', BCC_OPERATOR: '#27ae60' };
    return <span className="role-badge" style={{ backgroundColor: colors[role] ?? '#7f8c8d' }}>{role}</span>;
  };

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <div className="header-title-group">
          <h3>👥 Gestion des Utilisateurs</h3>
          {!isAdmin && (
            <span className="badge-readonly">
              🔒 Lecture seule (Création réservée ADMIN)
            </span>
          )}
        </div>
        {isAdmin && (
          <button className="btn-edit" onClick={() => { setShowCreate(!showCreate); setMsg(''); }}>
            {showCreate ? '✖ Fermer' : '➕ Nouvel utilisateur'}
          </button>
        )}
      </div>

      {msg && <div className={`admin-msg ${msg.startsWith('✅') ? 'admin-msg-ok' : 'admin-msg-err'}`}>{msg}</div>}

      {showCreate && isAdmin && (
        <div className="create-user-form">
          <h4>Créer un compte</h4>
          <div className="form-grid">
            <div className="form-field">
              <label>Nom d'utilisateur</label>
              <input placeholder="ex: sami" value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} />
            </div>
            <div className="form-field">
              <label>Nom complet</label>
              <input placeholder="ex: Sami Ben Ali" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="form-field">
              <label>Mot de passe (≥8 char)</label>
              <input type="password" placeholder="••••••••" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} />
            </div>
            <div className="form-field">
              <label>Rôle</label>
              <select value={form.role} onChange={e => handleRoleChange(e.target.value)}>
                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label>Type de périmètre (automatique)</label>
              <input
                type="text"
                readOnly
                disabled
                value={
                  form.scope_type === 'national'
                    ? 'National (Automatique)'
                    : form.scope_type === 'crc'
                    ? 'CRC Régional (Automatique)'
                    : 'BCC Local (Automatique)'
                }
                style={{ background: '#f8fafc', color: '#4a5568', cursor: 'not-allowed', fontWeight: 500 }}
              />
            </div>
            <div className="form-field">
              <label>Affectation du périmètre</label>
              {form.scope_type === 'national' ? (
                <input
                  type="text"
                  readOnly
                  disabled
                  value="National (Accès à tous les centres)"
                  style={{ background: '#f8fafc', color: '#718096', cursor: 'not-allowed' }}
                />
              ) : form.scope_type === 'crc' ? (
                <select
                  value={form.scope_id ?? 'CRC_N'}
                  onChange={e => setForm(f => ({ ...f, scope_id: e.target.value }))}
                >
                  {CRC_OPTIONS.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              ) : (
                <select
                  value={form.scope_id ?? 'BCC1'}
                  onChange={e => setForm(f => ({ ...f, scope_id: e.target.value }))}
                >
                  {BCC_OPTIONS.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              )}
            </div>
          </div>
          <div className="admin-actions">
            <button className="btn-save" onClick={handleCreate} disabled={creating}>
              {creating ? 'Création…' : 'Créer'}
            </button>
          </div>
        </div>
      )}

      <table className="admin-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Utilisateur</th>
            <th>Nom</th>
            <th>Rôle</th>
            <th>Périmètre</th>
            <th>Créé le</th>
            <th>Statut</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.id} className={u.is_active ? '' : 'user-inactive'}>
              <td>{u.id}</td>
              <td><code>{u.username}</code></td>
              <td>{u.name}</td>
              <td>{roleBadge(u.role)}</td>
              <td>{u.scope_type}{u.scope_id ? ` / ${u.scope_id}` : ''}</td>
              <td>{new Date(u.created_at).toLocaleDateString('fr-FR')}</td>
              <td>
                <span className={`status-dot ${u.is_active ? 'active' : 'inactive'}`}>
                  {u.is_active ? '● Actif' : '○ Inactif'}
                </span>
              </td>
              <td>
                {isAdmin ? (
                  <button className={`btn-toggle ${u.is_active ? 'btn-deactivate' : 'btn-activate'}`}
                    onClick={() => handleToggle(u.id)}>
                    {u.is_active ? 'Désactiver' : 'Activer'}
                  </button>
                ) : (
                  <span className="text-muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Audit Tab ────────────────────────────────────────────────────────────────

function AuditTab() {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState('');
  const [actorFilter, setActorFilter] = useState('');
  const [verifyResult, setVerifyResult] = useState<ChainVerifyResponse | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [loading, setLoading] = useState(false);
  const PAGE_SIZE = 50;

  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAuditLogs(page, PAGE_SIZE, actionFilter || undefined, actorFilter || undefined);
      setItems(res.items);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  }, [page, actionFilter, actorFilter]);

  useEffect(() => { load(); }, [load]);

  const handleVerify = async () => {
    setVerifying(true);
    setVerifyResult(null);
    try {
      setVerifyResult(await verifyAuditChain());
    } finally {
      setVerifying(false);
    }
  };

  const handleExportCsv = async () => {
    setExporting(true);
    try {
      await downloadAuditCsv(actionFilter || undefined, actorFilter || undefined);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      alert('Erreur lors de l\'export CSV : ' + (e.response?.data?.detail ?? 'Échec du téléchargement'));
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const actionColor = (action: string) => {
    if (action.includes('FEEDER')) return '#27ae60';
    if (action.includes('ORDER')) return '#3498db';
    if (action.includes('PARAMETER')) return '#e67e22';
    if (action.includes('USER')) return '#9b59b6';
    if (action.includes('ROTATION')) return '#e74c3c';
    return '#7f8c8d';
  };

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h3>Journal d'Audit et Traçabilité (SHA-256)</h3>
        <div className="audit-toolbar">
          <input placeholder="Filtrer action…" value={actionFilter}
            onChange={e => { setActionFilter(e.target.value); setPage(1); }} />
          <input placeholder="Filtrer acteur…" value={actorFilter}
            onChange={e => { setActorFilter(e.target.value); setPage(1); }} />
          <button className="btn-verify" onClick={handleVerify} disabled={verifying} title="Vérifier l'intégrité cryptographique SHA-256 de toute la chaîne">
            {verifying ? 'Vérification…' : 'Vérifier la chaîne'}
          </button>
          <button
            className="btn-export"
            onClick={handleExportCsv}
            disabled={exporting}
            title="Télécharger l'intégralité du journal d'audit au format tableur CSV"
          >
            {exporting ? 'Téléchargement…' : 'Exporter CSV'}
          </button>
        </div>
      </div>

      <div className="audit-help-box">
        <div className="help-row">
          <span className="help-badge">Vérifier la chaîne</span>
          <span>Contrôle séquentiel des empreintes SHA-256 depuis le bloc initial (seq=1) pour attester de la non-altération du registre.</span>
        </div>
        <div className="help-row">
          <span className="help-badge">Exporter CSV</span>
          <span>Exporte les enregistrements sélectionnés au format CSV pour archivage et audit réglementaire.</span>
        </div>
      </div>

      {verifyResult && (
        <div className={`chain-verify-result ${verifyResult.ok ? 'chain-ok' : 'chain-broken'}`}>
          {verifyResult.ok
            ? `Chaîne intacte — ${verifyResult.total_checked} enregistrements vérifiés avec succès`
            : `Chaîne compromise à seq=${verifyResult.broken_at_seq} (${verifyResult.total_checked} enregistrements vérifiés avant rupture)`}
        </div>
      )}

      <div className="audit-total">
        {loading ? 'Chargement…' : `${total} entrée${total > 1 ? 's' : ''} — Page ${page} / ${totalPages || 1}`}
      </div>

      <div className="audit-table-wrap">
        <table className="admin-table audit-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Horodatage</th>
              <th>Acteur</th>
              <th>Action</th>
              <th>Entité</th>
              <th>ID</th>
              <th>Hash (tronqué)</th>
            </tr>
          </thead>
          <tbody>
            {items.map(entry => (
              <tr key={entry.seq}>
                <td>{entry.seq}</td>
                <td className="audit-ts">{new Date(entry.timestamp).toLocaleString('fr-FR')}</td>
                <td>{entry.actor_name}</td>
                <td>
                  <span className="action-badge" style={{ backgroundColor: actionColor(entry.action) }}>
                    {entry.action}
                  </span>
                </td>
                <td>{entry.entity_type}</td>
                <td><code>{entry.entity_id}</code></td>
                <td><code className="hash-preview">{entry.hash.slice(0, 12)}…</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>◀</button>
          <span>Page {page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>▶</button>
        </div>
      )}
    </div>
  );
}

// ─── Main AdminPanel ─────────────────────────────────────────────────────────

export default function AdminPanel() {
  const [tab, setTab] = useState<Tab>('params');

  const tabs: { key: Tab; label: string }[] = [
    { key: 'params', label: 'Paramètres' },
    { key: 'users',  label: 'Utilisateurs' },
    { key: 'audit',  label: 'Journal d\'Audit' },
  ];

  return (
    <div className="admin-panel">
      <div className="admin-header">
        <h2>Administration du Système</h2>
        <p className="admin-subtitle">Configuration des paramètres d'exploitation, gestion des accès et traçabilité réglementaire (ADMIN)</p>
      </div>

      <div className="admin-tabs">
        {tabs.map(t => (
          <button key={t.key} className={`tab-btn ${tab === t.key ? 'tab-active' : ''}`}
            onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="tab-content">
        {tab === 'params' && <ParametersTab />}
        {tab === 'users'  && <UsersTab />}
        {tab === 'audit'  && <AuditTab />}
      </div>
    </div>
  );
}
