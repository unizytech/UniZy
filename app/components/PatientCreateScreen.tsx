'use client';

import React, { useState, useEffect } from 'react';
import { useAuth } from '@lib/auth';
import { API_CONFIG } from '@lib/config';
import { getDoctors, type Doctor } from '@/services/doctorApi';

interface PatientFormData {
  patient_id: string;
  full_name: string;
  date_of_birth: string;
  gender: string;
  ip_id: string;
  op_id: string;
  add_info: string; // JSON string
}

interface CreateResult {
  success: boolean;
  patient?: Record<string, unknown>;
  created: boolean;
  message: string;
}

export function PatientCreateScreen() {
  const { getAccessToken } = useAuth();

  const [formData, setFormData] = useState<PatientFormData>({
    patient_id: '',
    full_name: '',
    date_of_birth: '',
    gender: '',
    ip_id: '',
    op_id: '',
    add_info: ''
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<CreateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Doctor multi-select state
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [selectedDoctorIds, setSelectedDoctorIds] = useState<string[]>([]);
  const [isDoctorsLoading, setIsDoctorsLoading] = useState(true);
  const [doctorSearchQuery, setDoctorSearchQuery] = useState('');

  // Load doctors on mount
  useEffect(() => {
    const loadDoctors = async () => {
      try {
        setIsDoctorsLoading(true);
        const accessToken = getAccessToken();
        const data = await getDoctors(true, accessToken);
        setDoctors(data);
      } catch (err) {
        console.error('Error loading doctors:', err);
      } finally {
        setIsDoctorsLoading(false);
      }
    };
    loadDoctors();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount

  // Filter doctors based on search
  const filteredDoctors = doctors.filter(doctor => {
    if (!doctorSearchQuery.trim()) return true;
    const query = doctorSearchQuery.toLowerCase();
    return (
      doctor.full_name.toLowerCase().includes(query) ||
      doctor.email.toLowerCase().includes(query) ||
      (doctor.specialization && doctor.specialization.toLowerCase().includes(query))
    );
  });

  const toggleDoctorSelection = (doctorId: string) => {
    setSelectedDoctorIds(prev =>
      prev.includes(doctorId)
        ? prev.filter(id => id !== doctorId)
        : [...prev, doctorId]
    );
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setResult(null);
    setError(null);

    // Validate required field
    if (!formData.patient_id.trim()) {
      setError('Student ID (UHID) is required');
      setIsSubmitting(false);
      return;
    }

    try {
      const token = await getAccessToken();

      // Build request body
      const body: Record<string, unknown> = {
        patient_id: formData.patient_id.trim()
      };

      if (formData.full_name.trim()) body.full_name = formData.full_name.trim();
      if (formData.date_of_birth) body.date_of_birth = formData.date_of_birth;
      if (formData.gender) body.gender = formData.gender;
      if (formData.ip_id.trim()) body.ip_id = formData.ip_id.trim();
      if (formData.op_id.trim()) body.op_id = formData.op_id.trim();
      if (selectedDoctorIds.length > 0) body.doctor_ids = selectedDoctorIds;

      // Parse add_info JSON if provided
      if (formData.add_info.trim()) {
        try {
          body.add_info = JSON.parse(formData.add_info);
        } catch {
          setError('Invalid JSON in Additional Info field');
          setIsSubmitting(false);
          return;
        }
      }

      const response = await fetch(`${API_CONFIG.backendUrl}/api/v1/patients`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify(body)
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to create student');
      }

      setResult(data);

      // Clear form on successful creation
      if (data.created) {
        setFormData({
          patient_id: '',
          full_name: '',
          date_of_birth: '',
          gender: '',
          ip_id: '',
          op_id: '',
          add_info: ''
        });
        setSelectedDoctorIds([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create student');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClear = () => {
    setFormData({
      patient_id: '',
      full_name: '',
      date_of_birth: '',
      gender: '',
      ip_id: '',
      op_id: '',
      add_info: ''
    });
    setSelectedDoctorIds([]);
    setDoctorSearchQuery('');
    setResult(null);
    setError(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white">Create Student</h2>
          <p className="text-sm text-slate-400 mt-1">
            Add a new student to the system
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Form Section */}
        <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Patient ID - Required */}
            <div>
              <label htmlFor="patient_id" className="block text-sm font-medium text-slate-300 mb-1">
                Student ID (UHID) <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                id="patient_id"
                name="patient_id"
                value={formData.patient_id}
                onChange={handleInputChange}
                placeholder="e.g., UHID123456"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent"
                required
              />
            </div>

            {/* Full Name */}
            <div>
              <label htmlFor="full_name" className="block text-sm font-medium text-slate-300 mb-1">
                Full Name
              </label>
              <input
                type="text"
                id="full_name"
                name="full_name"
                value={formData.full_name}
                onChange={handleInputChange}
                placeholder="Student's full name"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent"
              />
            </div>

            {/* Date of Birth */}
            <div>
              <label htmlFor="date_of_birth" className="block text-sm font-medium text-slate-300 mb-1">
                Date of Birth
              </label>
              <input
                type="date"
                id="date_of_birth"
                name="date_of_birth"
                value={formData.date_of_birth}
                onChange={handleInputChange}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent"
              />
            </div>

            {/* Gender */}
            <div>
              <label htmlFor="gender" className="block text-sm font-medium text-slate-300 mb-1">
                Gender
              </label>
              <select
                id="gender"
                name="gender"
                value={formData.gender}
                onChange={handleInputChange}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent"
              >
                <option value="">Select gender</option>
                <option value="M">Male</option>
                <option value="F">Female</option>
                <option value="O">Other</option>
              </select>
            </div>

            {/* IP ID and OP ID in a row */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="ip_id" className="block text-sm font-medium text-slate-300 mb-1">
                  Inpatient ID
                </label>
                <input
                  type="text"
                  id="ip_id"
                  name="ip_id"
                  value={formData.ip_id}
                  onChange={handleInputChange}
                  placeholder="IP ID"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent"
                />
              </div>
              <div>
                <label htmlFor="op_id" className="block text-sm font-medium text-slate-300 mb-1">
                  Outpatient ID
                </label>
                <input
                  type="text"
                  id="op_id"
                  name="op_id"
                  value={formData.op_id}
                  onChange={handleInputChange}
                  placeholder="OP ID"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent"
                />
              </div>
            </div>

            {/* Linked Doctors (Multi-select) */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Linked Counsellors
              </label>
              {isDoctorsLoading ? (
                <div className="flex items-center gap-2 text-slate-400 text-sm py-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-slate-400"></div>
                  Loading counsellors...
                </div>
              ) : (
                <div className="space-y-2">
                  {/* Search input */}
                  <input
                    type="text"
                    value={doctorSearchQuery}
                    onChange={(e) => setDoctorSearchQuery(e.target.value)}
                    placeholder="Search counsellors..."
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent text-sm"
                  />

                  {/* Selected doctors chips */}
                  {selectedDoctorIds.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {selectedDoctorIds.map(id => {
                        const doctor = doctors.find(d => d.id === id);
                        return doctor ? (
                          <span
                            key={id}
                            className="inline-flex items-center gap-1 px-2 py-1 bg-lime-600/30 text-lime-300 rounded text-xs"
                          >
                            {doctor.full_name}
                            <button
                              type="button"
                              onClick={() => toggleDoctorSelection(id)}
                              className="hover:text-lime-100"
                            >
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </span>
                        ) : null;
                      })}
                    </div>
                  )}

                  {/* Doctor list */}
                  <div className="max-h-40 overflow-y-auto bg-slate-800 rounded-lg border border-slate-600">
                    {filteredDoctors.length === 0 ? (
                      <div className="px-3 py-2 text-slate-500 text-sm">No counsellors found</div>
                    ) : (
                      filteredDoctors.map(doctor => (
                        <label
                          key={doctor.id}
                          className={`flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-slate-700 transition-colors ${
                            selectedDoctorIds.includes(doctor.id) ? 'bg-slate-700/50' : ''
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedDoctorIds.includes(doctor.id)}
                            onChange={() => toggleDoctorSelection(doctor.id)}
                            className="rounded border-slate-500 bg-slate-600 text-lime-500 focus:ring-lime-500"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-white truncate">{doctor.full_name}</div>
                            <div className="text-xs text-slate-400 truncate">
                              {doctor.specialization || doctor.email}
                            </div>
                          </div>
                        </label>
                      ))
                    )}
                  </div>
                </div>
              )}
              <p className="text-xs text-slate-500 mt-1">Select counsellors this student is linked to</p>
            </div>

            {/* Additional Info (JSON) */}
            <div>
              <label htmlFor="add_info" className="block text-sm font-medium text-slate-300 mb-1">
                Additional Info (JSON)
              </label>
              <textarea
                id="add_info"
                name="add_info"
                value={formData.add_info}
                onChange={handleInputChange}
                placeholder='{"roomNo": "101", "bedNo": "A"}'
                rows={3}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent font-mono text-sm"
              />
              <p className="text-xs text-slate-500 mt-1">Optional JSON object for custom fields</p>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex-1 px-4 py-2 bg-lime-600 hover:bg-lime-700 disabled:bg-lime-800 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Creating...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    Create Student
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={handleClear}
                className="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white font-medium rounded-lg transition-colors"
              >
                Clear
              </button>
            </div>
          </form>
        </div>

        {/* Result Section */}
        <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700">
          <h3 className="text-lg font-medium text-white mb-4">Result</h3>

          {error && (
            <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="font-medium">Error</span>
              </div>
              <p className="mt-2">{error}</p>
            </div>
          )}

          {result && (
            <div className={`rounded-lg p-4 ${result.created ? 'bg-green-900/30 border border-green-700' : 'bg-amber-900/30 border border-amber-700'}`}>
              <div className="flex items-center gap-2 mb-3">
                {result.created ? (
                  <>
                    <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="font-medium text-green-300">Student Created</span>
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span className="font-medium text-amber-300">Student Already Exists</span>
                  </>
                )}
              </div>
              <p className="text-slate-300 text-sm mb-3">{result.message}</p>

              {result.patient && (
                <div className="bg-slate-900/50 rounded-lg p-3 mt-3">
                  <h4 className="text-sm font-medium text-slate-400 mb-2">Student Details</h4>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-400">ID:</span>
                      <span className="text-white font-mono">{result.patient.id as string}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Student ID:</span>
                      <span className="text-white">{result.patient.patient_id as string}</span>
                    </div>
                    {result.patient.full_name ? (
                      <div className="flex justify-between">
                        <span className="text-slate-400">Name:</span>
                        <span className="text-white">{String(result.patient.full_name)}</span>
                      </div>
                    ) : null}
                    {result.patient.date_of_birth ? (
                      <div className="flex justify-between">
                        <span className="text-slate-400">DOB:</span>
                        <span className="text-white">{String(result.patient.date_of_birth)}</span>
                      </div>
                    ) : null}
                    {result.patient.gender ? (
                      <div className="flex justify-between">
                        <span className="text-slate-400">Gender:</span>
                        <span className="text-white">{String(result.patient.gender)}</span>
                      </div>
                    ) : null}
                    {result.patient.ip_id ? (
                      <div className="flex justify-between">
                        <span className="text-slate-400">IP ID:</span>
                        <span className="text-white">{String(result.patient.ip_id)}</span>
                      </div>
                    ) : null}
                    {result.patient.op_id ? (
                      <div className="flex justify-between">
                        <span className="text-slate-400">OP ID:</span>
                        <span className="text-white">{String(result.patient.op_id)}</span>
                      </div>
                    ) : null}
                    {result.patient.doctor_ids && Array.isArray(result.patient.doctor_ids) && (result.patient.doctor_ids as string[]).length > 0 ? (
                      <div className="mt-2 pt-2 border-t border-slate-700">
                        <span className="text-slate-400 text-xs">Linked Counsellors:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {(result.patient.doctor_ids as string[]).map((docId: string) => {
                            const doctor = doctors.find(d => d.id === docId);
                            return (
                              <span key={docId} className="px-2 py-0.5 bg-lime-600/20 text-lime-300 rounded text-xs">
                                {doctor ? doctor.full_name : docId}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                    {result.patient.add_info && Object.keys(result.patient.add_info as object).length > 0 ? (
                      <div className="mt-2 pt-2 border-t border-slate-700">
                        <span className="text-slate-400 text-xs">Additional Info:</span>
                        <pre className="text-xs text-slate-300 mt-1 bg-slate-800 p-2 rounded overflow-x-auto">
                          {JSON.stringify(result.patient.add_info, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                  </div>
                </div>
              )}
            </div>
          )}

          {!error && !result && (
            <div className="text-center py-8 text-slate-500">
              <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <p>Fill in the form and click "Create Student"</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
