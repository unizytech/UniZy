"use client";

/**
 * NurseSelector Component
 *
 * Dropdown selector for choosing a nurse from the list of active nurses.
 * Used in VHR screen for optional nurse selection alongside doctor selection.
 *
 * Features:
 * - Loads active nurses from API
 * - Search/filter functionality
 * - Displays nurse name, qualification, and email
 * - Loading and error states
 * - Emits selected nurse_id to parent component
 */

import { useState, useEffect } from 'react';
import { getNurses, type Nurse } from '@/services/nurseApi';
import { useAuth } from '@lib/auth';

interface NurseSelectorProps {
  selectedNurseId: string | null;
  onNurseSelect: (nurseId: string | null) => void;
  className?: string;
  required?: boolean;
  hospitalId?: string;  // Optional filter by hospital
}

export default function NurseSelector({
  selectedNurseId,
  onNurseSelect,
  className = '',
  required = false,
  hospitalId
}: NurseSelectorProps) {
  const { getAccessToken, loading: authLoading } = useAuth();
  const [nurses, setNurses] = useState<Nurse[]>([]);
  const [filteredNurses, setFilteredNurses] = useState<Nurse[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);

  // Load nurses when auth is ready (only once, or when hospitalId changes)
  useEffect(() => {
    // Prevent re-fetching if already loaded (avoids loop on auth state changes)
    if (hasLoaded && !hospitalId) return;

    if (!authLoading) {
      const token = getAccessToken();
      if (token) {
        setHasLoaded(true);
        loadNurses();
      }
    }
    // Note: getAccessToken excluded from deps to prevent loop on auth state changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, hospitalId]);

  // Filter nurses based on search query
  useEffect(() => {
    if (searchQuery.trim() === '') {
      setFilteredNurses(nurses);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = nurses.filter(
        (nurse) =>
          nurse.full_name.toLowerCase().includes(query) ||
          nurse.email.toLowerCase().includes(query) ||
          (nurse.qualification && nurse.qualification.toLowerCase().includes(query))
      );
      setFilteredNurses(filtered);
    }
  }, [searchQuery, nurses]);

  const loadNurses = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const accessToken = getAccessToken();
      const data = await getNurses(true, hospitalId, accessToken); // Active nurses only
      setNurses(data);
      setFilteredNurses(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load nurses');
      console.error('Error loading nurses:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectNurse = (nurseId: string | null) => {
    onNurseSelect(nurseId);
    setIsOpen(false);
    setSearchQuery('');
  };

  const selectedNurse = nurses.find((n) => n.id === selectedNurseId);

  // Qualification badge color mapping
  const getQualificationColor = (qualification: string | null): string => {
    if (!qualification) return 'bg-gray-100 dark:bg-gray-700';
    const q = qualification.toUpperCase();
    if (q.includes('RN') || q.includes('BSN')) return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
    if (q.includes('LPN') || q.includes('LVN')) return 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300';
    if (q.includes('NP') || q.includes('APRN')) return 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300';
    return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300';
  };

  return (
    <div className={`relative ${className}`}>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        Select Nurse {required && <span className="text-red-500">*</span>}
        {!required && <span className="text-gray-400 dark:text-gray-500 text-xs ml-1">(Optional)</span>}
      </label>

      {/* Dropdown Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className="w-full px-4 py-3 text-left bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-sm hover:border-teal-500 dark:hover:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-500 dark:focus:ring-teal-400 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            {isLoading ? (
              <span className="text-gray-500 dark:text-gray-400">Loading nurses...</span>
            ) : selectedNurse ? (
              <div>
                <div className="font-medium text-gray-900 dark:text-white truncate">
                  {selectedNurse.full_name}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400 truncate">
                  {selectedNurse.qualification && `${selectedNurse.qualification} • `}
                  {selectedNurse.email}
                </div>
              </div>
            ) : (
              <span className="text-gray-500 dark:text-gray-400">Select a nurse...</span>
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
              placeholder="Search nurses..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 dark:focus:ring-teal-400 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400"
              autoFocus
            />
          </div>

          {/* Nurse List */}
          <div className="overflow-y-auto max-h-80">
            {/* Clear Selection Option */}
            {!required && selectedNurseId && (
              <button
                type="button"
                onClick={() => handleSelectNurse(null)}
                className="w-full px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-700 border-b border-gray-200 dark:border-gray-700 transition-colors"
              >
                <div className="text-sm text-gray-500 dark:text-gray-400 italic">
                  Clear selection
                </div>
              </button>
            )}

            {filteredNurses.length === 0 ? (
              <div className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                {searchQuery ? 'No nurses found matching your search' : 'No active nurses available'}
              </div>
            ) : (
              filteredNurses.map((nurse) => (
                <button
                  key={nurse.id}
                  type="button"
                  onClick={() => handleSelectNurse(nurse.id)}
                  className={`w-full px-4 py-3 text-left hover:bg-teal-50 dark:hover:bg-teal-900/20 transition-colors ${
                    selectedNurseId === nurse.id
                      ? 'bg-teal-50 dark:bg-teal-900/30 border-l-4 border-teal-500'
                      : ''
                  }`}
                >
                  <div className="font-medium text-gray-900 dark:text-white">
                    {nurse.full_name}
                    {selectedNurseId === nurse.id && (
                      <span className="ml-2 text-teal-600 dark:text-teal-400">✓</span>
                    )}
                  </div>
                  <div className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">
                    {nurse.qualification && (
                      <span className={`inline-block mr-2 px-2 py-0.5 rounded text-xs font-medium ${getQualificationColor(nurse.qualification)}`}>
                        {nurse.qualification}
                      </span>
                    )}
                    {nurse.email}
                  </div>
                </button>
              ))
            )}
          </div>

          {/* Refresh Button */}
          <div className="p-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
            <button
              type="button"
              onClick={loadNurses}
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
            {error}
          </p>
          <button
            onClick={loadNurses}
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
