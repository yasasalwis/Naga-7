/**
 * Custom hook: NATS WebSocket connection for real-time alert streaming.
 * Extracted from AlertPanel to be shared across IncidentPanel and OverviewPanel.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { connect, jwtAuthenticator, StringCodec } from 'nats.ws';
import type { NatsConnection } from 'nats.ws';
import type { Alert, Striker } from '../utils/alertUtils';

const API_BASE = import.meta.env.VITE_API_URL;

interface UseNatsAlertsReturn {
  alerts: Alert[];
  strikers: Striker[];
  error: string | null;
  connected: boolean;
  activeStrikerCount: number;
  refreshAlerts: () => Promise<void>;
}

export function useNatsAlerts(): UseNatsAlertsReturn {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [strikers, setStrikers] = useState<Striker[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const ncRef = useRef<NatsConnection | null>(null);

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
    let isActive = true;

    fetchAlerts();
    fetchStrikers();

    const connectNats = async () => {
      try {
        const token = localStorage.getItem('n7_token');
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const response = await axios.get(`${API_BASE}/api/v1/alerts/ws-token`, { headers });

        if (!isActive) return;

        const { jwt, seed } = response.data;
        const seedBytes = new TextEncoder().encode(seed);

        const nc = await connect({
          servers: 'ws://localhost:9222',
          authenticator: jwtAuthenticator(() => jwt, seedBytes),
        });

        ncRef.current = nc;
        if (isActive) setConnected(true);

        const sc = StringCodec();
        const sub = nc.subscribe('n7.alerts.critical.new');

        for await (const msg of sub) {
          if (!isActive) break;
          try {
            const newAlert = JSON.parse(sc.decode(msg.data));
            setAlerts(prev => {
              const exists = prev.find(a => a.alert_id === newAlert.alert_id);
              if (exists) return prev;
              return [newAlert, ...prev].slice(0, 50);
            });
          } catch (e) {
            console.error('Error parsing NATS message', e);
          }
        }
      } catch (err) {
        console.error('NATS WebSocket connection failed. Retrying in 5s...', err);
        if (isActive) {
          setConnected(false);
          setTimeout(connectNats, 5000);
        }
      }
    };

    connectNats();

    const strikerInterval = setInterval(fetchStrikers, 15000);

    return () => {
      isActive = false;
      clearInterval(strikerInterval);
      if (ncRef.current) {
        ncRef.current.close();
        ncRef.current = null;
      }
      setConnected(false);
    };
  }, [fetchAlerts, fetchStrikers]);

  const activeStrikerCount = strikers.filter(s => s.status === 'active').length;

  return {
    alerts,
    strikers,
    error,
    connected,
    activeStrikerCount,
    refreshAlerts: fetchAlerts,
  };
}
