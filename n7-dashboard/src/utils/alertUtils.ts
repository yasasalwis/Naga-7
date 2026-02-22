/**
 * Shared alert/incident utilities extracted from AlertPanel.
 * Used by IncidentPanel, OverviewPanel, and AlertPanel.
 */

// ── Types ────────────────────────────────────────────────────────────────────

export interface AlertReasoning {
  rule?: string;
  description?: string;
  source?: string;
  mitre_tactics?: string[];
  mitre_techniques?: string[];
  is_multi_stage?: boolean;
  count?: number;
}

export interface Alert {
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

export interface Striker {
  id: string;
  agent_subtype: string;
  zone: string;
  status: string;
  capabilities: string[];
}

export interface RecommendedAction {
  action_type: string;
  label: string;
  description: string;
  parameters: Record<string, unknown>;
  risk: 'low' | 'medium' | 'high';
}

export interface DispatchResult {
  action_type: string;
  action_id: string;
  status: string;
  error?: string;
}

export interface DispatchEntry {
  selected: Set<string>;
  dispatching: boolean;
  result: DispatchResult[] | null;
}

export interface DispatchState {
  [alertId: string]: DispatchEntry;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

export function getSeverityClass(severity: string): string {
  switch (severity?.toLowerCase()) {
    case 'critical': return 'severity-critical';
    case 'high': return 'severity-high';
    case 'medium': return 'severity-medium';
    case 'low': return 'severity-low';
    default: return 'severity-medium';
  }
}

export function getSeverityColor(severity: string): string {
  switch (severity?.toLowerCase()) {
    case 'critical': return '#ef4444';
    case 'high': return '#f97316';
    case 'medium': return '#eab308';
    case 'low': return '#22c55e';
    default: return '#94a3b8';
  }
}

export function isHoneytoken(alert: Alert): boolean {
  return (
    alert.threat_score >= 100 ||
    alert.reasoning?.rule === 'Honeytoken File Access' ||
    (alert.reasoning?.mitre_tactics ?? []).includes('TA0009')
  );
}

export const RISK_LABELS: Record<string, string> = {
  low: 'Low Risk',
  medium: 'Medium Risk',
  high: 'High Risk',
};

/**
 * Parse the LLM remediation text into discrete recommended striker actions.
 * Each numbered line (1. ...) is parsed into a recommended action payload.
 */
export function parseRecommendedActions(
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

// ── Time formatting ──────────────────────────────────────────────────────────

export function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) return '--';
  const date = new Date(timestamp.endsWith('Z') ? timestamp : timestamp + 'Z');
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}d ago`;
}

export function formatTimestamp(timestamp: string | null): string {
  if (!timestamp) return '--';
  const date = new Date(timestamp.endsWith('Z') ? timestamp : timestamp + 'Z');
  return date.toLocaleString();
}
