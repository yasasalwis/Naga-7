/**
 * Custom hook: Dispatch state management for striker action execution.
 * Extracted from AlertPanel to be shared across IncidentPanel and AlertPanel.
 */
import { useState, useCallback } from 'react';
import axios from 'axios';
import type { Alert, RecommendedAction, DispatchState } from '../utils/alertUtils';

const API_BASE = import.meta.env.VITE_API_URL;

interface UseDispatchReturn {
  dispatch: DispatchState;
  toggleActionSelection: (alertId: string, actionType: string) => void;
  isSelected: (alertId: string, actionType: string) => boolean;
  handleDispatch: (alert: Alert, recommendedActions: RecommendedAction[]) => Promise<void>;
}

export function useDispatch(): UseDispatchReturn {
  const [dispatch, setDispatch] = useState<DispatchState>({});

  const toggleActionSelection = useCallback((alertId: string, actionType: string) => {
    setDispatch(prev => {
      const current = prev[alertId] ?? { selected: new Set<string>(), dispatching: false, result: null };
      const selected = new Set(current.selected);
      selected.has(actionType) ? selected.delete(actionType) : selected.add(actionType);
      return { ...prev, [alertId]: { ...current, selected, result: null } };
    });
  }, []);

  const isSelected = useCallback((alertId: string, actionType: string): boolean => {
    return dispatch[alertId]?.selected?.has(actionType) ?? false;
  }, [dispatch]);

  const handleDispatch = useCallback(async (alert: Alert, recommendedActions: RecommendedAction[]) => {
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
          selected: new Set<string>(),
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
            error: 'Network error \u2014 check Core API',
          })),
        },
      }));
    }
  }, [dispatch]);

  return {
    dispatch,
    toggleActionSelection,
    isSelected,
    handleDispatch,
  };
}
