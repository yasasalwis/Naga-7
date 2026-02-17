import { useState, useEffect } from 'react';
import axios from 'axios';
import { Activity } from 'lucide-react';

interface Event {
    event_id: string;
    timestamp: string;
    event_class: string;
    severity: string;
    raw_data: any;
}

export function EventStream() {
    const [events, setEvents] = useState<Event[]>([]);

    useEffect(() => {
        const fetchEvents = async () => {
            try {
                const response = await axios.get('http://localhost:8000/api/events/');
                setEvents(response.data);
            } catch (error) {
                console.error('Failed to fetch events', error);
            }
        };

        fetchEvents();
        const interval = setInterval(fetchEvents, 2000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="bg-white shadow rounded-lg p-6">
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                <Activity className="w-6 h-6 text-purple-600" />
                Event Stream
            </h2>
            <div className="space-y-2 max-h-96 overflow-y-auto">
                {events.map((evt) => (
                    <div key={evt.event_id} className="border-l-4 border-purple-500 pl-4 py-2 bg-gray-50 rounded text-sm">
                        <div className="flex justify-between">
                            <span className="font-mono text-xs text-gray-400">{evt.timestamp}</span>
                            <span className={`px-1 rounded text-xs ${evt.severity === 'medium' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-200 text-gray-800'
                                }`}>
                                {evt.severity}
                            </span>
                        </div>
                        <p className="font-semibold">{evt.event_class}</p>
                        <pre className="text-xs text-gray-500 mt-1 whitespace-pre-wrap">
                            {JSON.stringify(evt.raw_data, null, 2)}
                        </pre>
                    </div>
                ))}
            </div>
        </div>
    );
}
