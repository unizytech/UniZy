'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '@lib/auth';
import { authGet } from '@lib/apiClient';
import {
  getSharingLinks,
  createSharingLink,
  updateSharingLink,
  deactivateSharingLink,
  type SharingLink,
} from '../services/doctorSharingApi';

interface Doctor {
  id: string;
  full_name: string;
  email: string;
  hospital_id: string | null;
}

interface Hospital {
  id: string;
  hospital_name: string;
}

interface Patient {
  id: string;
  patient_external_id: string;
  name: string;
}

export default function DoctorSharingScreen() {
  const { getAccessToken } = useAuth();
  const getTokenRef = useRef(getAccessToken);
  getTokenRef.current = getAccessToken;

  // Data state
  const [links, setLinks] = useState<SharingLink[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Create form state
  const [selectedHospitalId, setSelectedHospitalId] = useState<string>('');
  const [doctorAId, setDoctorAId] = useState<string>('');
  const [doctorBId, setDoctorBId] = useState<string>('');
  const [sharingMode, setSharingMode] = useState<'all' | 'specific'>('all');
  const [selectedPatientIds, setSelectedPatientIds] = useState<string[]>([]);
  const [patientSearch, setPatientSearch] = useState('');

  // Edit state
  const [editingLink, setEditingLink] = useState<SharingLink | null>(null);
  const [editMode, setEditMode] = useState<'all' | 'specific'>('all');
  const [editPatientIds, setEditPatientIds] = useState<string[]>([]);

  // Load initial data
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const token = getTokenRef.current();

        // Load hospitals, doctors, and sharing links in parallel
        const [hospitalsRes, doctorsRes, linksData] = await Promise.all([
          authGet('/api/v1/doctors/hospitals', token ?? null),
          authGet('/api/v1/doctors', token ?? null),
          getSharingLinks(undefined, token),
        ]);

        if (cancelled) return;

        const hospitalsData = await hospitalsRes.json();
        setHospitals(hospitalsData.hospitals || []);

        const doctorsData = await doctorsRes.json();
        setDoctors(doctorsData.doctors || []);

        setLinks(linksData);
      } catch (err) {
        if (!cancelled) setError('Failed to load data: ' + (err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  // Load patients when hospital is selected (for specific sharing)
  useEffect(() => {
    if (!selectedHospitalId || sharingMode !== 'specific') return;
    let cancelled = false;
    const loadPatients = async () => {
      try {
        const token = getTokenRef.current();
        const res = await authGet(`/api/v1/patients?hospital_id=${selectedHospitalId}&limit=200`, token ?? null);
        if (cancelled) return;
        const data = await res.json();
        setPatients(data.patients || []);
      } catch {
        // Non-critical - patients list is optional
      }
    };
    loadPatients();
    return () => { cancelled = true; };
  }, [selectedHospitalId, sharingMode]);

  const refreshLinks = async () => {
    try {
      const token = getTokenRef.current();
      const data = await getSharingLinks(undefined, token);
      setLinks(data);
    } catch (err) {
      setError('Failed to refresh: ' + (err as Error).message);
    }
  };

  // Filtered doctors by selected hospital
  const filteredDoctors = selectedHospitalId
    ? doctors.filter(d => d.hospital_id === selectedHospitalId)
    : doctors;

  // Filtered patients for search
  const filteredPatients = patientSearch
    ? patients.filter(p =>
        p.name?.toLowerCase().includes(patientSearch.toLowerCase()) ||
        p.patient_external_id?.toLowerCase().includes(patientSearch.toLowerCase())
      )
    : patients;

  const handleCreate = async () => {
    if (!doctorAId || !doctorBId) {
      setError('Please select both doctors');
      return;
    }
    if (doctorAId === doctorBId) {
      setError('Cannot link a doctor to themselves');
      return;
    }

    setActionLoading('create');
    setError(null);
    try {
      const token = getTokenRef.current();
      await createSharingLink(
        {
          doctor_id: doctorAId,
          linked_doctor_id: doctorBId,
          patient_ids: sharingMode === 'all' ? null : selectedPatientIds,
        },
        token,
      );
      await refreshLinks();
      // Reset form
      setShowCreateForm(false);
      setDoctorAId('');
      setDoctorBId('');
      setSharingMode('all');
      setSelectedPatientIds([]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleUpdate = async () => {
    if (!editingLink) return;

    setActionLoading('update');
    setError(null);
    try {
      const token = getTokenRef.current();
      await updateSharingLink(
        editingLink.doctor_id,
        editingLink.linked_doctor_id,
        { patient_ids: editMode === 'all' ? null : editPatientIds },
        token,
      );
      await refreshLinks();
      setEditingLink(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeactivate = async (link: SharingLink) => {
    if (!confirm(`Deactivate sharing between ${link.doctor_name} and ${link.linked_doctor_name}?`)) return;

    setActionLoading(`deactivate-${link.id}`);
    setError(null);
    try {
      const token = getTokenRef.current();
      await deactivateSharingLink(link.doctor_id, link.linked_doctor_id, token);
      await refreshLinks();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionLoading(null);
    }
  };

  const startEdit = (link: SharingLink) => {
    setEditingLink(link);
    setEditMode(link.sharing_mode === 'all_patients' ? 'all' : 'specific');
    setEditPatientIds(link.patient_ids || []);

    // Load patients for this pair's hospital if needed
    const doctor = doctors.find(d => d.id === link.doctor_id);
    if (doctor?.hospital_id) {
      setSelectedHospitalId(doctor.hospital_id);
    }
  };

  const togglePatientSelection = (patientId: string, list: string[], setter: (ids: string[]) => void) => {
    if (list.includes(patientId)) {
      setter(list.filter(id => id !== patientId));
    } else {
      setter([...list, patientId]);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        <span className="ml-3 text-slate-400">Loading doctor sharing data...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Doctor Sharing Management</h2>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-sm font-medium"
        >
          {showCreateForm ? 'Cancel' : '+ New Sharing Link'}
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">x</button>
        </div>
      )}

      {/* Create Form */}
      {showCreateForm && (
        <div className="bg-slate-800/60 rounded-lg p-5 border border-slate-600/50 space-y-4">
          <h3 className="text-lg font-semibold text-white">Add New Sharing Link</h3>

          {/* Hospital Filter */}
          <div>
            <label className="block text-sm text-slate-400 mb-1">Hospital (filter doctors)</label>
            <select
              value={selectedHospitalId}
              onChange={e => {
                setSelectedHospitalId(e.target.value);
                setDoctorAId('');
                setDoctorBId('');
              }}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
            >
              <option value="">All hospitals</option>
              {hospitals.map(h => (
                <option key={h.id} value={h.id}>{h.hospital_name}</option>
              ))}
            </select>
          </div>

          {/* Doctor Selection */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Doctor A</label>
              <select
                value={doctorAId}
                onChange={e => setDoctorAId(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              >
                <option value="">Select doctor...</option>
                {filteredDoctors.filter(d => d.id !== doctorBId).map(d => (
                  <option key={d.id} value={d.id}>{d.full_name} ({d.email})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Doctor B</label>
              <select
                value={doctorBId}
                onChange={e => setDoctorBId(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              >
                <option value="">Select doctor...</option>
                {filteredDoctors.filter(d => d.id !== doctorAId).map(d => (
                  <option key={d.id} value={d.id}>{d.full_name} ({d.email})</option>
                ))}
              </select>
            </div>
          </div>

          {/* Sharing Mode */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Sharing Mode</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={sharingMode === 'all'}
                  onChange={() => setSharingMode('all')}
                  className="text-blue-600"
                />
                <span className="text-sm text-slate-300">Share all patients</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={sharingMode === 'specific'}
                  onChange={() => setSharingMode('specific')}
                  className="text-blue-600"
                />
                <span className="text-sm text-slate-300">Share specific patients</span>
              </label>
            </div>
          </div>

          {/* Patient Selection (specific mode) */}
          {sharingMode === 'specific' && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                Select Patients ({selectedPatientIds.length} selected)
              </label>
              <input
                type="text"
                placeholder="Search patients..."
                value={patientSearch}
                onChange={e => setPatientSearch(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm mb-2"
              />
              <div className="max-h-48 overflow-y-auto bg-slate-700/50 rounded-lg border border-slate-600 divide-y divide-slate-700">
                {filteredPatients.length === 0 ? (
                  <div className="p-3 text-sm text-slate-500">
                    {patients.length === 0 ? 'Select a hospital first to load patients' : 'No patients match search'}
                  </div>
                ) : (
                  filteredPatients.slice(0, 50).map(p => (
                    <label key={p.id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-600/50 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedPatientIds.includes(p.id)}
                        onChange={() => togglePatientSelection(p.id, selectedPatientIds, setSelectedPatientIds)}
                        className="text-blue-600 rounded"
                      />
                      <span className="text-sm text-slate-300">
                        {p.name || 'Unnamed'} <span className="text-slate-500">({p.patient_external_id})</span>
                      </span>
                    </label>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Submit */}
          <div className="flex justify-end">
            <button
              onClick={handleCreate}
              disabled={!doctorAId || !doctorBId || actionLoading === 'create'}
              className="px-5 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors text-sm font-medium"
            >
              {actionLoading === 'create' ? 'Creating...' : 'Link Doctors'}
            </button>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editingLink && (
        <div className="bg-slate-800/60 rounded-lg p-5 border border-yellow-500/30 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white">
              Edit: {editingLink.doctor_name} ↔ {editingLink.linked_doctor_name}
            </h3>
            <button onClick={() => setEditingLink(null)} className="text-slate-400 hover:text-white">
              Cancel
            </button>
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-2">Sharing Mode</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={editMode === 'all'}
                  onChange={() => setEditMode('all')}
                  className="text-blue-600"
                />
                <span className="text-sm text-slate-300">Share all patients</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={editMode === 'specific'}
                  onChange={() => setEditMode('specific')}
                  className="text-blue-600"
                />
                <span className="text-sm text-slate-300">Share specific patients</span>
              </label>
            </div>
          </div>

          {editMode === 'specific' && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                Selected Patients ({editPatientIds.length})
              </label>
              <input
                type="text"
                placeholder="Search patients..."
                value={patientSearch}
                onChange={e => setPatientSearch(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm mb-2"
              />
              <div className="max-h-48 overflow-y-auto bg-slate-700/50 rounded-lg border border-slate-600 divide-y divide-slate-700">
                {filteredPatients.length === 0 ? (
                  <div className="p-3 text-sm text-slate-500">No patients available</div>
                ) : (
                  filteredPatients.slice(0, 50).map(p => (
                    <label key={p.id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-600/50 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editPatientIds.includes(p.id)}
                        onChange={() => togglePatientSelection(p.id, editPatientIds, setEditPatientIds)}
                        className="text-blue-600 rounded"
                      />
                      <span className="text-sm text-slate-300">
                        {p.name || 'Unnamed'} <span className="text-slate-500">({p.patient_external_id})</span>
                      </span>
                    </label>
                  ))
                )}
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={handleUpdate}
              disabled={actionLoading === 'update'}
              className="px-5 py-2 bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50 text-white rounded-lg transition-colors text-sm font-medium"
            >
              {actionLoading === 'update' ? 'Updating...' : 'Save Changes'}
            </button>
          </div>
        </div>
      )}

      {/* Active Sharing Links */}
      <div className="bg-slate-800/40 rounded-lg border border-slate-700/50">
        <div className="px-4 py-3 border-b border-slate-700/50">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
            Active Sharing Links ({links.length})
          </h3>
        </div>

        {links.length === 0 ? (
          <div className="p-6 text-center text-slate-500">
            No sharing links configured. Click &quot;+ New Sharing Link&quot; to create one.
          </div>
        ) : (
          <div className="divide-y divide-slate-700/50">
            {links.map(link => (
              <div key={link.id} className="px-4 py-3 flex items-center justify-between hover:bg-slate-700/20">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-medium">{link.doctor_name}</span>
                    <span className="text-slate-500">↔</span>
                    <span className="text-white font-medium">{link.linked_doctor_name}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      link.sharing_mode === 'all_patients'
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-blue-500/20 text-blue-400'
                    }`}>
                      {link.sharing_mode === 'all_patients'
                        ? 'All patients'
                        : `${link.patient_count ?? 0} patient(s)`}
                    </span>
                    <span className="text-xs text-slate-500">
                      Created {new Date(link.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => startEdit(link)}
                    className="px-3 py-1.5 text-xs bg-slate-600 hover:bg-slate-500 text-white rounded transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeactivate(link)}
                    disabled={actionLoading === `deactivate-${link.id}`}
                    className="px-3 py-1.5 text-xs bg-red-600/80 hover:bg-red-600 disabled:opacity-50 text-white rounded transition-colors"
                  >
                    {actionLoading === `deactivate-${link.id}` ? '...' : 'Remove'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
