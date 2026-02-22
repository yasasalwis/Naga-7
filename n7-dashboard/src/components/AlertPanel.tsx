import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { connect, jwtAuthenticator, StringCodec } from 'nats.ws';
import type { NatsConnection } from 'nats.ws';
import {
    Brain, ShieldAlert, Wrench,
    Send, CheckCircle, XCircle, Loader, ChevronDown, ChevronUp,
    Zap, Shield
} from 'lucide-react';
import './AlertPanel.css';

interface AlertReasoning {
    rule?: string;
    description?: string;
    source?: string;
    mitre_tactics?: string[];
    mitre_techniques?: string[];
    is_multi_stage?: boolean;
    count?: number;
}

interface Alert {
    id: string;
    alert_id: string;
    created_at: string | null;
    severity: string;
    threat_score: number;
    status: string;
    verdict: string | null;
    affected_assets: string[];
    reasoning: AlertReasoning;
    event_ids: string[];
    llm_narrative: string | null;
    llm_mitre_tactic: string | null;
    llm_mitre_technique: string | null;
    llm_remediation: string | null;
}

interface Striker {
    id: string;
    agent_subtype: string;
    zone: string;
    status: string;
    capabilities: string[];
}

interface RecommendedAction {
    action_type: string;
    label: string;
    description: string;
    parameters: Record<string, unknown>;
    risk: 'low' | 'medium' | 'high';
}

interface DispatchState {
    [alertId: string]: {
        selected: Set<string>;        // selected action_types
        dispatching: boolean;
        result: { action_type: string; action_id: string; status: string; error?: string }[] | null;
    };
}

const API_BASE = import.meta.env.VITE_API_URL;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getSeverityClass(severity: string): string {
    switch (severity?.toLowerCase()) {
        case 'critical': return 'severity-critical';
        case 'high': return 'severity-high';
        case 'medium': return 'severity-medium';
        case 'low': return 'severity-low';
        default: return 'severity-medium';
    }
}

function isHoneytoken(alert: Alert): boolean {
    return (
        alert.threat_score >= 100 ||
        alert.reasoning?.rule === 'Honeytoken File Access' ||
        (alert.reasoning?.mitre_tactics ?? []).includes('TA0009')
    );
}

/**
 * Parse the LLM remediation text into discrete recommended striker actions.
 * Each numbered line (1. ...) is parsed into a recommended action payload.
 * Action type is inferred from keywords in the step text.
 */
function parseRecommendedActions(
    remediation: string | null,
    affectedAssets: string[]
): RecommendedAction[] {
    if (!remediation) return [];

    const target = affectedAssets[0] ?? 'unknown';
    const actions: RecommendedAction[] = [];

    const lines = remediation
        .split('\n')
        .map(l => l.trim())
        .filter(l => /^\d+\./.test(l));

    for (const line of lines) {
        const text = line.replace(/^\d+\.\s*/, '').toLowerCase();

        if (/block|isolat|blacklist|firewall/.test(text) && /ip|host|network/.test(text) && !/full|complet/.test(text)) {
            if (!actions.find(a => a.action_type === 'network_block')) {
                actions.push({
                    action_type: 'network_block',
                    label: 'Block IP / Network',
                    description: line.replace(/^\d+\.\s*/, ''),
                    parameters: { target, duration: 3600 },
                    risk: 'medium',
                });
            }
        } else if (/isolat|quarantin|contain/.test(text) || (/block/.test(text) && /host|machine|system|endpoint/.test(text))) {
            if (!actions.find(a => a.action_type === 'isolate_host')) {
                actions.push({
                    action_type: 'isolate_host',
                    label: 'Isolate Host',
                    description: line.replace(/^\d+\.\s*/, ''),
                    parameters: { target },
                    risk: 'high',
                });
            }
        } else if (/kill|terminat|stop|end/.test(text) && /process|proc/.test(text)) {
            if (!actions.find(a => a.action_type === 'kill_process')) {
                actions.push({
                    action_type: 'kill_process',
                    label: 'Kill Process',
                    description: line.replace(/^\d+\.\s*/, ''),
                    parameters: { target },
                    risk: 'medium',
                });
            }
        } else if (/collect|gather|captur|forensic|evidence|log/.test(text)) {
            if (!actions.find(a => a.action_type === 'collect_evidence')) {
                actions.push({
                    action_type: 'collect_evidence',
                    label: 'Collect Evidence',
                    description: line.replace(/^\d+\.\s*/, ''),
                    parameters: { asset: target, artifacts: ['network_logs', 'auth_logs', 'process_list'] },
                    risk: 'low',
                });
            }
        } else if (/notif|alert|escalat|soc|team/.test(text)) {
            if (!actions.find(a => a.action_type === 'notify')) {
                actions.push({
                    action_type: 'notify',
                    label: 'Notify SOC',
                    description: line.replace(/^\d+\.\s*/, ''),
                    parameters: { channel: 'slack', message: `Alert requires attention: ${target}` },
                    risk: 'low',
                });
            }
        }
    }

    return actions;
}

const RISK_LABELS: Record<string, string> = {
    low: 'Low Risk',
    medium: 'Medium Risk',
    high: 'High Risk — Irreversible',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AlertPanel() {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [strikers, setStrikers] = useState<Striker[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [expandedRemediation, setExpandedRemediation] = useState<Set<string>>(new Set());
    const [expandedDispatch, setExpandedDispatch] = useState<Set<string>>(new Set());
    const [dispatch, setDispatch] = useState<DispatchState>({});

    // ---------------------------------------------------------------------------
    // Data fetching
    // ---------------------------------------------------------------------------

    const fetchAlerts = useCallback(async () => {
        try {
            const response = await axios.get(`${API_BASE}/api/v1/alerts/?limit=50`);
            setAlerts(response.data);
            setError(null);
        } catch (err) {
            console.error('Failed to fetch alerts', err);
            setError('Could not connect to N7-Core API');
        }
    }, []);

    const fetchStrikers = useCallback(async () => {
        try {
            const response = await axios.get(`${API_BASE}/api/v1/agents/strikers`);
            setStrikers(response.data);
        } catch (err) {
            console.warn('Could not fetch striker list', err);
        }
    }, []);

    useEffect(() => {
        let nc: NatsConnection | null = null;
        let isActive = true;

        // Perform initial HTTP fetch for current state
        fetchAlerts();
        fetchStrikers();

        // Connect to NATS WebSockets for live alerts
        const connectNats = async () => {
            try {
                // Fetch dynamic JWT and seed
                const token = localStorage.getItem('token');
                const headers = token ? { Authorization: `Bearer ${token}` } : {};
                const response = await axios.get(`${API_BASE}/api/v1/alerts/ws-token`, { headers });

                if (!isActive) return;

                const { jwt, seed } = response.data;
                const seedBytes = new TextEncoder().encode(seed);

                nc = await connect({
                    servers: 'ws://localhost:9222',
                    authenticator: jwtAuthenticator(() => jwt, seedBytes),
                });

                console.log("Connected to NATS WebSockets for real-time alerts!");
                const sc = StringCodec();

                // Subscribe to critical alerts
                const sub = nc.subscribe("n7.alerts.critical.new");
                for await (const msg of sub) {
                    if (!isActive) break;
                    try {
                        const newAlert = JSON.parse(sc.decode(msg.data));
                        setAlerts(prev => {
                            // Deduplicate
                            const exists = prev.find(a => a.alert_id === newAlert.alert_id);
                            if (exists) return prev;
                            return [newAlert, ...prev].slice(0, 50);
                        });
                    } catch (e) {
                        console.error("Error parsing NATS WebSocket message", e);
                    }
                }
            } catch (err) {
                console.error("NATS WebSocket connection failed. Retrying in 5s...", err);
                if (isActive) {
                    setTimeout(connectNats, 5000);
                }
            }
        };

        connectNats();

        // Keep HTTP polling for strikers
        const strikerInterval = setInterval(fetchStrikers, 15000);

        return () => {
            isActive = false;
            clearInterval(strikerInterval);
            if (nc) {
                nc.close();
            }
        };
    }, [fetchAlerts, fetchStrikers]);

    // ---------------------------------------------------------------------------
    // UI helpers
    // ---------------------------------------------------------------------------

    const toggleRemediation = (alertId: string) => {
        setExpandedRemediation(prev => {
            const next = new Set(prev);
            next.has(alertId) ? next.delete(alertId) : next.add(alertId);
            return next;
        });
    };

    const toggleDispatch = (alertId: string) => {
        setExpandedDispatch(prev => {
            const next = new Set(prev);
            next.has(alertId) ? next.delete(alertId) : next.add(alertId);
            return next;
        });
    };

    const toggleActionSelection = (alertId: string, actionType: string) => {
        setDispatch(prev => {
            const current = prev[alertId] ?? { selected: new Set(), dispatching: false, result: null };
            const selected = new Set(current.selected);
            selected.has(actionType) ? selected.delete(actionType) : selected.add(actionType);
            return { ...prev, [alertId]: { ...current, selected, result: null } };
        });
    };

    const isSelected = (alertId: string, actionType: string): boolean =>
        dispatch[alertId]?.selected?.has(actionType) ?? false;

    // ---------------------------------------------------------------------------
    // Dispatch
    // ---------------------------------------------------------------------------

    const handleDispatch = async (alert: Alert, recommendedActions: RecommendedAction[]) => {
        const selected = dispatch[alert.alert_id]?.selected ?? new Set<string>();
        if (selected.size === 0) return;

        const actionsToSend = recommendedActions
            .filter(a => selected.has(a.action_type))
            .map(a => ({ action_type: a.action_type, parameters: a.parameters }));

        setDispatch(prev => ({
            ...prev,
            [alert.alert_id]: { ...prev[alert.alert_id], dispatching: true, result: null },
        }));

        try {
            const response = await axios.post(
                `${API_BASE}/api/v1/alerts/${alert.alert_id}/dispatch`,
                { actions: actionsToSend, operator_note: 'Dispatched from dashboard' }
            );
            setDispatch(prev => ({
                ...prev,
                [alert.alert_id]: {
                    selected: new Set(),
                    dispatching: false,
                    result: response.data.dispatched,
                },
            }));
        } catch (err) {
            console.error('Dispatch failed', err);
            setDispatch(prev => ({
                ...prev,
                [alert.alert_id]: {
                    ...prev[alert.alert_id],
                    dispatching: false,
                    result: actionsToSend.map(a => ({
                        action_type: a.action_type,
                        action_id: '',
                        status: 'error',
                        error: 'Network error — check Core API',
                    })),
                },
            }));
        }
    };

    // ---------------------------------------------------------------------------
    // Striker availability summary
    // ---------------------------------------------------------------------------

    const activeStrikerCount = strikers.filter(s => s.status === 'active').length;

    // ---------------------------------------------------------------------------
    // Render
    // ---------------------------------------------------------------------------

    return (
        <div className="alert-panel-container">
            <div className="alert-panel-header-row">
                <h2 className="alert-panel-header">
                    <Brain className="alert-panel-title-icon" size={24} />
                    AI Recommendations & Alerts
                </h2>
                <div className="striker-status-pill">
                    <Shield size={14} />
                    <span>{activeStrikerCount} security agent{activeStrikerCount !== 1 ? 's' : ''} ready</span>
                </div>
            </div>

            {error && <div className="alert-panel-error">{error}</div>}

            {alerts.length === 0 && !error && (
                <div className="alert-panel-empty">
                    <CheckCircle size={32} color="var(--accent-success)" style={{ marginBottom: '10px' }} />
                    <p>No active threats detected. Your system is secure.</p>
                </div>
            )}

            <div className="alert-list">
                {alerts.map((alert) => {
                    const recommendedActions = parseRecommendedActions(
                        alert.llm_remediation,
                        alert.affected_assets
                    );
                    const dispatchState = dispatch[alert.alert_id];
                    const isDispatchOpen = expandedDispatch.has(alert.alert_id);

                    return (
                        <div key={alert.alert_id} className={`alert-card ${getSeverityClass(alert.severity)}`}>
                            {/* ---- Header row ---- */}
                            <div className="alert-card-header">
                                <div className="alert-card-badges">
                                    <span className={`severity-badge ${getSeverityClass(alert.severity)}`}>
                                        {alert.severity?.toUpperCase()}
                                    </span>
                                    <span className="threat-score-badge">
                                        Score: {alert.threat_score}
                                    </span>
                                    {isHoneytoken(alert) && (
                                        <span className="honeytoken-badge">🍯 HONEYTOKEN</span>
                                    )}
                                    {alert.reasoning?.is_multi_stage && (
                                        <span className="multi-stage-badge">MULTI-STAGE</span>
                                    )}
                                </div>
                                <span className="alert-timestamp">
                                    {alert.created_at
                                        ? new Date(alert.created_at + 'Z').toLocaleString()
                                        : '—'}
                                </span>
                            </div>

                            {/* ---- Rule & source ---- */}
                            <div className="alert-rule">
                                <strong>{alert.reasoning?.rule ?? 'Unknown Rule'}</strong>
                                {alert.reasoning?.source && (
                                    <span className="alert-source"> — {alert.reasoning.source}</span>
                                )}
                            </div>

                            {/* ---- Description ---- */}
                            {alert.reasoning?.description && (
                                <p className="alert-description">{alert.reasoning.description}</p>
                            )}

                            {/* ---- Affected assets ---- */}
                            {alert.affected_assets?.length > 0 && (
                                <div className="alert-assets">
                                    <span className="alert-assets-label">Affected: </span>
                                    {alert.affected_assets.join(', ')}
                                </div>
                            )}

                            {/* ---- MITRE tactics ---- */}
                            {(alert.reasoning?.mitre_tactics?.length ?? 0) > 0 && (
                                <div className="alert-mitre">
                                    <span className="mitre-label">MITRE: </span>
                                    {alert.reasoning.mitre_tactics!.join(', ')}
                                    {(alert.reasoning?.mitre_techniques?.length ?? 0) > 0 && (
                                        <span> / {alert.reasoning.mitre_techniques!.join(', ')}</span>
                                    )}
                                </div>
                            )}

                            {/* ---- LLM AI Analysis box ---- */}
                            {alert.llm_narrative && (
                                <div className="llm-analysis-box">
                                    <div className="llm-analysis-header">
                                        <Brain size={16} className="llm-icon" />
                                        <span>AI Security Analysis</span>
                                        {(alert.llm_mitre_tactic || alert.llm_mitre_technique) && (
                                            <div className="llm-mitre" title="MITRE ATT&CK Framework categorization">
                                                {alert.llm_mitre_tactic && (
                                                    <span className="llm-mitre-tag">{alert.llm_mitre_tactic}</span>
                                                )}
                                                {alert.llm_mitre_technique && (
                                                    <span className="llm-mitre-tag">{alert.llm_mitre_technique}</span>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                    <p className="llm-narrative">{alert.llm_narrative}</p>
                                </div>
                            )}

                            {/* ---- LLM Remediation Steps (collapsible) ---- */}
                            {alert.llm_remediation && (
                                <div className="llm-remediation-box">
                                    <button
                                        className="llm-remediation-toggle"
                                        onClick={() => toggleRemediation(alert.alert_id)}
                                    >
                                        <Wrench size={14} className="llm-icon" />
                                        <span>
                                            {expandedRemediation.has(alert.alert_id)
                                                ? 'Hide Recommended Steps'
                                                : 'Show Recommended Steps'}
                                        </span>
                                        {expandedRemediation.has(alert.alert_id)
                                            ? <ChevronUp size={14} />
                                            : <ChevronDown size={14} />}
                                    </button>
                                    {expandedRemediation.has(alert.alert_id) && (
                                        <div className="llm-remediation-steps">
                                            {alert.llm_remediation.split('\n').filter(s => s.trim()).map((step, i) => (
                                                <p key={i} className="remediation-step">{step}</p>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* ---- Operator Dispatch Panel ---- */}
                            {recommendedActions.length > 0 && (
                                <div className="dispatch-panel">
                                    <button
                                        className="dispatch-panel-toggle"
                                        onClick={() => toggleDispatch(alert.alert_id)}
                                    >
                                        <Shield size={16} />
                                        <span>
                                            {isDispatchOpen
                                                ? 'Hide Action Menu'
                                                : `Take Action (${recommendedActions.length} recommended)`}
                                        </span>
                                        {isDispatchOpen
                                            ? <ChevronUp size={16} />
                                            : <ChevronDown size={16} />}
                                    </button>

                                    {isDispatchOpen && (
                                        <div className="dispatch-panel-body">
                                            {/* Striker availability */}
                                            <div className="dispatch-striker-info">
                                                <Zap size={12} />
                                                <span>
                                                    {activeStrikerCount > 0
                                                        ? `${activeStrikerCount} striker${activeStrikerCount !== 1 ? 's' : ''} available`
                                                        : 'No active strikers — actions will be queued'}
                                                </span>
                                            </div>

                                            {/* Action selection */}
                                            <div className="dispatch-actions-list">
                                                {recommendedActions.map((action) => {
                                                    const selected = isSelected(alert.alert_id, action.action_type);
                                                    return (
                                                        <label
                                                            key={action.action_type}
                                                            className={`dispatch-action-item ${selected ? 'selected' : ''} risk-${action.risk}`}
                                                        >
                                                            <input
                                                                type="checkbox"
                                                                className="dispatch-action-checkbox"
                                                                checked={selected}
                                                                onChange={() => toggleActionSelection(alert.alert_id, action.action_type)}
                                                                disabled={dispatchState?.dispatching}
                                                            />
                                                            <div className="dispatch-action-info">
                                                                <span className="dispatch-action-label">{action.label}</span>
                                                                <span className={`dispatch-action-risk risk-badge-${action.risk}`}>
                                                                    {RISK_LABELS[action.risk]}
                                                                </span>
                                                                <p className="dispatch-action-desc">{action.description}</p>
                                                            </div>
                                                        </label>
                                                    );
                                                })}
                                            </div>

                                            {/* Dispatch button */}
                                            <button
                                                className="dispatch-btn"
                                                disabled={
                                                    dispatchState?.dispatching ||
                                                    (dispatchState?.selected?.size ?? 0) === 0
                                                }
                                                onClick={() => handleDispatch(alert, recommendedActions)}
                                            >
                                                {dispatchState?.dispatching ? (
                                                    <>
                                                        <Loader size={14} className="spin" />
                                                        <span>Dispatching…</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <Send size={14} />
                                                        <span>
                                                            Dispatch{' '}
                                                            {(dispatchState?.selected?.size ?? 0) > 0
                                                                ? `${dispatchState.selected.size} Action${dispatchState.selected.size !== 1 ? 's' : ''}`
                                                                : '(select actions)'}
                                                        </span>
                                                    </>
                                                )}
                                            </button>

                                            {/* Dispatch results */}
                                            {dispatchState?.result && (
                                                <div className="dispatch-results">
                                                    {dispatchState.result.map((r, i) => (
                                                        <div
                                                            key={i}
                                                            className={`dispatch-result-item ${r.status === 'queued' ? 'success' : 'failure'}`}
                                                        >
                                                            {r.status === 'queued'
                                                                ? <CheckCircle size={13} />
                                                                : <XCircle size={13} />}
                                                            <span>
                                                                <strong>{r.action_type}</strong>
                                                                {r.status === 'queued'
                                                                    ? ` — queued (${r.action_id.slice(0, 8)}…)`
                                                                    : ` — error: ${r.error}`}
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* ---- Verdict ---- */}
                            {alert.verdict && alert.verdict !== 'pending' && (
                                <div className={`alert-verdict verdict-${alert.verdict}`}>
                                    <ShieldAlert size={14} />
                                    <span>Verdict: {alert.verdict.replace('_', ' ').toUpperCase()}</span>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
