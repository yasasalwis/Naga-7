import { useState, useMemo } from 'react';
import {
  Brain, Shield, ChevronDown, ChevronUp,
  Send, CheckCircle, XCircle, Loader,
  ShieldAlert, Zap, Target, Clock,
} from 'lucide-react';
import { useNatsAlerts } from '../hooks/useNatsAlerts';
import { useDispatch } from '../hooks/useDispatch';
import {
  getSeverityClass, isHoneytoken, parseRecommendedActions,
  formatRelativeTime, formatTimestamp, RISK_LABELS,
} from '../utils/alertUtils';
import type { Alert } from '../utils/alertUtils';
import './IncidentPanel.css';

type SeverityFilter = 'all' | 'critical' | 'high' | 'medium' | 'low';
type StatusFilter = 'all' | 'new' | 'acknowledged' | 'resolved';

const SEVERITY_FILTERS: { value: SeverityFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'new', label: 'New' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'resolved', label: 'Resolved' },
];

export function IncidentPanel() {
  const { alerts, error, activeStrikerCount } = useNatsAlerts();
  const { dispatch, toggleActionSelection, isSelected, handleDispatch } = useDispatch();

  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [expandedRemediation, setExpandedRemediation] = useState<Set<string>>(new Set());

  // Filter alerts that have LLM analysis
  const incidents = useMemo(() => {
    return alerts.filter(a => {
      if (!a.llm_narrative) return false;
      if (severityFilter !== 'all' && a.severity !== severityFilter) return false;
      if (statusFilter !== 'all' && a.status !== statusFilter) return false;
      return true;
    });
  }, [alerts, severityFilter, statusFilter]);

  const selectedIncident = incidents.find(a => a.alert_id === selectedIncidentId) ?? incidents[0] ?? null;

  const toggleRemediation = (alertId: string) => {
    setExpandedRemediation(prev => {
      const next = new Set(prev);
      next.has(alertId) ? next.delete(alertId) : next.add(alertId);
      return next;
    });
  };

  return (
    <div className="incident-panel">
      {/* ── Toolbar ── */}
      <div className="incident-toolbar">
        <div className="incident-toolbar-left">
          <div className="incident-filter-group">
            <span className="filter-label">Severity</span>
            <div className="filter-pills">
              {SEVERITY_FILTERS.map(f => (
                <button
                  key={f.value}
                  className={`filter-pill ${severityFilter === f.value ? 'filter-pill--active' : ''}`}
                  onClick={() => setSeverityFilter(f.value)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="incident-filter-group">
            <span className="filter-label">Status</span>
            <div className="filter-pills">
              {STATUS_FILTERS.map(f => (
                <button
                  key={f.value}
                  className={`filter-pill ${statusFilter === f.value ? 'filter-pill--active' : ''}`}
                  onClick={() => setStatusFilter(f.value)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="incident-toolbar-right">
          <div className="striker-pill">
            <Shield size={14} />
            <span>{activeStrikerCount} striker{activeStrikerCount !== 1 ? 's' : ''} ready</span>
          </div>
        </div>
      </div>

      {error && <div className="incident-error">{error}</div>}

      {/* ── Main Layout: List + Detail ── */}
      <div className="incident-layout">
        {/* Incident List */}
        <div className="incident-list">
          {incidents.length === 0 ? (
            <div className="incident-empty">
              <CheckCircle size={32} />
              <p>No AI-analyzed incidents found</p>
              <span>Alerts with LLM analysis will appear here</span>
            </div>
          ) : (
            incidents.map(incident => {
              const isActive = selectedIncident?.alert_id === incident.alert_id;
              return (
                <button
                  key={incident.alert_id}
                  className={`incident-list-item ${isActive ? 'incident-list-item--active' : ''} ${getSeverityClass(incident.severity)}`}
                  onClick={() => setSelectedIncidentId(incident.alert_id)}
                >
                  <div className="incident-list-severity" />
                  <div className="incident-list-body">
                    <div className="incident-list-top">
                      <span className="incident-list-rule">
                        {incident.reasoning?.rule ?? 'Unknown Rule'}
                      </span>
                      <span className={`incident-list-score severity-badge ${getSeverityClass(incident.severity)}`}>
                        {incident.threat_score}
                      </span>
                    </div>
                    <div className="incident-list-bottom">
                      <span className={`incident-list-sev-label ${getSeverityClass(incident.severity)}`}>
                        {incident.severity?.toUpperCase()}
                      </span>
                      <span className="incident-list-time">
                        {formatRelativeTime(incident.created_at)}
                      </span>
                      <span className={`incident-list-status status-${incident.status}`}>
                        {incident.status}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Incident Detail */}
        <div className="incident-detail">
          {selectedIncident ? (
            <IncidentDetail
              incident={selectedIncident}
              dispatch={dispatch}
              toggleActionSelection={toggleActionSelection}
              isSelected={isSelected}
              handleDispatch={handleDispatch}
              expandedRemediation={expandedRemediation}
              toggleRemediation={toggleRemediation}
              activeStrikerCount={activeStrikerCount}
            />
          ) : (
            <div className="incident-detail-empty">
              <Brain size={40} />
              <p>Select an incident to view AI analysis</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Incident Detail Sub-component ── */

interface IncidentDetailProps {
  incident: Alert;
  dispatch: ReturnType<typeof useDispatch>['dispatch'];
  toggleActionSelection: (alertId: string, actionType: string) => void;
  isSelected: (alertId: string, actionType: string) => boolean;
  handleDispatch: (alert: Alert, recommendedActions: ReturnType<typeof parseRecommendedActions>) => Promise<void>;
  expandedRemediation: Set<string>;
  toggleRemediation: (alertId: string) => void;
  activeStrikerCount: number;
}

function IncidentDetail({
  incident,
  dispatch: dispatchState,
  toggleActionSelection,
  isSelected,
  handleDispatch,
  expandedRemediation,
  toggleRemediation,
  activeStrikerCount,
}: IncidentDetailProps) {
  const recommendedActions = parseRecommendedActions(
    incident.llm_remediation,
    incident.affected_assets
  );
  const ds = dispatchState[incident.alert_id];

  return (
    <div className="detail-content">
      {/* Header */}
      <div className="detail-header">
        <div className="detail-header-left">
          <span className={`detail-severity-badge severity-badge ${getSeverityClass(incident.severity)}`}>
            {incident.severity?.toUpperCase()}
          </span>
          <span className="detail-threat-score">
            <Target size={14} />
            Score: {incident.threat_score}
          </span>
          {isHoneytoken(incident) && (
            <span className="detail-honeytoken-badge">HONEYTOKEN</span>
          )}
          {incident.reasoning?.is_multi_stage && (
            <span className="detail-multi-badge">MULTI-STAGE</span>
          )}
        </div>
        <div className="detail-header-right">
          <Clock size={14} />
          <span>{formatTimestamp(incident.created_at)}</span>
        </div>
      </div>

      {/* Rule & Description */}
      <h3 className="detail-rule">{incident.reasoning?.rule ?? 'Unknown Rule'}</h3>
      {incident.reasoning?.description && (
        <p className="detail-description">{incident.reasoning.description}</p>
      )}

      {/* Affected Assets */}
      {incident.affected_assets?.length > 0 && (
        <div className="detail-assets">
          <span className="detail-assets-label">Affected Assets:</span>
          <div className="detail-assets-list">
            {incident.affected_assets.map((asset, i) => (
              <span key={i} className="detail-asset-tag">{asset}</span>
            ))}
          </div>
        </div>
      )}

      {/* AI Analysis */}
      {incident.llm_narrative && (
        <div className="detail-ai-box">
          <div className="detail-ai-header">
            <Brain size={16} className="detail-ai-icon" />
            <span>AI Security Analysis</span>
          </div>
          <p className="detail-ai-narrative">{incident.llm_narrative}</p>
          {(incident.llm_mitre_tactic || incident.llm_mitre_technique) && (
            <div className="detail-mitre-tags">
              {incident.llm_mitre_tactic && (
                <span className="detail-mitre-tag">{incident.llm_mitre_tactic}</span>
              )}
              {incident.llm_mitre_technique && (
                <span className="detail-mitre-tag">{incident.llm_mitre_technique}</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Remediation Steps */}
      {incident.llm_remediation && (
        <div className="detail-remediation-box">
          <button
            className="detail-remediation-toggle"
            onClick={() => toggleRemediation(incident.alert_id)}
          >
            <ShieldAlert size={14} />
            <span>
              {expandedRemediation.has(incident.alert_id)
                ? 'Hide Recommended Steps'
                : 'Show Recommended Steps'}
            </span>
            {expandedRemediation.has(incident.alert_id)
              ? <ChevronUp size={14} />
              : <ChevronDown size={14} />}
          </button>
          {expandedRemediation.has(incident.alert_id) && (
            <div className="detail-remediation-steps">
              {incident.llm_remediation.split('\n').filter(s => s.trim()).map((step, i) => (
                <p key={i} className="detail-step">{step}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Dispatch Actions */}
      {recommendedActions.length > 0 && (
        <div className="detail-dispatch">
          <div className="detail-dispatch-header">
            <Shield size={16} />
            <span>Dispatch Actions ({recommendedActions.length} recommended)</span>
          </div>

          <div className="detail-dispatch-info">
            <Zap size={12} />
            <span>
              {activeStrikerCount > 0
                ? `${activeStrikerCount} striker${activeStrikerCount !== 1 ? 's' : ''} available`
                : 'No active strikers \u2014 actions will be queued'}
            </span>
          </div>

          <div className="detail-actions-list">
            {recommendedActions.map(action => {
              const selected = isSelected(incident.alert_id, action.action_type);
              return (
                <label
                  key={action.action_type}
                  className={`detail-action-item ${selected ? 'selected' : ''} risk-${action.risk}`}
                >
                  <input
                    type="checkbox"
                    className="detail-action-checkbox"
                    checked={selected}
                    onChange={() => toggleActionSelection(incident.alert_id, action.action_type)}
                    disabled={ds?.dispatching}
                  />
                  <div className="detail-action-info">
                    <span className="detail-action-label">{action.label}</span>
                    <span className={`detail-action-risk risk-badge-${action.risk}`}>
                      {RISK_LABELS[action.risk]}
                    </span>
                    <p className="detail-action-desc">{action.description}</p>
                  </div>
                </label>
              );
            })}
          </div>

          <button
            className="detail-dispatch-btn"
            disabled={ds?.dispatching || (ds?.selected?.size ?? 0) === 0}
            onClick={() => handleDispatch(incident, recommendedActions)}
          >
            {ds?.dispatching ? (
              <>
                <Loader size={14} className="spin" />
                <span>Dispatching...</span>
              </>
            ) : (
              <>
                <Send size={14} />
                <span>
                  Dispatch{' '}
                  {(ds?.selected?.size ?? 0) > 0
                    ? `${ds!.selected.size} Action${ds!.selected.size !== 1 ? 's' : ''}`
                    : '(select actions)'}
                </span>
              </>
            )}
          </button>

          {/* Dispatch results */}
          {ds?.result && (
            <div className="detail-dispatch-results">
              {ds.result.map((r, i) => (
                <div
                  key={i}
                  className={`detail-result-item ${r.status === 'queued' ? 'success' : 'failure'}`}
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

      {/* Related Events */}
      {incident.event_ids?.length > 0 && (
        <div className="detail-events">
          <span className="detail-events-label">Related Events ({incident.event_ids.length})</span>
          <div className="detail-event-ids">
            {incident.event_ids.slice(0, 5).map((eid, i) => (
              <span key={i} className="detail-event-id">{eid.slice(0, 12)}...</span>
            ))}
            {incident.event_ids.length > 5 && (
              <span className="detail-event-more">+{incident.event_ids.length - 5} more</span>
            )}
          </div>
        </div>
      )}

      {/* Verdict */}
      {incident.verdict && incident.verdict !== 'pending' && (
        <div className={`detail-verdict verdict-${incident.verdict}`}>
          <ShieldAlert size={14} />
          <span>Verdict: {incident.verdict.replace('_', ' ').toUpperCase()}</span>
        </div>
      )}
    </div>
  );
}
