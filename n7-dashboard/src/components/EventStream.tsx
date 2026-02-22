import { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import {
  Activity, Brain, X, Trash2, RefreshCw,
  ChevronDown, ChevronRight, Search,
} from 'lucide-react';
import { formatRelativeTime } from '../utils/alertUtils';
import './EventStream.css';

type FetchStatus = 'loading' | 'ok' | 'error';
type SeverityFilter = 'all' | 'critical' | 'high' | 'medium' | 'low' | 'informational';
type ClassFilter = 'all' | 'network' | 'endpoint' | 'system' | 'cloud';

interface Event {
  event_id: string;
  timestamp: string;
  event_class: string;
  severity: string;
  raw_data: unknown;
  enrichments?: {
    llm_recommendation?: unknown;
    [key: string]: unknown;
  };
}

const SEVERITY_OPTIONS: { value: SeverityFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
  { value: 'informational', label: 'Info' },
];

const CLASS_OPTIONS: { value: ClassFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'network', label: 'Network' },
  { value: 'endpoint', label: 'Endpoint' },
  { value: 'system', label: 'System' },
  { value: 'cloud', label: 'Cloud' },
];

const PAGE_SIZE = 50;

export function EventStream() {
  const [events, setEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState<FetchStatus>('loading');
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(() => {
    try {
      const stored = sessionStorage.getItem('n7_dismissed_events');
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch { return new Set(); }
  });

  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [classFilter, setClassFilter] = useState<ClassFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [page, setPage] = useState(1);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());

  // Persist dismissed IDs
  useEffect(() => {
    sessionStorage.setItem('n7_dismissed_events', JSON.stringify([...dismissedIds]));
  }, [dismissedIds]);

  // Fetch events
  const fetchEvents = useCallback(async () => {
    try {
      const response = await axios.get(`${import.meta.env.VITE_API_URL}/api/v1/events/?limit=200`);
      setEvents(response.data);
      setStatus('ok');
    } catch (error) {
      console.error('Failed to fetch events', error);
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    if (!autoRefresh) return;
    const interval = setInterval(fetchEvents, 2000);
    return () => clearInterval(interval);
  }, [fetchEvents, autoRefresh]);

  // Filter events
  const filteredEvents = useMemo(() => {
    return events.filter(evt => {
      if (dismissedIds.has(evt.event_id)) return false;
      if (severityFilter !== 'all' && evt.severity?.toLowerCase() !== severityFilter) return false;
      if (classFilter !== 'all' && evt.event_class?.toLowerCase() !== classFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const raw = JSON.stringify(evt.raw_data).toLowerCase();
        const cls = (evt.event_class || '').toLowerCase();
        if (!raw.includes(q) && !cls.includes(q)) return false;
      }
      return true;
    });
  }, [events, dismissedIds, severityFilter, classFilter, searchQuery]);

  // Pagination
  const paginatedEvents = filteredEvents.slice(0, page * PAGE_SIZE);
  const hasMore = page * PAGE_SIZE < filteredEvents.length;

  const handleDismiss = (eventId: string) => {
    setDismissedIds(prev => new Set(prev).add(eventId));
  };

  const handleClearAll = () => {
    setDismissedIds(new Set(events.map(e => e.event_id)));
  };

  const handleResetDismissed = () => {
    setDismissedIds(new Set());
    sessionStorage.removeItem('n7_dismissed_events');
  };

  const toggleExpand = (eventId: string) => {
    setExpandedEvents(prev => {
      const next = new Set(prev);
      next.has(eventId) ? next.delete(eventId) : next.add(eventId);
      return next;
    });
  };

  const getSeverityClass = (severity: string) => {
    switch (severity?.toLowerCase()) {
      case 'critical': return 'es-critical';
      case 'high': return 'es-high';
      case 'medium': return 'es-medium';
      case 'low': return 'es-low';
      default: return 'es-info';
    }
  };

  const handleStrike = async (eventId: string, actionType: string, target: string) => {
    try {
      await axios.post(`${import.meta.env.VITE_API_URL}/api/v1/events/${eventId}/strike`, {
        action_type: actionType,
        target: target
      });
    } catch (error) {
      console.error('Failed to dispatch strike', error);
    }
  };

  return (
    <div className="es-container">
      {/* ── Toolbar ── */}
      <div className="es-toolbar">
        <div className="es-toolbar-top">
          <div className="es-count-badge">
            <Activity size={14} />
            <span>{filteredEvents.length} event{filteredEvents.length !== 1 ? 's' : ''}</span>
          </div>

          <div className="es-toolbar-actions">
            {dismissedIds.size > 0 && (
              <button className="es-btn es-btn--ghost" onClick={handleResetDismissed}>
                <RefreshCw size={13} />
                Restore ({dismissedIds.size})
              </button>
            )}
            <button
              className="es-btn es-btn--danger"
              onClick={handleClearAll}
              disabled={filteredEvents.length === 0}
            >
              <Trash2 size={13} />
              Clear All
            </button>
            <button
              className={`es-btn ${autoRefresh ? 'es-btn--active' : 'es-btn--ghost'}`}
              onClick={() => setAutoRefresh(prev => !prev)}
              title={autoRefresh ? 'Auto-refresh ON (2s)' : 'Auto-refresh OFF'}
            >
              <RefreshCw size={13} className={autoRefresh ? 'es-spin' : ''} />
              {autoRefresh ? 'Live' : 'Paused'}
            </button>
          </div>
        </div>

        {/* Filter bar */}
        <div className="es-filters">
          <div className="es-filter-group">
            <span className="es-filter-label">Severity</span>
            <div className="es-filter-pills">
              {SEVERITY_OPTIONS.map(f => (
                <button
                  key={f.value}
                  className={`es-filter-pill ${severityFilter === f.value ? 'es-filter-pill--active' : ''}`}
                  onClick={() => { setSeverityFilter(f.value); setPage(1); }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          <div className="es-filter-group">
            <span className="es-filter-label">Class</span>
            <div className="es-filter-pills">
              {CLASS_OPTIONS.map(f => (
                <button
                  key={f.value}
                  className={`es-filter-pill ${classFilter === f.value ? 'es-filter-pill--active' : ''}`}
                  onClick={() => { setClassFilter(f.value); setPage(1); }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          <div className="es-search-wrap">
            <Search size={14} className="es-search-icon" />
            <input
              className="es-search"
              type="text"
              placeholder="Search events..."
              value={searchQuery}
              onChange={e => { setSearchQuery(e.target.value); setPage(1); }}
            />
            {searchQuery && (
              <button className="es-search-clear" onClick={() => setSearchQuery('')}>
                <X size={12} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Event List ── */}
      <div className="es-list">
        {status === 'loading' && (
          <div className="es-empty">
            <RefreshCw size={24} className="es-spin" />
            <p>Loading events...</p>
          </div>
        )}
        {status === 'error' && (
          <div className="es-empty es-empty--error">
            <p>Failed to load events. Check API connectivity.</p>
          </div>
        )}
        {status === 'ok' && filteredEvents.length === 0 && (
          <div className="es-empty">
            <Activity size={28} />
            <p>No events match your filters</p>
          </div>
        )}

        {paginatedEvents.map(evt => {
          const isExpanded = expandedEvents.has(evt.event_id);
          return (
            <div key={evt.event_id} className={`es-event ${getSeverityClass(evt.severity)}`}>
              <div className="es-event-header">
                <div className="es-event-meta">
                  <span className={`es-severity-badge ${getSeverityClass(evt.severity)}`}>
                    {evt.severity?.toUpperCase()}
                  </span>
                  <span className="es-event-class">{evt.event_class}</span>
                  <span className="es-event-time" title={evt.timestamp}>
                    {formatRelativeTime(evt.timestamp)}
                  </span>
                </div>
                <div className="es-event-actions">
                  <button
                    className="es-expand-btn"
                    onClick={() => toggleExpand(evt.event_id)}
                    title={isExpanded ? 'Collapse' : 'Expand raw data'}
                  >
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                  <button
                    className="es-dismiss-btn"
                    onClick={() => handleDismiss(evt.event_id)}
                    title="Dismiss event"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>

              {/* LLM Recommendation */}
              {!!evt.enrichments?.llm_recommendation && (() => {
                const rec = evt.enrichments!.llm_recommendation;
                const recText = typeof rec === 'string'
                  ? rec
                  : typeof rec === 'object' && rec !== null && 'insight' in (rec as Record<string, unknown>)
                    ? String((rec as Record<string, unknown>).insight)
                    : JSON.stringify(rec);
                const hasAction = typeof rec === 'object' && rec !== null &&
                  'recommended_action' in (rec as Record<string, unknown>);
                return (
                  <div className="es-llm-box">
                    <Brain size={14} className="es-llm-icon" />
                    <div className="es-llm-content">
                      <strong>AI Analysis:</strong> {recText}
                    </div>
                    {hasAction && (
                      <button
                        className="es-strike-btn"
                        onClick={() => {
                          const action = (rec as Record<string, Record<string, string>>).recommended_action;
                          handleStrike(evt.event_id, action.action_type, action.target);
                        }}
                      >
                        Take Action
                      </button>
                    )}
                  </div>
                );
              })()}

              {/* Collapsible raw data */}
              {isExpanded && (
                <pre className="es-raw-data">
                  {JSON.stringify(evt.raw_data, null, 2)}
                </pre>
              )}
            </div>
          );
        })}

        {/* Load More */}
        {hasMore && (
          <button className="es-load-more" onClick={() => setPage(p => p + 1)}>
            Load More ({filteredEvents.length - paginatedEvents.length} remaining)
          </button>
        )}
      </div>
    </div>
  );
}
