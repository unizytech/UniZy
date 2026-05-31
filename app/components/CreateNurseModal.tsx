"use client";

/**
 * CreateNurseModal Component
 *
 * Modal for creating a new nurse with basic profile information.
 * Form fields: full_name, email, qualification (optional)
 */

import { useState, useEffect } from 'react';
import { useAuth } from '@lib/auth';
import { createNurse } from '@/services/nurseApi';
import { getHospitals } from '@/services/doctorApi';

interface CreateNurseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (nurseId: string) => void;
}

interface Hospital {
  id: string;
  hospital_name: string;
}

export default function CreateNurseModal({
  isOpen,
  onClose,
  onCreated
}: CreateNurseModalProps) {
  const { getAccessToken } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    qualification: '',
    hospital_id: ''
  });

  // Load hospitals on mount
  useEffect(() => {
    if (isOpen) {
      loadHospitals();
    }
  }, [isOpen]);

  const loadHospitals = async () => {
    try {
      const token = getAccessToken();
      const data = await getHospitals(token);
      setHospitals(data);
    } catch (err) {
      console.error('Failed to load hospitals:', err);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!form.full_name.trim() || !form.email.trim()) {
      setError('Full name and email are required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const token = getAccessToken();
      const nurse = await createNurse({
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        qualification: form.qualification.trim() || undefined,
        hospital_id: form.hospital_id || undefined
      }, token);

      onCreated(nurse.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setForm({
      full_name: '',
      email: '',
      qualification: '',
      hospital_id: ''
    });
    setError(null);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg max-w-md w-full shadow-xl">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">Create New Assistant</h2>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-red-800 text-sm">{error}</p>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Full Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              placeholder="Enter assistant's full name"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email <span className="text-red-500">*</span>
            </label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="assistant@school.com"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Qualification
            </label>
            <input
              type="text"
              value={form.qualification}
              onChange={(e) => setForm({ ...form, qualification: e.target.value })}
              placeholder="e.g., RN, BSN, LPN, APRN"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Common qualifications: RN (Registered Assistant), BSN, LPN, NP, APRN
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              School
            </label>
            <select
              value={form.hospital_id}
              onChange={(e) => setForm({ ...form, hospital_id: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            >
              <option value="">Select school (optional)</option>
              {hospitals.map((hospital) => (
                <option key={hospital.id} value={hospital.id}>
                  {hospital.hospital_name}
                </option>
              ))}
            </select>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={handleClose}
              className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:bg-gray-300 disabled:cursor-not-allowed font-medium transition-colors"
            >
              {loading ? (
                <span className="flex items-center justify-center">
                  <svg className="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Creating...
                </span>
              ) : (
                'Create Assistant'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
