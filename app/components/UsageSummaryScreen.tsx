'use client';

/**
 * Usage Summary Screen
 *
 * Displays aggregated LLM usage analytics by API client, hospital, or doctor.
 * Features:
 * - Group by: API client, hospital, or doctor
 * - Date range filtering
 * - Summary cards: Total cost, recording hours, API calls
 * - Sortable data table
 * - CSV export
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { authGet } from '@lib/apiClient';
import { ModelPricingModal } from './ModelPricingModal';

// Types
interface UsageSummaryItem {
  group_id: string;
  group_name: string;
  group_type: string;
  hospital_id?: string;
  hospital_name?: string;
  total_api_calls: number;
  total_sessions: number;
  total_cost_usd: number;
  total_cache_savings_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cached_tokens: number;
  total_recording_hours: number;
  total_transcription_hours: number;
  avg_cache_hit_ratio?: number;
  error_count: number;
  first_usage_at?: string;
  last_usage_at?: string;
}

interface UsageTotals {
  total_api_calls: number;
  total_sessions: number;
  total_cost_usd: number;
  total_cache_savings_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_recording_hours: number;
  unique_doctors: number;
  unique_hospitals: number;
  unique_api_clients: number;
}

interface FilterOption {
  id: string;
  name: string;
  type?: string;
  hospital_name?: string;
}

type GroupByOption = 'api_client' | 'hospital' | 'doctor';

export function UsageSummaryScreen() {
  const { getAccessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<UsageSummaryItem[]>([]);
  const [totals, setTotals] = useState<UsageTotals | null>(null);

  // Filters
  const [groupBy, setGroupBy] = useState<GroupByOption>('doctor');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [selectedApiClientId, setSelectedApiClientId] = useState<string>('');
  const [selectedHospitalId, setSelectedHospitalId] = useState<string>('');
  const [selectedDoctorId, setSelectedDoctorId] = useState<string>('');

  // Filter options
  const [apiClients, setApiClients] = useState<FilterOption[]>([]);
  const [hospitals, setHospitals] = useState<FilterOption[]>([]);
  const [doctors, setDoctors] = useState<FilterOption[]>([]);
  const [loadingFilters, setLoadingFilters] = useState(true);

  // Export state
  const [exporting, setExporting] = useState(false);

  // Pricing modal state
  const [showPricingModal, setShowPricingModal] = useState(false);

  // Load filter options on mount
  useEffect(() => {
    loadFilterOptions();
  }, []);

  // Load data when filters change
  useEffect(() => {
    loadUsageData();
  }, [groupBy, dateFrom, dateTo, selectedApiClientId, selectedHospitalId, selectedDoctorId]);

  const loadFilterOptions = async () => {
    setLoadingFilters(true);
    try {
      const accessToken = getAccessToken();
      const res = await authGet('/api/v1/usage/filters', accessToken);

      if (!res.ok) {
        console.error('Failed to load filter options');
        return;
      }

      const data = await res.json();
      setApiClients(
        (data.api_clients || []).map((c: { id: string; client_name: string; client_type: string; hospital_name?: string }) => ({
          id: c.id,
          name: `${c.client_name} (${c.client_type})`,
          type: c.client_type,
          hospital_name: c.hospital_name,
        }))
      );
      setHospitals(
        (data.hospitals || []).map((h: { id: string; hospital_name: string }) => ({
          id: h.id,
          name: h.hospital_name,
        }))
      );
      setDoctors(
        (data.doctors || []).map((d: { id: string; full_name: string; specialization?: string; hospital_name?: string }) => ({
          id: d.id,
          name: d.full_name + (d.specialization ? ` (${d.specialization})` : ''),
          hospital_name: d.hospital_name,
        }))
      );
    } catch (err) {
      console.error('Failed to load filter options:', err);
    } finally {
      setLoadingFilters(false);
    }
  };

  const loadUsageData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ group_by: groupBy });

      if (dateFrom) params.append('date_from', new Date(dateFrom).toISOString());
      if (dateTo) params.append('date_to', new Date(dateTo).toISOString());
      if (selectedApiClientId) params.append('api_client_id', selectedApiClientId);
      if (selectedHospitalId) params.append('hospital_id', selectedHospitalId);
      if (selectedDoctorId) params.append('doctor_id', selectedDoctorId);

      const res = await authGet(`/api/v1/usage/summary?${params}`, getAccessToken());

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();
      setItems(data.items || []);
      setTotals(data.totals || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load usage data');
    } finally {
      setLoading(false);
    }
  }, [groupBy, dateFrom, dateTo, selectedApiClientId, selectedHospitalId, selectedDoctorId, getAccessToken]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams({ group_by: groupBy });

      if (dateFrom) params.append('date_from', new Date(dateFrom).toISOString());
      if (dateTo) params.append('date_to', new Date(dateTo).toISOString());
      if (selectedApiClientId) params.append('api_client_id', selectedApiClientId);
      if (selectedHospitalId) params.append('hospital_id', selectedHospitalId);
      if (selectedDoctorId) params.append('doctor_id', selectedDoctorId);

      const res = await authGet(`/api/v1/usage/export?${params}`, getAccessToken());

      if (!res.ok) {
        throw new Error('Export failed');
      }

      // Download the CSV
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `usage_${groupBy}_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Export failed:', err);
      setError('Failed to export data');
    } finally {
      setExporting(false);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('en-US').format(value);
  };

  const formatHours = (value: number) => {
    return value.toFixed(2);
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getGroupByLabel = () => {
    switch (groupBy) {
      case 'api_client':
        return 'API Client';
      case 'hospital':
        return 'Hospital';
      case 'doctor':
        return 'Doctor';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Usage Summary</h1>
          <p className="text-slate-400 mt-1">Aggregated LLM usage and recording statistics</p>
        </div>
        <div className="flex items-center gap-2">
        <button
          onClick={() => setShowPricingModal(true)}
          className="px-4 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-500 flex items-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Model Pricing
        </button>
        <button
          onClick={handleExport}
          disabled={exporting || loading}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {exporting ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Exporting...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Export CSV
            </>
          )}
        </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-slate-700/50 rounded-lg border border-slate-600 p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
          {/* Group By */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Group By</label>
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as GroupByOption)}
              className="w-full bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="doctor">Doctor</option>
              <option value="hospital">Hospital</option>
              <option value="api_client">API Client</option>
            </select>
          </div>

          {/* Date From */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">From Date</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Date To */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">To Date</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* API Client Filter */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">API Client</label>
            <select
              value={selectedApiClientId}
              onChange={(e) => setSelectedApiClientId(e.target.value)}
              disabled={loadingFilters}
              className="w-full bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-white disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All API Clients</option>
              {apiClients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          {/* Hospital Filter */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Hospital</label>
            <select
              value={selectedHospitalId}
              onChange={(e) => setSelectedHospitalId(e.target.value)}
              disabled={loadingFilters}
              className="w-full bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-white disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Hospitals</option>
              {hospitals.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </select>
          </div>

          {/* Doctor Filter */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Doctor</label>
            <select
              value={selectedDoctorId}
              onChange={(e) => setSelectedDoctorId(e.target.value)}
              disabled={loadingFilters}
              className="w-full bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-white disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Doctors</option>
              {doctors.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      {totals && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <div className="bg-slate-700/50 rounded-lg border border-slate-600 p-4">
            <div className="text-sm text-slate-400">Total Cost</div>
            <div className="text-2xl font-bold text-white">{formatCurrency(totals.total_cost_usd)}</div>
          </div>
          <div className="bg-slate-700/50 rounded-lg border border-slate-600 p-4">
            <div className="text-sm text-slate-400">Cache Savings</div>
            <div className="text-2xl font-bold text-green-400">{formatCurrency(totals.total_cache_savings_usd)}</div>
          </div>
          <div className="bg-slate-700/50 rounded-lg border border-slate-600 p-4">
            <div className="text-sm text-slate-400">Recording Hours</div>
            <div className="text-2xl font-bold text-blue-400">{formatHours(totals.total_recording_hours)} hrs</div>
          </div>
          <div className="bg-slate-700/50 rounded-lg border border-slate-600 p-4">
            <div className="text-sm text-slate-400">API Calls</div>
            <div className="text-2xl font-bold text-white">{formatNumber(totals.total_api_calls)}</div>
          </div>
          <div className="bg-slate-700/50 rounded-lg border border-slate-600 p-4">
            <div className="text-sm text-slate-400">Sessions</div>
            <div className="text-2xl font-bold text-white">{formatNumber(totals.total_sessions)}</div>
          </div>
          <div className="bg-slate-700/50 rounded-lg border border-slate-600 p-4">
            <div className="text-sm text-slate-400">
              {groupBy === 'doctor' ? 'Unique Doctors' : groupBy === 'hospital' ? 'Unique Hospitals' : 'Unique Clients'}
            </div>
            <div className="text-2xl font-bold text-white">
              {groupBy === 'doctor'
                ? totals.unique_doctors
                : groupBy === 'hospital'
                ? totals.unique_hospitals
                : totals.unique_api_clients}
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded-lg">{error}</div>
      )}

      {/* Data Table */}
      <div className="bg-slate-700/50 rounded-lg border border-slate-600 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-600">
            <thead className="bg-slate-800">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-300 uppercase tracking-wider">
                  {getGroupByLabel()}
                </th>
                {groupBy !== 'hospital' && (
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-300 uppercase tracking-wider">
                    Hospital
                  </th>
                )}
                <th className="px-4 py-3 text-right text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Cost (USD)
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Cache Savings
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Recording Hrs
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-slate-300 uppercase tracking-wider">
                  API Calls
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Sessions
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Cache Hit %
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Last Usage
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-600">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-400">
                    <svg
                      className="animate-spin h-8 w-8 mx-auto text-blue-500"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    <p className="mt-2">Loading usage data...</p>
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-400">
                    No usage data found for the selected filters.
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.group_id} className="hover:bg-slate-600/50">
                    <td className="px-4 py-3">
                      <div className="font-medium text-white">{item.group_name}</div>
                      <div className="text-sm text-slate-400">{item.group_type}</div>
                    </td>
                    {groupBy !== 'hospital' && (
                      <td className="px-4 py-3 text-sm text-slate-300">{item.hospital_name || '-'}</td>
                    )}
                    <td className="px-4 py-3 text-right font-medium text-white">
                      {formatCurrency(item.total_cost_usd)}
                    </td>
                    <td className="px-4 py-3 text-right text-green-400">
                      {formatCurrency(item.total_cache_savings_usd)}
                    </td>
                    <td className="px-4 py-3 text-right text-blue-400">{formatHours(item.total_recording_hours)}</td>
                    <td className="px-4 py-3 text-right text-slate-300">{formatNumber(item.total_api_calls)}</td>
                    <td className="px-4 py-3 text-right text-slate-300">{formatNumber(item.total_sessions)}</td>
                    <td className="px-4 py-3 text-right text-slate-300">
                      {item.avg_cache_hit_ratio != null ? `${item.avg_cache_hit_ratio.toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-400">{formatDate(item.last_usage_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Model Pricing Modal */}
      <ModelPricingModal
        isOpen={showPricingModal}
        onClose={() => setShowPricingModal(false)}
      />
    </div>
  );
}
