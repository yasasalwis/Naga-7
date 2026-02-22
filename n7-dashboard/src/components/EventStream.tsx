import { useState, useEffect } from 'react';
import axios from 'axios';
import { Activity, Brain } from 'lucide-react';
import './EventStream.css';

type FetchStatus = 'loading' | 'ok' | 'error';

interface Event {
    event_id: string;
    timestamp: string;
    event_class: string;
    severity: string;
    raw_data: any;
    enrichments?: any;
}

export function EventStream() {
    const [events, setEvents] = useState<Event[]>([]);
    const [status, setStatus] = useState<FetchStatus>('loading');

    useEffect(() => {
        const fetchEvents = async () => {
            try {
                const response = await axios.get(`${import.meta.env.VITE_API_URL}/api/v1/events/`);
                setEvents(response.data);
                setStatus('ok');
            } catch (error) {
                console.error('Failed to fetch events', error);
                setStatus('error');
            }
        };

        fetchEvents();
        const interval = setInterval(fetchEvents, 2000);
        return () => clearInterval(interval);
    }, []);

    const handleStrike = async (eventId: string, actionType: string, target: string) => {
        try {
            await axios.post(`${import.meta.env.VITE_API_URL}/api/v1/events/${eventId}/strike`, {
                action_type: actionType,
                target: target
            });
            alert('Strike action dispatched successfully!');
        } catch (error) {
            console.error('Failed to dispatch strike', error);
            alert('Failed to dispatch strike action');
        }
    };

    const getSeverityClass = (severity: string) => {
        switch (severity.toLowerCase()) {
            case 'high': return 'high';
            case 'medium': return 'medium';
            case 'low': return 'low';
            default: return 'medium';
        }
    };

    return (
        <div className="event-stream-container">
            <h2 className="event-stream-header">
                <Activity className="event-stream-title-icon" size={24} />
                Recent Security Events
            </h2>
            <div className="event-list">
                {status === 'loading' && <p className="event-stream-empty">Loading events…</p>}
                {status === 'error' && <p className="event-stream-empty">Failed to load events. Check API connectivity.</p>}
                {status === 'ok' && events.length === 0 && <p className="event-stream-empty">No events received yet.</p>}
                {events.map((evt) => (
                    <div key={evt.event_id} className="event-item">
                        <div className="event-meta">
                            <span className="event-timestamp">{evt.timestamp}</span>
                            <span className={`event-severity ${getSeverityClass(evt.severity)}`}>
                                {evt.severity}
                            </span>
                        </div>
                        <p className="event-class">{evt.event_class}</p>
                        {evt.enrichments?.llm_recommendation && (
                            <div className="event-llm-recommendation">
                                <Brain size={16} className="event-llm-icon" />
                                <div style={{ flex: 1 }}>
                                    <strong>AI Analysis:</strong> {
                                        typeof evt.enrichments.llm_recommendation === 'string'
                                            ? evt.enrichments.llm_recommendation
                                            : evt.enrichments.llm_recommendation.insight || JSON.stringify(evt.enrichments.llm_recommendation)
                                    }
                                </div>
                                {typeof evt.enrichments.llm_recommendation === 'object' && evt.enrichments.llm_recommendation.recommended_action && (
                                    <button
                                        className="nd-btn nd-btn--deploy event-strike-btn"
                                        style={{ padding: '6px 12px', fontSize: '0.8rem', height: 'auto', fontWeight: 'bold' }}
                                        onClick={() => handleStrike(
                                            evt.event_id,
                                            evt.enrichments.llm_recommendation.recommended_action.action_type,
                                            evt.enrichments.llm_recommendation.recommended_action.target
                                        )}
                                    >
                                        ⚡ Take Action
                                    </button>
                                )}
                            </div>
                        )}
                        <pre className="event-data">
                            {JSON.stringify(evt.raw_data, null, 2)}
                        </pre>
                    </div>
                ))}
            </div>
        </div>
    );
}
