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
} from '../services/counsellorSharingApi';

interface Counsellor {
  id: string;
  full_name: string;
  email: string;
  school_id: string | null;
}

interface School {
  id: string;
  school_name: string;
}

interface Student {
  id: string;
  student_external_id: string;
  name: string;
}

export default function CounsellorSharingScreen() {
  const { getAccessToken } = useAuth();
  const getTokenRef = useRef(getAccessToken);
  getTokenRef.current = getAccessToken;

  // Data state
  const [links, setLinks] = useState<SharingLink[]>([]);
  const [doctors, setCounsellors] = useState<Counsellor[]>([]);
  const [hospitals, setSchools] = useState<School[]>([]);
  const [patients, setStudents] = useState<Student[]>([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Create form state
  const [selectedSchoolId, setSelectedSchoolId] = useState<string>('');
  const [doctorAId, setCounsellorAId] = useState<string>('');
  const [doctorBId, setCounsellorBId] = useState<string>('');
  const [sharingMode, setSharingMode] = useState<'all' | 'specific'>('all');
  const [selectedStudentIds, setSelectedStudentIds] = useState<string[]>([]);
  const [patientSearch, setStudentSearch] = useState('');

  // Edit state
  const [editingLink, setEditingLink] = useState<SharingLink | null>(null);
  const [editMode, setEditMode] = useState<'all' | 'specific'>('all');
  const [editStudentIds, setEditStudentIds] = useState<string[]>([]);

  // Load initial data
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const token = getTokenRef.current();

        // Load schools, counsellors, and sharing links in parallel
        const [hospitalsRes, doctorsRes, linksData] = await Promise.all([
          authGet('/api/v1/counsellors/schools', token ?? null),
          authGet('/api/v1/counsellors', token ?? null),
          getSharingLinks(undefined, token),
        ]);

        if (cancelled) return;

        const hospitalsData = await hospitalsRes.json();
        setSchools(hospitalsData.schools || []);

        const doctorsData = await doctorsRes.json();
        setCounsellors(doctorsData.counsellors || []);

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

  // Load students when school is selected (for specific sharing)
  useEffect(() => {
    if (!selectedSchoolId || sharingMode !== 'specific') return;
    let cancelled = false;
    const loadStudents = async () => {
      try {
        const token = getTokenRef.current();
        const res = await authGet(`/api/v1/students?school_id=${selectedSchoolId}&limit=200`, token ?? null);
        if (cancelled) return;
        const data = await res.json();
        setStudents(data.students || []);
      } catch {
        // Non-critical - students list is optional
      }
    };
    loadStudents();
    return () => { cancelled = true; };
  }, [selectedSchoolId, sharingMode]);

  const refreshLinks = async () => {
    try {
      const token = getTokenRef.current();
      const data = await getSharingLinks(undefined, token);
      setLinks(data);
    } catch (err) {
      setError('Failed to refresh: ' + (err as Error).message);
    }
  };

  // Filtered counsellors by selected school
  const filteredCounsellors = selectedSchoolId
    ? doctors.filter(d => d.school_id === selectedSchoolId)
    : doctors;

  // Filtered students for search
  const filteredStudents = patientSearch
    ? patients.filter(p =>
        p.name?.toLowerCase().includes(patientSearch.toLowerCase()) ||
        p.student_external_id?.toLowerCase().includes(patientSearch.toLowerCase())
      )
    : patients;

  const handleCreate = async () => {
    if (!doctorAId || !doctorBId) {
      setError('Please select both counsellors');
      return;
    }
    if (doctorAId === doctorBId) {
      setError('Cannot link a counsellor to themselves');
      return;
    }

    setActionLoading('create');
    setError(null);
    try {
      const token = getTokenRef.current();
      await createSharingLink(
        {
          counsellor_id: doctorAId,
          linked_counsellor_id: doctorBId,
          student_ids: sharingMode === 'all' ? null : selectedStudentIds,
        },
        token,
      );
      await refreshLinks();
      // Reset form
      setShowCreateForm(false);
      setCounsellorAId('');
      setCounsellorBId('');
      setSharingMode('all');
      setSelectedStudentIds([]);
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
        editingLink.counsellor_id,
        editingLink.linked_counsellor_id,
        { student_ids: editMode === 'all' ? null : editStudentIds },
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
    if (!confirm(`Deactivate sharing between ${link.counsellor_name} and ${link.linked_counsellor_name}?`)) return;

    setActionLoading(`deactivate-${link.id}`);
    setError(null);
    try {
      const token = getTokenRef.current();
      await deactivateSharingLink(link.counsellor_id, link.linked_counsellor_id, token);
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
    setEditStudentIds(link.student_ids || []);

    // Load students for this pair's school if needed
    const doctor = doctors.find(d => d.id === link.counsellor_id);
    if (doctor?.school_id) {
      setSelectedSchoolId(doctor.school_id);
    }
  };

  const toggleStudentSelection = (patientId: string, list: string[], setter: (ids: string[]) => void) => {
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
        <span className="ml-3 text-slate-400">Loading counsellor sharing data...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Counsellor Sharing Management</h2>
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

          {/* School Filter */}
          <div>
            <label className="block text-sm text-slate-400 mb-1">School (filter counsellors)</label>
            <select
              value={selectedSchoolId}
              onChange={e => {
                setSelectedSchoolId(e.target.value);
                setCounsellorAId('');
                setCounsellorBId('');
              }}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
            >
              <option value="">All schools</option>
              {hospitals.map(h => (
                <option key={h.id} value={h.id}>{h.school_name}</option>
              ))}
            </select>
          </div>

          {/* Counsellor Selection */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Counsellor A</label>
              <select
                value={doctorAId}
                onChange={e => setCounsellorAId(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              >
                <option value="">Select counsellor...</option>
                {filteredCounsellors.filter(d => d.id !== doctorBId).map(d => (
                  <option key={d.id} value={d.id}>{d.full_name} ({d.email})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Counsellor B</label>
              <select
                value={doctorBId}
                onChange={e => setCounsellorBId(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
              >
                <option value="">Select counsellor...</option>
                {filteredCounsellors.filter(d => d.id !== doctorAId).map(d => (
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
                <span className="text-sm text-slate-300">Share all students</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={sharingMode === 'specific'}
                  onChange={() => setSharingMode('specific')}
                  className="text-blue-600"
                />
                <span className="text-sm text-slate-300">Share specific students</span>
              </label>
            </div>
          </div>

          {/* Student Selection (specific mode) */}
          {sharingMode === 'specific' && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                Select Students ({selectedStudentIds.length} selected)
              </label>
              <input
                type="text"
                placeholder="Search students..."
                value={patientSearch}
                onChange={e => setStudentSearch(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm mb-2"
              />
              <div className="max-h-48 overflow-y-auto bg-slate-700/50 rounded-lg border border-slate-600 divide-y divide-slate-700">
                {filteredStudents.length === 0 ? (
                  <div className="p-3 text-sm text-slate-500">
                    {patients.length === 0 ? 'Select a school first to load students' : 'No students match search'}
                  </div>
                ) : (
                  filteredStudents.slice(0, 50).map(p => (
                    <label key={p.id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-600/50 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedStudentIds.includes(p.id)}
                        onChange={() => toggleStudentSelection(p.id, selectedStudentIds, setSelectedStudentIds)}
                        className="text-blue-600 rounded"
                      />
                      <span className="text-sm text-slate-300">
                        {p.name || 'Unnamed'} <span className="text-slate-500">({p.student_external_id})</span>
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
              {actionLoading === 'create' ? 'Creating...' : 'Link Counsellors'}
            </button>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editingLink && (
        <div className="bg-slate-800/60 rounded-lg p-5 border border-yellow-500/30 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white">
              Edit: {editingLink.counsellor_name} ↔ {editingLink.linked_counsellor_name}
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
                <span className="text-sm text-slate-300">Share all students</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={editMode === 'specific'}
                  onChange={() => setEditMode('specific')}
                  className="text-blue-600"
                />
                <span className="text-sm text-slate-300">Share specific students</span>
              </label>
            </div>
          </div>

          {editMode === 'specific' && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                Selected Students ({editStudentIds.length})
              </label>
              <input
                type="text"
                placeholder="Search students..."
                value={patientSearch}
                onChange={e => setStudentSearch(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm mb-2"
              />
              <div className="max-h-48 overflow-y-auto bg-slate-700/50 rounded-lg border border-slate-600 divide-y divide-slate-700">
                {filteredStudents.length === 0 ? (
                  <div className="p-3 text-sm text-slate-500">No students available</div>
                ) : (
                  filteredStudents.slice(0, 50).map(p => (
                    <label key={p.id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-600/50 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editStudentIds.includes(p.id)}
                        onChange={() => toggleStudentSelection(p.id, editStudentIds, setEditStudentIds)}
                        className="text-blue-600 rounded"
                      />
                      <span className="text-sm text-slate-300">
                        {p.name || 'Unnamed'} <span className="text-slate-500">({p.student_external_id})</span>
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
                    <span className="text-white font-medium">{link.counsellor_name}</span>
                    <span className="text-slate-500">↔</span>
                    <span className="text-white font-medium">{link.linked_counsellor_name}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      link.sharing_mode === 'all_patients'
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-blue-500/20 text-blue-400'
                    }`}>
                      {link.sharing_mode === 'all_patients'
                        ? 'All students'
                        : `${link.student_count ?? 0} student(s)`}
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
