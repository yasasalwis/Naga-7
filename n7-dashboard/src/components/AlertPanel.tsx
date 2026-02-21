import { useState, useEffect } from 'react';
import axios from 'axios';
import { AlertTriangle, Brain, ShieldAlert } from 'lucide-react';
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
}

const API_BASE = import.meta.env.VITE_API_URL;

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

export function AlertPanel() {
    const [alerts, setAlerts] = useState<Alert[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchAlerts = async () => {
            try {
                const response = await axios.get(`${API_BASE}/api/v1/alerts/?limit=50`);
                setAlerts(response.data);
                setError(null);
            } catch (err) {
                console.error('Failed to fetch alerts', err);
                setError('Could not connect to N7-Core API');
            }
        };

        fetchAlerts();
        const interval = setInterval(fetchAlerts, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="alert-panel-container">
            <h2 className="alert-panel-header">
                <AlertTriangle className="alert-panel-title-icon" size={24} />
                Alert Triage
            </h2>

            {error && <div className="alert-panel-error">{error}</div>}

            {alerts.length === 0 && !error && (
                <div className="alert-panel-empty">No alerts detected. System is healthy.</div>
            )}

            <div className="alert-list">
                {alerts.map((alert) => (
                    <div key={alert.alert_id} className={`alert-card ${getSeverityClass(alert.severity)}`}>
                        {/* Header row */}
                        <div className="alert-card-header">
                            <div className="alert-card-badges">
                                <span className={`severity-badge ${getSeverityClass(alert.severity)}`}>
                                    {alert.severity?.toUpperCase()}
                                </span>
                                <span className="threat-score-badge">
                                    Score: {alert.threat_score}
                                </span>
                                {isHoneytoken(alert) && (
                                    <span className="honeytoken-badge">
                                        🍯 HONEYTOKEN
                                    </span>
                                )}
                                {alert.reasoning?.is_multi_stage && (
                                    <span className="multi-stage-badge">
                                        MULTI-STAGE
                                    </span>
                                )}
                            </div>
                            <span className="alert-timestamp">
                                {alert.created_at
                                    ? new Date(alert.created_at + 'Z').toLocaleString()
                                    : '—'}
                            </span>
                        </div>

                        {/* Rule & source */}
                        <div className="alert-rule">
                            <strong>{alert.reasoning?.rule ?? 'Unknown Rule'}</strong>
                            {alert.reasoning?.source && (
                                <span className="alert-source"> — {alert.reasoning.source}</span>
                            )}
                        </div>

                        {/* Description */}
                        {alert.reasoning?.description && (
                            <p className="alert-description">{alert.reasoning.description}</p>
                        )}

                        {/* Affected assets */}
                        {alert.affected_assets?.length > 0 && (
                            <div className="alert-assets">
                                <span className="alert-assets-label">Affected: </span>
                                {alert.affected_assets.join(', ')}
                            </div>
                        )}

                        {/* MITRE tactics */}
                        {(alert.reasoning?.mitre_tactics?.length ?? 0) > 0 && (
                            <div className="alert-mitre">
                                <span className="mitre-label">MITRE: </span>
                                {alert.reasoning.mitre_tactics!.join(', ')}
                                {(alert.reasoning?.mitre_techniques?.length ?? 0) > 0 && (
                                    <span> / {alert.reasoning.mitre_techniques!.join(', ')}</span>
                                )}
                            </div>
                        )}

                        {/* LLM Narrative — AI Analysis box */}
                        {alert.llm_narrative && (
                            <div className="llm-analysis-box">
                                <div className="llm-analysis-header">
                                    <Brain size={16} className="llm-icon" />
                                    <span>AI Analysis</span>
                                </div>
                                <p className="llm-narrative">{alert.llm_narrative}</p>
                                {(alert.llm_mitre_tactic || alert.llm_mitre_technique) && (
                                    <div className="llm-mitre">
                                        {alert.llm_mitre_tactic && (
                                            <span className="llm-mitre-tag">
                                                {alert.llm_mitre_tactic}
                                            </span>
                                        )}
                                        {alert.llm_mitre_technique && (
                                            <span className="llm-mitre-tag">
                                                {alert.llm_mitre_technique}
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Verdict */}
                        {alert.verdict && alert.verdict !== 'pending' && (
                            <div className={`alert-verdict verdict-${alert.verdict}`}>
                                <ShieldAlert size={14} />
                                <span>Verdict: {alert.verdict.replace('_', ' ').toUpperCase()}</span>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
