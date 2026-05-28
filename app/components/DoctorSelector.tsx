"use client";

/**
 * DoctorSelector Component
 *
 * Dropdown selector for choosing a doctor from the list of active doctors.
 * Used at the top of Medical Summary screen before consultation type selection.
 *
 * Features:
 * - Loads active doctors from API
 * - Search/filter functionality
 * - Displays doctor name, specialization, and email
 * - Loading and error states
 * - Emits selected doctor_id to parent component
 */

import { useState, useEffect } from 'react';
import { getDoctors, type Doctor } from '@/services/doctorApi';
import { useAuth } from '@lib/auth';

interface DoctorSelectorProps {
  selectedDoctorId: string | null;
  onDoctorSelect: (doctorId: string | null) => void;
  className?: string;
  required?: boolean;
}

export default function DoctorSelector({
  selectedDoctorId,
  onDoctorSelect,
  className = '',
  required = false
}: DoctorSelectorProps) {
  const { getAccessToken, loading: authLoading } = useAuth();
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [filteredDoctors, setFilteredDoctors] = useState<Doctor[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);

  // Load doctors when auth is ready (only once)
  useEffect(() => {
    if (!authLoading && !hasLoaded) {
      const token = getAccessToken();
      if (token) {
        setHasLoaded(true);
        loadDoctors();
      }
    }
  }, [authLoading, getAccessToken, hasLoaded]);

  // Filter doctors based on search query
  useEffect(() => {
    if (searchQuery.trim() === '') {
      setFilteredDoctors(doctors);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = doctors.filter(
        (doctor) =>
          doctor.full_name.toLowerCase().includes(query) ||
          doctor.email.toLowerCase().includes(query) ||
          (doctor.specialization && doctor.specialization.toLowerCase().includes(query))
      );
      setFilteredDoctors(filtered);
    }
  }, [searchQuery, doctors]);

  const loadDoctors = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const accessToken = getAccessToken();
      const data = await getDoctors(true, accessToken); // Active doctors only
      setDoctors(data);
      setFilteredDoctors(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load doctors');
      console.error('Error loading doctors:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectDoctor = (doctorId: string | null) => {
    onDoctorSelect(doctorId);
    setIsOpen(false);
    setSearchQuery('');
  };

  const selectedDoctor = doctors.find((d) => d.id === selectedDoctorId);

  return (
    <div className={`relative ${className}`}>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        Select Doctor {required && <span className="text-red-500">*</span>}
      </label>

      {/* Dropdown Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className="w-full px-4 py-3 text-left bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-sm hover:border-blue-500 dark:hover:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            {isLoading ? (
              <span className="text-gray-500 dark:text-gray-400">Loading doctors...</span>
            ) : selectedDoctor ? (
              <div>
                <div className="font-medium text-gray-900 dark:text-white truncate">
                  {selectedDoctor.full_name}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400 truncate">
                  {selectedDoctor.specialization && `${selectedDoctor.specialization} • `}
                  {selectedDoctor.email}
                </div>
              </div>
            ) : (
              <span className="text-gray-500 dark:text-gray-400">Select a doctor...</span>
            )}
          </div>
          <svg
            className={`ml-2 h-5 w-5 text-gray-400 transition-transform ${
              isOpen ? 'transform rotate-180' : ''
            }`}
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      </button>

      {/* Dropdown Panel */}
      {isOpen && !isLoading && (
        <div className="absolute z-50 mt-2 w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-96 overflow-hidden">
          {/* Search Input */}
          <div className="p-3 border-b border-gray-200 dark:border-gray-700">
            <input
              type="text"
              placeholder="Search doctors..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400"
              autoFocus
            />
          </div>

          {/* Doctor List */}
          <div className="overflow-y-auto max-h-80">
            {/* Clear Selection Option */}
            {!required && selectedDoctorId && (
              <button
                type="button"
                onClick={() => handleSelectDoctor(null)}
                className="w-full px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-700 border-b border-gray-200 dark:border-gray-700 transition-colors"
              >
                <div className="text-sm text-gray-500 dark:text-gray-400 italic">
                  Clear selection
                </div>
              </button>
            )}

            {filteredDoctors.length === 0 ? (
              <div className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                {searchQuery ? 'No doctors found matching your search' : 'No active doctors available'}
              </div>
            ) : (
              filteredDoctors.map((doctor) => (
                <button
                  key={doctor.id}
                  type="button"
                  onClick={() => handleSelectDoctor(doctor.id)}
                  className={`w-full px-4 py-3 text-left hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors ${
                    selectedDoctorId === doctor.id
                      ? 'bg-blue-50 dark:bg-blue-900/30 border-l-4 border-blue-500'
                      : ''
                  }`}
                >
                  <div className="font-medium text-gray-900 dark:text-white">
                    {doctor.full_name}
                    {selectedDoctorId === doctor.id && (
                      <span className="ml-2 text-blue-600 dark:text-blue-400">✓</span>
                    )}
                  </div>
                  <div className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">
                    {doctor.specialization && (
                      <span className="inline-block mr-2 px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs font-medium">
                        {doctor.specialization}
                      </span>
                    )}
                    {doctor.email}
                  </div>
                </button>
              ))
            )}
          </div>

          {/* Refresh Button */}
          <div className="p-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
            <button
              type="button"
              onClick={loadDoctors}
              className="w-full px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
            >
              ↻ Refresh List
            </button>
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mt-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <p className="text-sm text-red-600 dark:text-red-400">
            ⚠️ {error}
          </p>
          <button
            onClick={loadDoctors}
            className="mt-2 text-sm text-red-700 dark:text-red-300 hover:text-red-900 dark:hover:text-red-100 font-medium"
          >
            Try again
          </button>
        </div>
      )}

      {/* Click outside to close */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}
    </div>
  );
}
