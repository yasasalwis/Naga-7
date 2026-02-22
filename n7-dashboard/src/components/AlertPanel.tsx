/**
 * AlertPanel — Simplified version using shared hooks.
 * The primary alert/incident view is now IncidentPanel.
 * This component is retained for potential embedded use.
 */
import { useState } from 'react';
import {
  Brain, ShieldAlert, Wrench,
  Send, CheckCircle, XCircle, Loader, ChevronDown, ChevronUp,
  Zap, Shield
} from 'lucide-react';
import { useNatsAlerts } from '../hooks/useNatsAlerts';
import { useDispatch } from '../hooks/useDispatch';
import {
  getSeverityClass, isHoneytoken, parseRecommendedActions,
  formatTimestamp, RISK_LABELS,
} from '../utils/alertUtils';
import './AlertPanel.css';

export function AlertPanel() {
  const { alerts, error, activeStrikerCount } = useNatsAlerts();
  const { dispatch, toggleActionSelection, isSelected, handleDispatch } = useDispatch();
  const [expandedRemediation, setExpandedRemediation] = useState<Set<string>>(new Set());
  const [expandedDispatch, setExpandedDispatch] = useState<Set<string>>(new Set());

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
                    <span className="honeytoken-badge">HONEYTOKEN</span>
                  )}
                  {alert.reasoning?.is_multi_stage && (
                    <span className="multi-stage-badge">MULTI-STAGE</span>
                  )}
                </div>
                <span className="alert-timestamp">
                  {formatTimestamp(alert.created_at)}
                </span>
              </div>

              {/* Rule & source */}
              <div className="alert-rule">
                <strong>{alert.reasoning?.rule ?? 'Unknown Rule'}</strong>
                {alert.reasoning?.source && (
                  <span className="alert-source"> &mdash; {alert.reasoning.source}</span>
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

              {/* LLM AI Analysis box */}
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

              {/* LLM Remediation Steps (collapsible) */}
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

              {/* Operator Dispatch Panel */}
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
                      <div className="dispatch-striker-info">
                        <Zap size={12} />
                        <span>
                          {activeStrikerCount > 0
                            ? `${activeStrikerCount} striker${activeStrikerCount !== 1 ? 's' : ''} available`
                            : 'No active strikers \u2014 actions will be queued'}
                        </span>
                      </div>

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
                            <span>Dispatching...</span>
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
                                  ? ` \u2014 queued (${r.action_id.slice(0, 8)}...)`
                                  : ` \u2014 error: ${r.error}`}
                              </span>
                            </div>
                          ))}
                        </div>
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
          );
        })}
      </div>
    </div>
  );
}
