import { useState, useEffect } from 'react';
import axios from 'axios';
import { Activity } from 'lucide-react';
import './EventStream.css';

type FetchStatus = 'loading' | 'ok' | 'error';

interface Event {
    event_id: string;
    timestamp: string;
    event_class: string;
    severity: string;
    raw_data: any;
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
                Event Stream
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
                        <pre className="event-data">
                            {JSON.stringify(evt.raw_data, null, 2)}
                        </pre>
                    </div>
                ))}
            </div>
        </div>
    );
}
