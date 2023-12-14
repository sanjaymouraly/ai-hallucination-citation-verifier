import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  Activity, AlertCircle, ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronDown,
  CircleHelp, Database, FileCheck2, FileText, GitCompareArrows, Globe2, History, Info, LayoutDashboard,
  LoaderCircle, LockKeyhole, Menu, Moon, Plus, RotateCcw, ScanSearch, Settings2, ShieldAlert, ShieldCheck,
  Sparkles, Upload, X,
} from 'lucide-react';
import { api, downloadExport } from './services/api';
import type { AnalysisDetail, AnalysisSummary, DashboardData, Page, ProviderPreset, ProviderSettings, ReviewQueueItem } from './types';

const statusLabels: Record<string, string> = {
  supported: 'Supported', partially_supported: 'Partially supported', contradicted: 'Contradicted',
  insufficient_evidence: 'Insufficient evidence', citation_missing: 'Citation missing', source_unavailable: 'Source unavailable',
  needs_human_review: 'Needs review', not_applicable: 'Not applicable',
};
const statusDescriptions: Record<string, string> = {
  supported: 'Retrieved evidence matches key details. This is not proof of objective truth.',
  partially_supported: 'Some details match, but the full claim is not established.',
  contradicted: 'Retrieved evidence appears to conflict with the claim; human context review is recommended.',
  insufficient_evidence: 'Available passages do not establish support.',
  citation_missing: 'No citation was linked to this claim.',
  source_unavailable: 'A cited source could not be retrieved; that does not show the claim is false.',
  needs_human_review: 'Automation was uncertain. Review the source passage and context.',
  not_applicable: 'This text is not a checkable factual proposition.',
};
const statusOrder = ['supported', 'partially_supported', 'contradicted', 'insufficient_evidence', 'citation_missing', 'source_unavailable', 'needs_human_review', 'not_applicable'];
const pageTitles: Record<Page, string> = { dashboard: 'Overview', new: 'New analysis', batch: 'Batch evaluation', reviews: 'Human review', history: 'Analysis history', settings: 'Provider settings', help: 'Guide & limitations', result: 'Verification report' };

function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}
function shortDate(value?: string) { return value ? new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—'; }
function displayError(error: unknown) { return error instanceof Error ? error.message : 'Something went wrong. Please retry.'; }
function labelStatus(status: string) { return statusLabels[status] || status.replaceAll('_', ' '); }

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}><span className="status-dot" />{labelStatus(status)}</span>;
}
function Tooltip({ children }: { children: ReactNode }) { return <span className="tooltip-wrap"><Info size={13} /> <span className="tooltip-content">{children}</span></span>; }
function Alert({ children, kind = 'error' }: { children: ReactNode; kind?: 'error' | 'info' | 'success' }) { return <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{kind === 'error' ? <AlertCircle size={17} /> : kind === 'success' ? <CheckCircle2 size={17} /> : <Info size={17} />}<span>{children}</span></div>; }
function Loading({ label = 'Loading…' }: { label?: string }) { return <div className="loading-state"><LoaderCircle className="spin" size={19} />{label}</div>; }

function App() {
  const [page, setPage] = useState<Page>('dashboard');
  const [resultId, setResultId] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const [dark, setDark] = useState(localStorage.getItem('verity_theme') === 'dark');
  const [authRequired, setAuthRequired] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [tokenDraft, setTokenDraft] = useState('');
  const [authError, setAuthError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [provider, setProvider] = useState<ProviderSettings | null>(null);

  const readRoute = useCallback(() => {
    const path = window.location.pathname;
    if (path.startsWith('/analysis/')) { setPage('result'); setResultId(path.slice('/analysis/'.length)); return; }
    const key = path.replace(/^\//, '') as Page;
    setPage(['dashboard', 'new', 'batch', 'reviews', 'history', 'settings', 'help'].includes(key) ? key : 'dashboard');
    setResultId('');
  }, []);
  useEffect(() => { readRoute(); window.addEventListener('popstate', readRoute); return () => window.removeEventListener('popstate', readRoute); }, [readRoute]);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    localStorage.setItem('verity_theme', dark ? 'dark' : 'light');
  }, [dark]);
  useEffect(() => {
    api.authStatus().then((value) => { setAuthRequired(value.required); setAuthReady(true); }).catch(() => setAuthReady(true));
  }, []);
  useEffect(() => { api.provider().then(setProvider).catch(() => undefined); }, [refreshKey]);

  const navigate = (next: Page, id?: string) => {
    const path = next === 'result' && id ? `/analysis/${id}` : next === 'dashboard' ? '/' : `/${next}`;
    window.history.pushState({}, '', path);
    setPage(next); setResultId(id || ''); setMobileNav(false); window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior });
  };
  const authenticated = !authRequired || Boolean(sessionStorage.getItem('verity_token'));
  const submitToken = async (event: FormEvent) => {
    event.preventDefault(); setAuthError(''); sessionStorage.setItem('verity_token', tokenDraft);
    try { await api.dashboard(); setTokenDraft(''); }
    catch (error) { sessionStorage.removeItem('verity_token'); setAuthError(displayError(error)); }
  };
  const onCreated = (analysis: AnalysisSummary) => { setRefreshKey((value) => value + 1); navigate('result', analysis.id); };
  const nav = <>
    <div className="brand"><div className="brand-mark"><ShieldCheck size={21} /></div><div><strong>verity</strong><span>Evidence review</span></div></div>
    <div className="workspace-switch"><div className="workspace-avatar">V</div><div><strong>My workspace</strong><span>Private · local</span></div><ChevronDown size={15} /></div>
    <div className="nav-label">WORKSPACE</div>
    <nav className="nav-links" aria-label="Main navigation">
      <NavButton icon={<LayoutDashboard size={18} />} label="Overview" active={page === 'dashboard'} onClick={() => navigate('dashboard')} />
      <NavButton icon={<ScanSearch size={18} />} label="New analysis" active={page === 'new'} onClick={() => navigate('new')} />
      <NavButton icon={<LayersIcon />} label="Batch evaluation" active={page === 'batch'} onClick={() => navigate('batch')} />
      <NavButton icon={<FileCheck2 size={18} />} label="Human review" active={page === 'reviews'} onClick={() => navigate('reviews')} badge={provider?.provider !== 'local' ? undefined : undefined} />
      <NavButton icon={<History size={18} />} label="History" active={page === 'history' || page === 'result'} onClick={() => navigate('history')} />
    </nav>
    <div className="nav-label nav-label-spaced">PREFERENCES</div>
    <nav className="nav-links" aria-label="Preferences">
      <NavButton icon={<Settings2 size={18} />} label="Provider settings" active={page === 'settings'} onClick={() => navigate('settings')} />
      <NavButton icon={<BookOpen size={18} />} label="Guide & limitations" active={page === 'help'} onClick={() => navigate('help')} />
    </nav>
    <div className="sidebar-bottom">
      <div className="local-mode-card"><div className="local-mode-icon"><LockKeyhole size={16} /></div><div><strong>Local-first mode</strong><span>No paid API required</span></div><span className="online-dot" /></div>
      <button className="user-row" onClick={() => setDark((value) => !value)} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}><div className="user-avatar">A</div><div className="user-name"><strong>Analyst</strong><span>Single-user workspace</span></div>{dark ? <Check size={16} /> : <Moon size={16} />}</button>
    </div>
  </>;

  if (!authReady) return <div className="app-loading"><Loading label="Connecting to your workspace…" /></div>;
  if (authRequired && !authenticated) return <div className="auth-screen"><div className="auth-card"><div className="brand-mark"><ShieldCheck size={22} /></div><h1>Workspace access</h1><p>This installation requires a workspace token. The token is held in this browser tab only.</p><form onSubmit={submitToken}><label htmlFor="workspace-token">Access token</label><input id="workspace-token" type="password" value={tokenDraft} onChange={(event) => setTokenDraft(event.target.value)} autoComplete="off" required /><button className="button button-primary" type="submit">Continue <ArrowRight size={16} /></button></form>{authError && <Alert>{authError}</Alert>}</div></div>;

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>{nav}</aside>
    {mobileNav && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileNav(false)} />}
    <div className="app-main">
      <header className="topbar"><button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={19} /></button><div className="breadcrumbs"><span>Workspace</span><span className="crumb-sep">/</span><strong>{pageTitles[page]}</strong></div><div className="topbar-right"><span className="privacy-chip"><span className="online-dot" /> Local mode</span><button className="icon-button" aria-label="Toggle theme" onClick={() => setDark((value) => !value)}>{dark ? <Check size={17} /> : <Moon size={17} />}</button><button className="top-avatar" aria-label="Analyst account">A</button></div></header>
      <main className="page-container">
        {page === 'dashboard' && <DashboardPage onNavigate={navigate} refreshKey={refreshKey} />}
        {page === 'new' && <NewAnalysisPage provider={provider} onCreated={onCreated} />}
        {page === 'batch' && <BatchPage onOpenAnalysis={(id) => navigate('result', id)} />}
        {page === 'reviews' && <ReviewsPage onOpenAnalysis={(id) => navigate('result', id)} />}
        {page === 'history' && <HistoryPage onOpenAnalysis={(id) => navigate('result', id)} refreshKey={refreshKey} />}
        {page === 'settings' && <SettingsPage onSaved={(saved) => { setProvider(saved); setRefreshKey((value) => value + 1); }} />}
        {page === 'help' && <HelpPage />}
        {page === 'result' && resultId && <ResultPage id={resultId} onRefresh={() => setRefreshKey((value) => value + 1)} />}
      </main>
      <footer className="footer-note"><span>Verity evaluates source support—not guaranteed factual truth.</span><span>Built for transparent human review</span></footer>
    </div>
  </div>;
}

function LayersIcon() { return <Database size={18} />; }
function NavButton({ icon, label, active, onClick, badge }: { icon: ReactNode; label: string; active: boolean; onClick: () => void; badge?: string }) {
  return <button className={`nav-link ${active ? 'active' : ''}`} onClick={onClick}>{icon}<span>{label}</span>{badge && <em>{badge}</em>}</button>;
}

function DashboardPage({ onNavigate, refreshKey }: { onNavigate: (page: Page, id?: string) => void; refreshKey: number }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api.dashboard().then(setData).catch((e) => setError(displayError(e))); }, [refreshKey]);
  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Loading label="Loading overview…" />;
  const counts = data.status_counts || {};
  const activeCount = statusOrder.filter((status) => status !== 'not_applicable').reduce((sum, status) => sum + (counts[status] || 0), 0);
  return <div className="page-stack">
    <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-line" />EVIDENCE-FIRST VERIFICATION</div><h1>Good work starts with <span>good evidence.</span></h1><p>Inspect the sources behind AI-generated claims—one citation at a time.</p></div><button className="button button-primary" onClick={() => onNavigate('new')}><Plus size={17} /> New analysis</button></section>
    <div className="truth-banner"><div className="truth-icon"><ShieldAlert size={18} /></div><div><strong>Support is not the same as truth.</strong><span>Verity checks whether retrieved passages support a claim as written. It cannot guarantee that a source is accurate, unbiased, or up to date.</span></div><button className="text-button" onClick={() => onNavigate('help')}>How it works <ArrowUpRight size={14} /></button></div>
    <section className="metric-grid">
      <MetricCard icon={<ScanSearch size={18} />} label="Analyses run" value={data.total_analyses} caption="Saved in this workspace" tone="blue" />
      <MetricCard icon={<FileText size={18} />} label="Claims reviewed" value={data.total_claims} caption="Across all analyses" tone="violet" />
      <MetricCard icon={<CircleHelp size={18} />} label="Need a closer look" value={data.pending_reviews} caption="Flagged for human review" tone="amber" />
      <MetricCard icon={<Database size={18} />} label="Evidence mode" value="Local" caption="Deterministic · no API key" tone="green" />
    </section>
    <div className="dashboard-grid">
      <section className="panel status-panel"><div className="panel-heading"><div><h2>Claim outcomes</h2><p>Distribution across completed reviews</p></div><span className="panel-tag">{activeCount} claims</span></div>
        {activeCount ? <><div className="stacked-bar" aria-label="Status distribution">{statusOrder.filter((status) => status !== 'not_applicable' && counts[status] > 0).map((status) => <span key={status} className={`stacked-segment status-${status}`} style={{ width: `${(counts[status] / activeCount) * 100}%` }} title={`${labelStatus(status)}: ${counts[status]}`} />)}</div><div className="legend-grid">{statusOrder.filter((status) => status !== 'not_applicable').map((status) => <div className="legend-item" key={status}><span className={`legend-dot status-${status}`} /><span>{labelStatus(status)}</span><strong>{counts[status] || 0}</strong></div>)}</div></> : <div className="empty-inline"><div className="empty-icon"><Activity size={19} /></div><strong>No claim outcomes yet</strong><span>Run an analysis to see evidence-support results here.</span></div>}
      </section>
      <section className="panel activity-panel"><div className="panel-heading"><div><h2>Recent analyses</h2><p>Your latest verification runs</p></div><button className="text-button" onClick={() => onNavigate('history')}>View history <ArrowRight size={14} /></button></div>
        {data.recent.length ? <div className="recent-list">{data.recent.slice(0, 5).map((item) => <button key={item.id} className="recent-row" onClick={() => onNavigate('result', item.id)}><div className={`recent-icon recent-${item.status}`}><FileText size={17} /></div><div className="recent-copy"><strong>{item.title}</strong><span>{shortDate(item.created_at)} · {item.total_claims} {item.total_claims === 1 ? 'claim' : 'claims'}</span></div><StatusPill status={item.status === 'completed' ? (Object.entries(item.status_counts).sort((a, b) => b[1] - a[1])[0]?.[0] || item.status) : item.status} /><ArrowUpRight className="recent-arrow" size={15} /></button>)}</div> : <div className="empty-inline"><div className="empty-icon"><History size={19} /></div><strong>Your workspace is ready</strong><span>First, paste an answer or attach a RAG source.</span><button className="text-button" onClick={() => onNavigate('new')}>Create first analysis <ArrowRight size={14} /></button></div>}
      </section>
    </div>
    <section className="workflow-strip"><div className="workflow-icon"><Sparkles size={18} /></div><div><strong>How Verity works</strong><span>Extract claims → resolve your citations → retrieve real passages → show uncertainty → invite human review.</span></div><button className="button button-secondary button-sm" onClick={() => onNavigate('help')}>Explore the guide <ArrowRight size={14} /></button></section>
  </div>;
}
function MetricCard({ icon, label, value, caption, tone }: { icon: ReactNode; label: string; value: string | number; caption: string; tone: string }) {
  return <div className="metric-card"><div className={`metric-icon metric-${tone}`}>{icon}</div><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className="metric-caption">{caption}</div></div>;
}

interface SourceDraft { id: string; title: string; url: string; content: string; }
const demoText = 'Acme Robotics opened 12 new offices in 2024 and increased revenue by 25% compared with 2023 [S1].\nThe company reported $45 million in revenue in 2024 [S2].\nAcme Robotics launched its first lunar research station in 2025 [S3].';
const demoSources: SourceDraft[] = [
  { id: 'S1', title: 'Acme Robotics annual update', url: '', content: 'Acme Robotics opened 12 new offices in 2024. Revenue rose by 25% compared with 2023, according to the company annual update.' },
  { id: 'S2', title: 'Acme Robotics revenue release', url: '', content: 'Acme Robotics reported revenue of $45 million in 2024.' },
  { id: 'S3', title: 'Acme Robotics news', url: '', content: 'Acme Robotics announced an investment in laboratory automation. The release contains no information about a lunar research station.' },
];

function NewAnalysisPage({ provider, onCreated }: { provider: ProviderSettings | null; onCreated: (analysis: AnalysisSummary) => void }) {
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [evidenceFiles, setEvidenceFiles] = useState<File[]>([]);
  const [sources, setSources] = useState<SourceDraft[]>([]);
  const [mode, setMode] = useState<'citation_audit' | 'evidence_discovery'>('citation_audit');
  const [title, setTitle] = useState('');
  const [useAi, setUseAi] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const fillExample = () => { setText(demoText); setSources(demoSources.map((item) => ({ ...item }))); setTitle('Acme Robotics — sample source audit'); setFile(null); setEvidenceFiles([]); };
  const addSource = () => setSources((items) => [...items, { id: `S${items.length + 1}`, title: '', url: '', content: '' }]);
  const updateSource = (index: number, field: keyof SourceDraft, value: string) => setSources((items) => items.map((item, i) => i === index ? { ...item, [field]: value } : item));
  const removeSource = (index: number) => setSources((items) => items.filter((_, i) => i !== index));
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setLoading(true);
    try {
      let analysis: AnalysisSummary;
      const validSources = sources.filter((source) => source.content.trim()).map((source) => ({ id: source.id.trim() || undefined, title: source.title.trim() || 'User-provided evidence', url: source.url.trim() || undefined, content: source.content }));
      if (file || evidenceFiles.length) {
        const form = new FormData(); form.set('text', text); form.set('title', title); form.set('mode', mode); form.set('use_ai', String(useAi)); form.set('confirm_external_processing', String(confirmed));
        if (file) form.set('input_file', file);
        evidenceFiles.forEach((item) => form.append('evidence_files', item));
        form.set('sources_json', JSON.stringify(validSources));
        analysis = await api.createUpload(form);
      } else {
        analysis = await api.createAnalysis({ text, title: title || undefined, mode, sources: validSources, use_ai: useAi, confirm_external_processing: confirmed });
      }
      onCreated(analysis);
    } catch (e) { setError(displayError(e)); }
    finally { setLoading(false); }
  };
  const chars = text.length;
  return <div className="page-stack">
    <section className="page-intro"><div className="eyebrow"><span className="eyebrow-line" />START A REVIEW</div><h1>Verify an AI-generated answer</h1><p>Paste the response, attach the sources it cites, and inspect the claim-by-claim evidence trail.</p></section>
    <form className="analysis-layout" onSubmit={submit}>
      <div className="analysis-main-column">
        <section className="panel form-panel"><div className="step-heading"><span className="step-number">1</span><div><h2>Answer or document</h2><p>Paste the full AI response. Citation markers such as <code>[1]</code> and <code>[S1]</code> help associate sources.</p></div><button type="button" className="text-button sample-button" onClick={fillExample}><Sparkles size={14} /> Load sample</button></div>
          <div className="field-row"><label className="field-label" htmlFor="analysis-title">Analysis name <span>optional</span></label><input id="analysis-title" className="text-input" placeholder="e.g. Q3 market summary citation audit" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={240} /></div>
          <label className="field-label" htmlFor="response-text">AI-generated text <span className="char-count">{chars.toLocaleString()} / 200,000</span></label>
          <textarea id="response-text" className="response-textarea" value={text} onChange={(e) => setText(e.target.value)} placeholder={'Paste an answer or report here…\n\nExample: The study reported a 12% increase in 2024 [1].'} maxLength={200000} rows={12} />
          <div className="upload-row"><label className="upload-button"><Upload size={15} /><span>{file ? file.name : 'Upload input document'}</span><input type="file" accept=".txt,.md,.pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>{file && <button className="icon-button small" type="button" aria-label="Remove input file" onClick={() => setFile(null)}><X size={15} /></button>}<span className="helper-text">TXT · Markdown · PDF · DOCX · 10 MB max</span></div>
        </section>
        <section className="panel form-panel"><div className="step-heading"><span className="step-number">2</span><div><h2>Verification mode</h2><p>Choose what the system should treat as evidence.</p></div></div>
          <div className="mode-cards"><button type="button" className={`mode-card ${mode === 'citation_audit' ? 'selected' : ''}`} onClick={() => setMode('citation_audit')}><span className="mode-radio" /><div><strong>Citation audit</strong><span>Only assess sources cited in the response. Missing references stay missing.</span></div><FileCheck2 size={18} /></button><button type="button" className={`mode-card ${mode === 'evidence_discovery' ? 'selected' : ''}`} onClick={() => setMode('evidence_discovery')}><span className="mode-radio" /><div><strong>Evidence discovery</strong><span>Also assess the attached reference/RAG files as independent evidence.</span></div><Globe2 size={18} /></button></div>
        </section>
        <section className="panel form-panel"><div className="step-heading"><span className="step-number">3</span><div><h2>Attach source material <span className="optional-label">optional</span></h2><p>Paste retrieved RAG passages or upload source documents. Use a source ID like <code>S1</code> in the answer to link a passage explicitly.</p></div><button type="button" className="text-button add-source" onClick={addSource}><Plus size={14} /> Add source</button></div>
          {sources.length === 0 && evidenceFiles.length === 0 ? <div className="source-drop"><div className="source-drop-icon"><Database size={19} /></div><div><strong>No attached evidence yet</strong><span>We will fetch public URLs cited in the text. You can also attach local reference passages.</span></div><label className="button button-secondary button-sm"><Upload size={14} /> Add source files<input type="file" accept=".txt,.md,.pdf,.docx" multiple onChange={(e) => setEvidenceFiles(Array.from(e.target.files || []))} /></label></div> : null}
          {sources.map((source, index) => <div className="source-editor" key={`${index}-${source.id}`}><div className="source-editor-top"><span className="source-id">{source.id || `S${index + 1}`}</span><input aria-label={`Source ${index + 1} title`} className="text-input" placeholder="Source title" value={source.title} onChange={(e) => updateSource(index, 'title', e.target.value)} /><button type="button" className="icon-button small" aria-label="Remove source" onClick={() => removeSource(index)}><X size={15} /></button></div><div className="source-meta-fields"><input className="text-input" aria-label={`Source ${index + 1} identifier`} placeholder="ID, e.g. S1" value={source.id} onChange={(e) => updateSource(index, 'id', e.target.value)} /><input className="text-input" aria-label={`Source ${index + 1} URL`} placeholder="Source URL (optional)" value={source.url} onChange={(e) => updateSource(index, 'url', e.target.value)} /></div><textarea className="source-textarea" aria-label={`Source ${index + 1} passage`} placeholder="Paste the actual source passage. This exact text may be shown as evidence." value={source.content} onChange={(e) => updateSource(index, 'content', e.target.value)} rows={3} /></div>)}
          {evidenceFiles.length > 0 && <div className="attached-files">{evidenceFiles.map((item, index) => <div className="file-chip" key={`${item.name}-${index}`}><FileText size={14} /><span>{item.name}</span><button type="button" aria-label={`Remove ${item.name}`} onClick={() => setEvidenceFiles((items) => items.filter((_, i) => i !== index))}><X size={13} /></button></div>)}</div>}
          {(sources.length > 0 || evidenceFiles.length > 0) && <label className="upload-button source-files-button"><Upload size={14} /><span>Add evidence files</span><input type="file" accept=".txt,.md,.pdf,.docx" multiple onChange={(e) => setEvidenceFiles((items) => [...items, ...Array.from(e.target.files || [])])} /></label>}
        </section>
      </div>
      <aside className="analysis-side-column"><div className="panel run-card"><div className="run-card-icon"><ShieldCheck size={19} /></div><h2>Ready to review?</h2><p>Verity extracts factual claims, resolves nearby citations, and keeps evidence passages traceable to their source.</p><div className="run-checks"><span><CheckCircle2 size={15} /> Claim-level results</span><span><CheckCircle2 size={15} /> Source passage links</span><span><CheckCircle2 size={15} /> Reviewable uncertainty</span></div>
          <label className="field-label" htmlFor="provider-select">Assessment provider</label><div className="provider-inline"><span className="provider-status-dot" />{provider?.provider === 'local' || !provider ? 'Local deterministic rules' : provider.provider + (provider.model ? ` · ${provider.model}` : '')}</div>
          <label className="checkbox-row"><input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} /><span><strong>Use optional AI-assisted assessment</strong><small>Send claims and retrieved passages to the configured provider. The local assessment remains as fallback.</small></span></label>
          {useAi && provider?.provider && provider.provider !== 'local' && <label className="checkbox-row confirm-row"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /><span><strong>Allow external processing</strong><small>This may send submitted claim text and retrieved evidence to {provider.provider}.</small></span></label>}
          {error && <Alert>{error}</Alert>}
          <button className="button button-primary run-button" type="submit" disabled={loading || (!text.trim() && !file)}>{loading ? <><LoaderCircle className="spin" size={16} /> Queuing analysis…</> : <>Start analysis <ArrowRight size={16} /></>}</button><div className="run-footnote"><LockKeyhole size={13} /> Input and source text stay in this workspace unless cloud processing is explicitly enabled.</div>
        </div><div className="side-note"><Info size={15} /><span>Unsupported, outdated, or biased sources can still linguistically support a claim.</span></div></aside>
    </form>
  </div>;
}

function BatchPage({ onOpenAnalysis }: { onOpenAnalysis: (id: string) => void }) {
  const [jsonText, setJsonText] = useState(JSON.stringify({ items: [{ title: 'Response A', text: 'Example claim text [S1].', sources: [{ id: 'S1', title: 'Local fixture', content: 'The source passage supports the example claim text.' }] }, { title: 'Response B', text: 'Another claim without a citation.' }] }, null, 2));
  const [result, setResult] = useState<{ batch_id: string; total: number; complete: boolean; counts: Record<string, number>; items: AnalysisSummary[] } | null>(null);
  const [useAi, setUseAi] = useState(false); const [confirmed, setConfirmed] = useState(false); const [error, setError] = useState(''); const [loading, setLoading] = useState(false);
  const start = async () => {
    setError(''); setLoading(true);
    try { const parsed = JSON.parse(jsonText); const created = await api.createBatch({ ...parsed, use_ai: useAi, confirm_external_processing: confirmed }); setResult({ batch_id: created.batch_id, total: created.total, complete: false, counts: {}, items: created.items }); }
    catch (e) { setError(e instanceof SyntaxError ? 'The batch input is not valid JSON.' : displayError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (!result || result.complete) return; const timer = window.setInterval(() => api.batch(result.batch_id).then(setResult).catch((e) => setError(displayError(e))), 1400); return () => window.clearInterval(timer); }, [result?.batch_id, result?.complete]);
  return <div className="page-stack"><section className="page-intro"><div className="eyebrow"><span className="eyebrow-line" />MULTI-RESPONSE WORKFLOW</div><h1>Batch evaluation</h1><p>Queue up to 25 separate response-and-source pairs. Cloud model processing stays opt-in.</p></section><div className="batch-layout"><section className="panel form-panel"><div className="panel-heading"><div><h2>Batch input</h2><p>JSON with an <code>items</code> array; each item accepts <code>text</code>, <code>title</code>, <code>mode</code>, and <code>sources</code>.</p></div></div><textarea className="code-textarea" value={jsonText} onChange={(e) => setJsonText(e.target.value)} spellCheck={false} aria-label="Batch JSON input" rows={16} /><div className="button-row"><button className="button button-secondary" onClick={() => setJsonText(JSON.stringify({ items: [{ title: 'Revision A', text: demoText, mode: 'citation_audit', sources: demoSources.map(({ id, title, url, content }) => ({ id, title, url: url || undefined, content })) }, { title: 'Revision B', text: demoText.replace('12 new offices', '14 new offices'), mode: 'citation_audit', sources: demoSources.map(({ id, title, url, content }) => ({ id, title, url: url || undefined, content })) }] }, null, 2))}>Load local example</button><button className="button button-primary" onClick={start} disabled={loading}>{loading ? <LoaderCircle className="spin" size={16} /> : <ScanSearch size={16} />} Run batch</button></div><label className="checkbox-row batch-ai"><input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} /><span><strong>Use configured AI provider</strong><small>Bulk calls may incur provider charges; keep this off for the local, no-paid-API workflow.</small></span></label>{useAi && <label className="checkbox-row confirm-row"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /><span><strong>Confirm external processing</strong><small>Allow each response and retrieved passage to be sent to the provider.</small></span></label>}{error && <Alert>{error}</Alert>}</section>
      <aside className="panel batch-aside"><div className="batch-aside-icon"><Database size={20} /></div><h2>How batch jobs work</h2><ol className="batch-steps"><li>Each item becomes a saved analysis.</li><li>Jobs are processed by the durable local worker.</li><li>Results remain separate and exportable.</li><li>Use History to compare later revisions.</li></ol><div className="small-notice"><ShieldAlert size={15} /><span>External bulk processing is never silently enabled.</span></div></aside></div>
      {result && <section className="panel batch-results"><div className="panel-heading"><div><h2>Batch progress</h2><p>{result.complete ? 'All jobs have finished.' : 'The worker is processing the queued analyses.'} · {result.total} items</p></div><StatusPill status={result.complete ? 'completed' : 'running'} /></div><div className="batch-progress"><span style={{ width: `${result.total ? ((result.counts.completed || 0) + (result.counts.failed || 0) + (result.counts.cancelled || 0)) / result.total * 100 : 0}%` }} /></div><div className="batch-item-list">{result.items.map((item) => <button key={item.id} className="batch-item" onClick={() => onOpenAnalysis(item.id)}><div><strong>{item.title}</strong><small>{item.total_claims} claims · {item.status === 'running' ? `${item.progress}% complete` : item.status}</small></div><StatusPill status={item.status} /><ArrowRight size={15} /></button>)}</div></section>}
    </div>;
}

function ReviewsPage({ onOpenAnalysis }: { onOpenAnalysis: (id: string) => void }) {
  const [items, setItems] = useState<ReviewQueueItem[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [filter, setFilter] = useState('pending'); const [active, setActive] = useState<string | null>(null); const [decision, setDecision] = useState('supported'); const [notes, setNotes] = useState(''); const [saving, setSaving] = useState(false); const [savedMessage, setSavedMessage] = useState('');
  const load = useCallback(() => { setLoading(true); api.reviewQueue(filter).then((data) => setItems(data.items)).catch((e) => setError(displayError(e))).finally(() => setLoading(false)); }, [filter]);
  useEffect(() => { load(); }, [load]);
  const submit = async (id: string) => { setSaving(true); setError(''); try { await api.addReview(id, { decision, notes, reviewer: 'Analyst' }); setSavedMessage('Review decision saved. Model-generated findings remain unchanged; the human decision is recorded separately.'); setActive(null); setNotes(''); load(); } catch (e) { setError(displayError(e)); } finally { setSaving(false); } };
  return <div className="page-stack"><section className="page-intro"><div className="eyebrow"><span className="eyebrow-line" />HUMAN-IN-THE-LOOP</div><h1>Review uncertain findings</h1><p>Record a human decision with notes. It is saved separately from the automated assessment and preserved in review history.</p></section>
    {savedMessage && <Alert kind="success">{savedMessage}</Alert>}{error && <Alert>{error}</Alert>}
    <div className="filter-row"><div className="filter-tabs"><button className={filter === 'pending' ? 'selected' : ''} onClick={() => setFilter('pending')}>Pending</button><button className={filter === 'all' ? 'selected' : ''} onClick={() => setFilter('all')}>All claims</button></div><span className="muted-label">{items.length} findings</span></div>
    {loading ? <Loading label="Loading review queue…" /> : items.length ? <div className="review-list">{items.map((item) => <article className="panel review-card" key={item.id}><div className="review-card-top"><div><div className="review-analysis-label">{item.analysis_title} <button className="inline-link" onClick={() => onOpenAnalysis(item.analysis_id)}>Open analysis <ArrowUpRight size={13} /></button></div><blockquote>{item.claim}</blockquote></div><StatusPill status={item.status} /></div><p className="review-reason">{item.reasoning}</p>{item.evidence[0] && <div className="review-evidence"><span>Retrieved passage · {item.evidence[0].source_title}</span><p>“{item.evidence[0].text}”</p></div>}{item.latest_review && <div className="previous-review"><CheckCircle2 size={15} /><span>Last review: <strong>{labelStatus(item.latest_review.decision)}</strong> by {item.latest_review.reviewer} · {formatDate(item.latest_review.created_at)}{item.latest_review.notes && ` — “${item.latest_review.notes}”`}</span></div>}
        {active === item.id ? <div className="review-editor"><label className="field-label" htmlFor={`decision-${item.id}`}>Human decision</label><select id={`decision-${item.id}`} className="text-input" value={decision} onChange={(e) => setDecision(e.target.value)}><option value="supported">Supported by evidence</option><option value="partially_supported">Partially supported</option><option value="contradicted">Contradicted by evidence</option><option value="insufficient_evidence">Insufficient evidence</option><option value="needs_more_evidence">Needs more evidence</option><option value="not_applicable">Not applicable</option></select><label className="field-label" htmlFor={`review-note-${item.id}`}>Review rationale</label><textarea id={`review-note-${item.id}`} className="source-textarea" rows={3} maxLength={5000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Explain the evidence, qualification, or context considered…" /><div className="button-row"><button className="button button-secondary" onClick={() => setActive(null)}>Cancel</button><button className="button button-primary" onClick={() => submit(item.id)} disabled={saving}>{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} Save review</button></div></div> : <div className="review-card-actions"><button className="button button-secondary button-sm" onClick={() => { setActive(item.id); setDecision(item.status === 'needs_human_review' ? 'needs_more_evidence' : item.status); }}><Check size={14} /> Record human decision</button><button className="text-button" onClick={() => onOpenAnalysis(item.analysis_id)}>Open claim details <ArrowRight size={14} /></button></div>}
      </article>)}</div> : <EmptyState icon={<CheckCircle2 size={21} />} title="Nothing waiting for review" description="Claims routed for human review will appear here. You can also review any result from its claim detail panel." />}
  </div>;
}

function HistoryPage({ onOpenAnalysis, refreshKey }: { onOpenAnalysis: (id: string) => void; refreshKey: number }) {
  const [items, setItems] = useState<AnalysisSummary[]>([]); const [total, setTotal] = useState(0); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [search, setSearch] = useState(''); const [selected, setSelected] = useState<string[]>([]); const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);
  const load = useCallback(() => { setLoading(true); api.analyses().then((data) => { setItems(data.items); setTotal(data.total); }).catch((e) => setError(displayError(e))).finally(() => setLoading(false)); }, []);
  useEffect(() => { load(); }, [load, refreshKey]);
  const filtered = items.filter((item) => item.title.toLowerCase().includes(search.toLowerCase()));
  const toggle = (id: string) => setSelected((values) => values.includes(id) ? values.filter((value) => value !== id) : [...values.slice(-1), id]);
  const compare = async () => { if (selected.length !== 2) return; try { setComparison(await api.compare(selected[0], selected[1])); } catch (e) { setError(displayError(e)); } };
  const remove = async (id: string) => { if (!window.confirm('Delete this analysis and its evidence and review history? This cannot be undone.')) return; try { await api.delete(id); load(); } catch (e) { setError(displayError(e)); } };
  const rerun = async (item: AnalysisSummary) => {
    const confirmed = item.use_ai ? window.confirm('Rerunning this analysis may send its claims and retrieved passages to the configured AI provider again. Continue?') : false;
    if (item.use_ai && !confirmed) return;
    try { await api.rerun(item.id, confirmed); load(); } catch (e) { setError(displayError(e)); }
  };
  const exportFile = async (item: AnalysisSummary, format: string) => { try { await downloadExport(item.id, format, item.title); } catch (e) { setError(displayError(e)); } };
  return <div className="page-stack"><section className="page-intro history-intro"><div><div className="eyebrow"><span className="eyebrow-line" />SAVED WORKSPACE</div><h1>Analysis history</h1><p>Reopen, rerun, export, or compare saved verification results.</p></div><div className="history-total"><strong>{total}</strong><span>saved analyses</span></div></section>
    {error && <Alert>{error}</Alert>}
    <section className="panel history-panel"><div className="history-toolbar"><div className="search-box"><ScanSearch size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search analyses…" aria-label="Search analyses" /></div><div className="history-actions"><span className="selection-count">{selected.length}/2 selected</span><button className="button button-secondary button-sm" disabled={selected.length !== 2} onClick={compare}><GitCompareArrows size={14} /> Compare</button></div></div>
      {comparison && <div className="compare-result"><div><strong>Revision comparison</strong><span>{String((comparison.left as { title?: string })?.title)} → {String((comparison.right as { title?: string })?.title)}</span></div><button className="icon-button small" aria-label="Close comparison" onClick={() => setComparison(null)}><X size={15} /></button><p>{(comparison.changes as Record<string, unknown>[]).length} claim changes · {String(comparison.unchanged_claims)} unchanged claims</p>{(comparison.changes as Record<string, unknown>[]).slice(0, 6).map((change, index) => <div className="compare-change" key={index}><span className={`change-pill change-${String(change.change)}`}>{String(change.change)}</span><span>{String(change.claim)}</span><span>{change.old_status ? labelStatus(String(change.old_status)) : '—'} → {change.new_status ? labelStatus(String(change.new_status)) : '—'}</span></div>)}</div>}
      {loading ? <Loading label="Loading analyses…" /> : filtered.length ? <div className="table-wrap"><table className="history-table"><thead><tr><th aria-label="Select for comparison" /><th>Analysis</th><th>Mode</th><th>Claims</th><th>Status overview</th><th>Created</th><th>Actions</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><input type="checkbox" aria-label={`Select ${item.title} for comparison`} checked={selected.includes(item.id)} onChange={() => toggle(item.id)} /></td><td><button className="table-title" onClick={() => onOpenAnalysis(item.id)}>{item.title}</button><span className="table-id">{item.id.slice(0, 8)}</span></td><td><span className="mode-tag">{item.mode === 'citation_audit' ? 'Citation audit' : 'Evidence discovery'}</span></td><td>{item.total_claims}</td><td><StatusPill status={item.status === 'completed' ? dominantStatus(item.status_counts) : item.status} /></td><td>{formatDate(item.created_at)}</td><td><div className="table-actions"><button className="icon-button small" onClick={() => onOpenAnalysis(item.id)} title="Open analysis" aria-label="Open analysis"><ArrowUpRight size={15} /></button><button className="icon-button small" onClick={() => exportFile(item, 'json')} title="Export JSON" aria-label="Export JSON"><ArrowDownToLine size={15} /></button><button className="icon-button small" onClick={() => rerun(item)} title="Rerun analysis" aria-label="Rerun analysis"><RotateCcw size={15} /></button><button className="icon-button small danger-hover" onClick={() => remove(item.id)} title="Delete analysis" aria-label="Delete analysis"><X size={15} /></button></div></td></tr>)}</tbody></table></div> : <EmptyState icon={<History size={21} />} title="No analyses found" description={search ? 'Try a different search.' : 'Your completed and in-progress analyses will be saved here.'} />}
    </section><div className="history-help"><Info size={14} />Source text is retained with each saved analysis so findings remain traceable. Delete an analysis to remove its associated records.</div>
  </div>;
}
function dominantStatus(counts: Record<string, number>) { return statusOrder.filter((status) => status !== 'not_applicable').sort((a, b) => (counts[b] || 0) - (counts[a] || 0))[0] || 'completed'; }

function ResultPage({ id, onRefresh }: { id: string; onRefresh: () => void }) {
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [selectedId, setSelectedId] = useState(''); const [filter, setFilter] = useState('all'); const [search, setSearch] = useState(''); const [decision, setDecision] = useState('needs_more_evidence'); const [notes, setNotes] = useState(''); const [reviewOpen, setReviewOpen] = useState(false); const [saving, setSaving] = useState(false); const [saved, setSaved] = useState(''); const [exporting, setExporting] = useState(false);
  const load = useCallback(() => { api.analysis(id).then((data) => { setAnalysis(data); if (!selectedId && data.claims.length) setSelectedId(data.claims[0].id); setError(''); }).catch((e) => setError(displayError(e))).finally(() => setLoading(false)); }, [id, selectedId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (!analysis || !['queued', 'running'].includes(analysis.status)) return; const timer = window.setInterval(load, 1200); return () => window.clearInterval(timer); }, [analysis?.status, load]);
  const currentClaim = analysis?.claims.find((claim) => claim.id === selectedId) || analysis?.claims[0];
  const filteredClaims = useMemo(() => (analysis?.claims || []).filter((claim) => (filter === 'all' || claim.status === filter) && `${claim.text} ${claim.normalized_text}`.toLowerCase().includes(search.toLowerCase())), [analysis?.claims, filter, search]);
  const submitReview = async () => { if (!currentClaim) return; setSaving(true); setError(''); try { await api.addReview(currentClaim.id, { decision, notes, reviewer: 'Analyst' }); setSaved('Human review saved separately from the automated finding.'); setReviewOpen(false); setNotes(''); load(); onRefresh(); } catch (e) { setError(displayError(e)); } finally { setSaving(false); } };
  const exportFile = async (format: string) => { if (!analysis) return; setExporting(true); try { await downloadExport(analysis.id, format, analysis.title); } catch (e) { setError(displayError(e)); } finally { setExporting(false); } };
  const cancel = async () => { try { await api.cancel(id); load(); } catch (e) { setError(displayError(e)); } };
  if (loading && !analysis) return <Loading label="Loading verification report…" />;
  if (error && !analysis) return <Alert>{error}</Alert>;
  if (!analysis) return null;
  const counts = analysis.status_counts || {};
  return <div className="page-stack result-page"><section className="result-heading"><div><button className="back-link" onClick={() => window.history.length > 1 ? window.history.back() : (window.location.href = '/history')}><ArrowRight className="back-arrow" size={14} /> Back to history</button><div className="eyebrow"><span className="eyebrow-line" />VERIFICATION REPORT</div><h1>{analysis.title}</h1><p>{analysis.mode === 'citation_audit' ? 'Citation audit' : 'Evidence discovery'} · Created {formatDate(analysis.created_at)} · {analysis.claims.length} claims</p></div><div className="result-toolbar"><StatusPill status={analysis.status} /><div className="export-wrap"><button className="button button-secondary" onClick={() => exportFile('markdown')} disabled={exporting}><ArrowDownToLine size={15} /> Export <ChevronDown size={14} /></button><div className="export-menu"><button onClick={() => exportFile('json')}>JSON report</button><button onClick={() => exportFile('csv')}>CSV</button><button onClick={() => exportFile('markdown')}>Markdown</button><button onClick={() => exportFile('html')}>HTML</button></div></div></div></section>
    {error && <Alert>{error}</Alert>}{saved && <Alert kind="success">{saved}</Alert>}
    {analysis.status === 'queued' || analysis.status === 'running' ? <div className="panel job-progress"><div className="job-progress-top"><div className="job-spinner"><LoaderCircle className="spin" size={18} /></div><div><strong>{analysis.status === 'queued' ? 'Waiting for the local worker' : 'Evidence review in progress'}</strong><span>Job {analysis.id.slice(0, 8)} · {analysis.progress}%</span></div><button className="button button-secondary button-sm" onClick={cancel}>Cancel job</button></div><div className="progress-track"><span style={{ width: `${analysis.progress}%` }} /></div><p>The job runs in the background; you can safely revisit this report later.</p></div> : null}
    {analysis.status === 'failed' && <Alert>Analysis did not complete. {analysis.error || 'Review the server logs for diagnostics.'} <button className="inline-link" onClick={() => { const confirmed = analysis.use_ai ? window.confirm('Retrying may send this analysis to the configured AI provider again. Continue?') : false; if (analysis.use_ai && !confirmed) return; api.rerun(id, confirmed).then(load).catch((e) => setError(displayError(e))); }}>Retry</button></Alert>}
    <div className="result-summary-grid"><div className="result-summary-card"><span>Total claims</span><strong>{analysis.claims.length}</strong><small>Independent factual spans</small></div>{statusOrder.filter((status) => status !== 'not_applicable').slice(0, 5).map((status) => <div className={`result-summary-card summary-${status}`} key={status}><span>{labelStatus(status)}</span><strong>{counts[status] || 0}</strong><small>{status === 'supported' ? 'Not a truth guarantee' : status === 'source_unavailable' ? 'Not proof of falsity' : statusDescriptions[status]?.split('.')[0]}</small></div>)}</div>
    <div className="result-layout"><div className="result-left-column"><section className="panel original-panel"><div className="panel-heading"><div><h2>Original response</h2><p>Extracted claim spans are highlighted in context.</p></div><span className="panel-tag">{analysis.input_text.length.toLocaleString()} chars</span></div><div className="original-text">{highlightText(analysis.input_text, analysis.claims, selectedId)}</div><div className="highlight-legend"><span><i className="highlight-selected" />Selected claim</span><span><i className="highlight-other" />Other extracted claims</span></div></section>
      <section className="panel claims-panel"><div className="panel-heading claims-heading"><div><h2>Claim findings <span className="count-bubble">{analysis.claims.length}</span></h2><p>Choose a claim to inspect the actual source evidence.</p></div></div><div className="claims-controls"><div className="search-box"><ScanSearch size={15} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search claims…" aria-label="Search claims" /></div><select aria-label="Filter claims by status" className="filter-select" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All statuses</option>{statusOrder.map((status) => <option key={status} value={status}>{labelStatus(status)} ({counts[status] || 0})</option>)}</select></div>{filteredClaims.length ? <div className="claim-list">{filteredClaims.map((claim) => <button className={`claim-list-item ${currentClaim?.id === claim.id ? 'selected' : ''}`} key={claim.id} onClick={() => { setSelectedId(claim.id); setReviewOpen(false); }}><div className="claim-list-top"><span className="claim-index">{String(claim.ordinal).padStart(2, '0')}</span><StatusPill status={claim.status} /></div><p>{claim.text}</p><div className="claim-list-meta"><span>{claim.citations.length} citation{claim.citations.length === 1 ? '' : 's'}</span><span>{claim.evidence.length} passage{claim.evidence.length === 1 ? '' : 's'}</span><span className="uncertainty-tag">{claim.uncertainty} certainty</span></div></button>)}</div> : <div className="empty-inline"><strong>No claims match these filters</strong><span>Change the search or status filter.</span></div>}</section>
      </div>
      <div className="result-right-column">{currentClaim ? <ClaimDetail claim={currentClaim} analysisId={analysis.id} onReview={() => { setDecision(currentClaim.status === 'supported' ? 'supported' : 'needs_more_evidence'); setReviewOpen(true); }} /> : <div className="panel detail-panel"><EmptyState icon={<FileCheck2 size={21} />} title="No claim selected" description="Extracted claims appear here when the job finishes." /></div>}
        {currentClaim && reviewOpen && <section className="panel review-editor detail-review"><div className="panel-heading"><div><h2>Human review</h2><p>Saved as a separate reviewer decision.</p></div><button className="icon-button small" onClick={() => setReviewOpen(false)} aria-label="Close review"><X size={15} /></button></div><label className="field-label">Decision</label><select className="text-input" value={decision} onChange={(e) => setDecision(e.target.value)}><option value="supported">Supported</option><option value="partially_supported">Partially supported</option><option value="contradicted">Contradicted</option><option value="insufficient_evidence">Insufficient evidence</option><option value="needs_more_evidence">Needs more evidence</option><option value="not_applicable">Not applicable</option></select><label className="field-label">Notes</label><textarea className="source-textarea" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={5000} placeholder="Why does the evidence support, qualify, or contradict this claim?" /><button className="button button-primary full-width" onClick={submitReview} disabled={saving}>{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} Save human review</button></section>}
      </div></div>
    <section className="report-limitations"><ShieldAlert size={16} /><div><strong>Interpretation note</strong><span>A source passage may support a claim linguistically while being inaccurate, biased, fraudulent, or outdated. Verify source quality, context, and qualifications independently.</span></div><button className="text-button" onClick={() => window.history.pushState({}, '', '/help')}>Read limitations <ArrowUpRight size={13} /></button></section>
  </div>;
}
function highlightText(text: string, claims: AnalysisDetail['claims'], selectedId: string) {
  const ranges = claims.map((claim) => ({ start: Math.max(0, claim.start_char), end: Math.min(text.length, claim.end_char), id: claim.id })).filter((range) => range.end > range.start).sort((a, b) => a.start - b.start);
  const parts: ReactNode[] = []; let cursor = 0;
  for (const range of ranges) {
    const start = Math.max(cursor, range.start); if (start > cursor) parts.push(text.slice(cursor, start));
    const end = Math.max(start, range.end); if (end > start) parts.push(<mark key={`${range.id}-${start}`} className={range.id === selectedId ? 'selected-mark' : 'claim-mark'}>{text.slice(start, end)}</mark>);
    cursor = end;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}
function ClaimDetail({ claim, analysisId, onReview }: { claim: AnalysisDetail['claims'][number]; analysisId: string; onReview: () => void }) {
  return <section className="panel detail-panel"><div className="detail-topline"><span className="detail-index">CLAIM {String(claim.ordinal).padStart(2, '0')}</span><StatusPill status={claim.status} /></div><blockquote className="detail-claim">{claim.text}</blockquote><div className="detail-meaning"><strong>Assessment rationale</strong><p>{claim.reasoning}</p><div className="assessment-meta"><span>Assessor: {claim.assessor}</span><span>Uncertainty: {claim.uncertainty}</span></div></div>
    <div className="detail-section"><div className="detail-section-heading"><h3>Citations <span>{claim.citations.length}</span></h3><Tooltip>Resolved citations are not automatically evidence of support. Inspect the linked passage and its context.</Tooltip></div>{claim.citations.length ? <div className="citation-list">{claim.citations.map((citation) => <div className="citation-item" key={citation.id}><div className="citation-status"><StatusPill status={citation.resolution_status === 'resolved' ? 'supported' : citation.resolution_status === 'unavailable' ? 'source_unavailable' : 'citation_missing'} /><span>{citation.kind.replaceAll('_', ' ')}</span></div><strong>{citation.source?.title || citation.raw}</strong>{citation.url && <a href={citation.url} target="_blank" rel="noopener noreferrer">{citation.url}<ArrowUpRight size={12} /></a>}{citation.title_mismatch && <span className="mismatch-note"><AlertCircle size={13} /> Link label may not match the fetched page title.</span>}{citation.source?.error && <span className="source-error">{citation.source.error}</span>}</div>)}</div> : <div className="empty-detail"><span className="missing-dot" />No citation was associated with this claim.</div>}</div>
    <div className="detail-section"><div className="detail-section-heading"><h3>Retrieved evidence <span>{claim.evidence.length}</span></h3><Tooltip>Quoted text below is an exact extracted passage from the stored source; it is not generated. Similarity is not logical entailment.</Tooltip></div>{claim.evidence.length ? <div className="evidence-list">{claim.evidence.map((item) => <article className="evidence-card" key={item.id}><div className="evidence-source-line"><div className="evidence-file-icon"><FileText size={14} /></div><div><strong>{item.source_title}</strong><span>{item.page ? `Page ${item.page}` : item.source_url ? new URL(item.source_url).hostname : 'User-provided source'}</span></div>{item.source_url && <a className="evidence-open" href={item.source_url} target="_blank" rel="noopener noreferrer" aria-label="Open source"><ArrowUpRight size={14} /></a>}</div><blockquote>“{item.text}”</blockquote><div className="evidence-foot"><span>Source chars {item.start_char}–{item.end_char}</span><span>Passage rank {item.rank}</span></div></article>)}</div> : <div className="empty-detail"><span className="missing-dot" />No sufficiently relevant source passage was retrieved.</div>}</div>
    {claim.reviews.length > 0 && <div className="detail-section"><div className="detail-section-heading"><h3>Human review history <span>{claim.reviews.length}</span></h3></div>{claim.reviews.map((review) => <div className="review-history-row" key={review.id}><CheckCircle2 size={15} /><div><strong>{labelStatus(review.decision)} · {review.reviewer}</strong><span>{formatDate(review.created_at)}{review.notes && ` — ${review.notes}`}</span></div></div>)}</div>}
    <button className="button button-secondary full-width detail-review-button" onClick={onReview}><Check size={15} /> Record human review</button><div className="detail-repro">Analysis {analysisId.slice(0, 8)} · text offsets {claim.start_char}–{claim.end_char}</div>
  </section>;
}

function SettingsPage({ onSaved }: { onSaved: (value: ProviderSettings) => void }) {
  const [settings, setSettings] = useState<ProviderSettings | null>(null); const [catalog, setCatalog] = useState<ProviderPreset[]>([]); const [key, setKey] = useState(''); const [clearKey, setClearKey] = useState(false); const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false); const [testing, setTesting] = useState(false); const [message, setMessage] = useState(''); const [error, setError] = useState(''); const [models, setModels] = useState<string[]>([]); const [modelStatus, setModelStatus] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {    Promise.all([api.provider(), api.providers(), api.modelsStatus()]).then(([provider, catalogData, modelInfo]) => {
      setSettings(provider); setCatalog(catalogData.providers); setModelStatus(modelInfo);
    }).catch((e) => setError(displayError(e))).finally(() => setLoading(false));
  }, []);
  if (loading || !settings) return <Loading label="Loading provider settings…" />;
  const update = (field: keyof ProviderSettings, value: string | number) => setSettings((current) => current ? { ...current, [field]: value } : current);
  const presetFor = (id: string) => catalog.find((item) => item.id === id); const activePreset = presetFor(settings.provider); const payload = (over: { provider?: string; base_url?: string | null; api_key?: string | null; clear_api_key?: boolean; model?: string | null } = {}) => ({ provider: over.provider ?? settings.provider, base_url: over.base_url !== undefined ? over.base_url : (settings.base_url || null), api_key: over.api_key !== undefined ? over.api_key : (key || null), clear_api_key: over.clear_api_key !== undefined ? over.clear_api_key : clearKey, model: over.model !== undefined ? over.model : (settings.model || null), temperature: settings.temperature, max_output_tokens: settings.max_output_tokens, timeout_seconds: settings.timeout_seconds, retries: settings.retries, analysis_token_budget: settings.analysis_token_budget, daily_token_budget: settings.daily_token_budget });
  const save = async (event: FormEvent) => { event.preventDefault(); setError(''); setMessage(''); setSaving(true); try { const saved = await api.saveProvider(payload()); setSettings(saved); setKey(''); setClearKey(false); onSaved(saved); setMessage(saved.secret_storage === 'session_only' ? 'Settings saved. Your API key is held in process memory only; configure APP_ENCRYPTION_KEY to persist it encrypted, or use an environment variable.' : 'Provider settings saved. The secret itself is never returned to the browser.'); } catch (e) { setError(displayError(e)); } finally { setSaving(false); } };
  const runTest = async (over: { provider?: string; base_url?: string | null; api_key?: string | null; clear_api_key?: boolean; model?: string | null } = {}) => {
    setError(''); setMessage(''); setTesting(true);
    try {
      const result = await api.testProvider(payload(over));
      setMessage(result.message); setModels(result.models || []);
      if (!over.model && result.suggested_model) update('model', result.suggested_model);
      return true;
    } catch (e) { setError(displayError(e)); return false; }
    finally { setTesting(false); }
  };
  const test = () => runTest();
  const connect = async (id: string) => {
    const preset = presetFor(id);
    if (!preset) return;
    setError(''); setMessage(''); setModels([]);
    update('provider', id);
    if (preset.base_url) update('base_url', preset.base_url);
    if (!preset.key_required) {
      setKey(''); setClearKey(false);
      const ok = await runTest({ provider: id, base_url: preset.base_url, api_key: null, clear_api_key: false, model: null });
      if (ok) setMessage(`${preset.label} connected. ${preset.model_help}`);
    } else {
      setMessage(`Selected ${preset.label}. Paste the API key below, then test the connection to discover models.`);
    }
  };
  const providerDescription: Record<string, string> = { local: 'Deterministic, local rules. No provider request, model download, or paid API is required.', openai: 'OpenAI official API. A ChatGPT subscription is separate from API access and billing.', anthropic: 'Anthropic Claude official API.', openrouter: 'OpenRouter API. Provider pricing depends on the selected model; check the provider before bulk use.', custom: 'OpenAI-compatible endpoint. Use HTTPS for multi-user deployments.', ollama: 'Ollama local OpenAI-compatible endpoint. Ensure the backend can reach the configured URL.', lm_studio: 'LM Studio local OpenAI-compatible endpoint. Keep its local server access restricted.' };
  return <div className="page-stack settings-page"><section className="page-intro"><div className="eyebrow"><span className="eyebrow-line" />MODEL & CONNECTION CONTROL</div><h1>Provider settings</h1><p>Local deterministic analysis is the default. Cloud model use is a separate, explicit option per analysis.</p></section>
    <section className="panel easy-connect-panel"><div className="panel-heading"><div><h2>Easy connect</h2><p>Choose a provider to prefill its endpoint. Keyless local providers connect immediately and list their models.</p></div></div>
      <div className="provider-catalog">
        {catalog.map((preset) => (
          <button key={preset.id} type="button" className={`provider-card ${settings.provider === preset.id ? 'active' : ''}`} onClick={() => connect(preset.id)}>
            <span className="provider-card-top"><strong>{preset.label}</strong><span className={`cost-badge cost-${preset.cost_tier}`}>{preset.cost_tier === 'free' ? 'Free' : preset.cost_tier === 'usage' ? 'Paid · usage' : 'Cost varies'}</span></span>
            <span className="provider-card-tagline">{preset.tagline}</span>
            <span className="provider-card-meta">{preset.key_required ? 'API key required' : 'No API key'}{preset.base_url ? ` · ${preset.base_url}` : ''}</span>
          </button>
        ))}
      </div>
    </section>
    {error && <Alert>{error}</Alert>}{message && <Alert kind="success">{message}</Alert>}
    <div className="settings-layout"><form className="panel settings-form" onSubmit={save}><div className="panel-heading"><div><h2>AI provider</h2><p>Keys are redacted in API responses and never written to application logs.</p></div><span className="settings-lock"><LockKeyhole size={15} /> Secret-safe</span></div>
      <label className="field-label" htmlFor="provider-choice">Provider</label><select id="provider-choice" className="text-input provider-select" value={settings.provider} onChange={(e) => { update('provider', e.target.value); setModels([]); setMessage(''); }}><option value="local">Local deterministic mode (default)</option><option value="openai">OpenAI API</option><option value="anthropic">Anthropic Claude API</option><option value="openrouter">OpenRouter</option><option value="custom">Custom OpenAI-compatible endpoint</option><option value="ollama">Ollama local endpoint</option><option value="lm_studio">LM Studio local endpoint</option></select><div className="provider-description"><Info size={15} /><span>{activePreset?.description || providerDescription[settings.provider]}</span></div>
      {['custom', 'ollama', 'lm_studio', 'openai', 'openrouter'].includes(settings.provider) && <><label className="field-label" htmlFor="provider-url">API base URL <span>{['openai', 'openrouter'].includes(settings.provider) ? 'optional override' : 'required'}</span></label><input id="provider-url" className="text-input" type="url" placeholder={activePreset?.base_url || 'https://your-provider.example/v1'} value={settings.base_url || ''} onChange={(e) => update('base_url', e.target.value)} /><span className="field-hint">The backend process—not your browser—connects to this address.</span></>}
      {settings.provider !== 'local' && settings.provider !== 'ollama' && settings.provider !== 'lm_studio' && <><label className="field-label" htmlFor="provider-key">API key <span>{settings.has_api_key ? `Configured · ${settings.secret_storage}` : 'Not configured'}</span></label><input id="provider-key" className="text-input" type="password" autoComplete="new-password" value={key} onChange={(e) => setKey(e.target.value)} placeholder={settings.has_api_key ? 'Leave blank to keep the current key' : 'Enter provider API key'} /><span className="field-hint">The saved key cannot be retrieved. Environment variables take precedence for supported providers.</span>{settings.has_api_key && <label className="clear-secret"><input type="checkbox" checked={clearKey} onChange={(e) => setClearKey(e.target.checked)} /> Clear the configured key when saving</label>}</>}
      <label className="field-label" htmlFor="model-id">Model identifier <span>provider-issued</span></label><div className="model-field"><input id="model-id" className="text-input" value={settings.model || ''} onChange={(e) => update('model', e.target.value)} placeholder={settings.provider === 'local' ? 'Not used by deterministic local rules' : 'Test connection to discover available IDs'} list="discovered-models" /><datalist id="discovered-models">{models.map((model) => <option key={model} value={model} />)}</datalist><button type="button" className="button button-secondary button-sm" onClick={test} disabled={testing}>{testing ? <LoaderCircle className="spin" size={15} /> : <Activity size={15} />} Test connection</button></div>{models.length > 0 && <div className="model-list">{models.slice(0, 12).map((model) => <button type="button" key={model} onClick={() => update('model', model)}>{model}</button>)}</div>}
      <div className="settings-grid"><div><label className="field-label" htmlFor="temperature">Temperature</label><input id="temperature" className="text-input" type="number" min="0" max="2" step="0.1" value={settings.temperature} onChange={(e) => update('temperature', Number(e.target.value))} /></div><div><label className="field-label" htmlFor="max-tokens">Max output tokens</label><input id="max-tokens" className="text-input" type="number" min="32" max="8192" step="32" value={settings.max_output_tokens} onChange={(e) => update('max_output_tokens', Number(e.target.value))} /></div><div><label className="field-label" htmlFor="timeout">Timeout (seconds)</label><input id="timeout" className="text-input" type="number" min="3" max="180" value={settings.timeout_seconds} onChange={(e) => update('timeout_seconds', Number(e.target.value))} /></div><div><label className="field-label" htmlFor="retries">Network retries</label><input id="retries" className="text-input" type="number" min="0" max="5" value={settings.retries} onChange={(e) => update('retries', Number(e.target.value))} /></div><div><label className="field-label" htmlFor="analysis-budget">Token budget / analysis</label><input id="analysis-budget" className="text-input" type="number" min="100" max="1000000" step="100" value={settings.analysis_token_budget} onChange={(e) => update('analysis_token_budget', Number(e.target.value))} /></div><div><label className="field-label" htmlFor="daily-budget">Daily token budget</label><input id="daily-budget" className="text-input" type="number" min="100" max="10000000" step="1000" value={settings.daily_token_budget} onChange={(e) => update('daily_token_budget', Number(e.target.value))} /></div></div>
      <div className="budget-note"><Info size={15} /><span>Token estimates are approximate and are for request budgets only. Provider-specific dollar pricing is not estimated unless trustworthy pricing data is available.</span></div><div className="settings-submit"><button className="button button-secondary" type="button" onClick={() => { setKey(''); setClearKey(false); api.provider().then(setSettings); setMessage(''); }}>Reset form</button><button className="button button-primary" type="submit" disabled={saving}>{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} Save settings</button></div></form>
      <aside className="settings-aside"><div className="panel local-provider-card"><div className="local-provider-icon"><ShieldCheck size={19} /></div><span className="eyebrow">DEFAULT MODE</span><h2>Local, by design</h2><p>With no provider configured, Verity uses deterministic claim extraction, lexical passage retrieval, and conservative rule-based assessment. This is an explainable fallback—not a semantic NLI model.</p><div className="local-provider-list"><span><CheckCircle2 size={15} /> No paid API key</span><span><CheckCircle2 size={15} /> No automatic cloud calls</span><span><CheckCircle2 size={15} /> Human-review friendly</span></div></div><div className="panel model-status-card"><div className="panel-heading"><div><h3>Optional local NLP models</h3><p>{String(modelStatus?.mode || 'checking')}</p></div><Sparkles size={17} /></div><p>{String(modelStatus?.message || 'Model status unavailable.')}</p>{settings.daily_usage_estimate !== undefined && <div className="usage-row"><span>Daily estimated tokens</span><strong>{settings.daily_usage_estimate.toLocaleString()} / {settings.daily_token_budget.toLocaleString()}</strong></div>}</div><div className="privacy-callout"><LockKeyhole size={15} /><span>{settings.secret_storage === 'encrypted' ? <>Provider keys are encrypted at rest. Set <code>APP_ENCRYPTION_KEY</code> in <code>.env</code> and keep it private.</> : settings.secret_storage === 'session_only' ? <>The supplied key is process-memory only and will disappear on restart. Set <code>APP_ENCRYPTION_KEY</code> in <code>.env</code> to persist it encrypted.</> : <>No provider key is stored. Keys typed here are never returned to the browser.</>}</span></div></aside></div>
  </div>;
}

function HelpPage() {
  return <div className="page-stack help-page"><section className="page-intro"><div className="eyebrow"><span className="eyebrow-line" />TRANSPARENT BY DESIGN</div><h1>How to read a finding</h1><p>Verity is an evidence-support checker. It does not make truth guarantees.</p></section>
    <div className="help-grid"><section className="panel help-card"><div className="help-card-icon"><ScanSearch size={19} /></div><h2>The workflow</h2><ol><li>Claim spans are extracted from your text and mapped back to original character offsets.</li><li>Citations are parsed from URLs, DOI links, numbered references, footnotes, and local source IDs.</li><li>Public sources are fetched with redirect, size, and network-address checks. Attached passages remain traceable.</li><li>Candidate passages are ranked, then conservatively assessed. Local rules use lexical coverage and explicit mismatch checks.</li><li>Uncertainty is visible. Reviewers can save a separate decision and rationale.</li></ol></section><section className="panel help-card"><div className="help-card-icon amber"><ShieldAlert size={19} /></div><h2>What statuses mean</h2><div className="help-status-list">{statusOrder.map((status) => <div key={status}><StatusPill status={status} /><span>{statusDescriptions[status]}</span></div>)}</div></section><section className="panel help-card full-help"><div className="help-card-icon green"><Database size={19} /></div><h2>Evidence is not truth</h2><p>A source can be inaccurate, fraudulent, biased, outdated, or quoted out of context and still appear to support a claim linguistically. A page that cannot be fetched is not evidence that the claim is false. A high retrieval score means topical similarity, not logical entailment.</p><p>Default local mode is deterministic and uses rules, not a calibrated probability model. Optional sentence-transformer retrieval can improve paraphrase matching when weights are installed; it still does not establish truth. Optional external AI assessment sends content to the configured provider only when explicitly selected and confirmed.</p><p>Use Verity to triage and inspect evidence—not as a substitute for source-quality review, expert judgment, or primary research.</p></section><section className="panel help-card"><div className="help-card-icon violet"><LockKeyhole size={19} /></div><h2>Privacy & security</h2><ul><li>Local mode does not send response content to an AI provider.</li><li>Retrieved webpages and document text are treated as untrusted data; embedded instructions are never executed.</li><li>URL fetching blocks private, loopback, link-local, and metadata IP ranges, and rechecks redirects.</li><li>Uploads are bounded and extracted in-memory. Saved analyses can be deleted from History.</li><li>For multi-user mode, configure individual tokens with <code>APP_API_TOKENS</code> and protect the database and encryption key. Use HTTPS and a reverse proxy; the application does not provide identity federation.</li></ul></section><section className="panel help-card"><div className="help-card-icon"><CircleHelp size={19} /></div><h2>Getting better results</h2><ul><li>Keep one claim per sentence when possible; compound predicates are split heuristically.</li><li>Use <code>[S1]</code> markers with attached local passages for RAG audits.</li><li>Use Citation audit to isolate supplied references; choose Evidence discovery to include attached independent sources.</li><li>Scanned PDFs require OCR before upload. Paywalled pages are not bypassed.</li><li>Check source title mismatch and passage context before relying on an automated label.</li></ul></section></div>
  </div>;
}

function EmptyState({ icon, title, description }: { icon: ReactNode; title: string; description: string }) { return <div className="empty-state"><div className="empty-state-icon">{icon}</div><strong>{title}</strong><span>{description}</span></div>; }

export default App;
