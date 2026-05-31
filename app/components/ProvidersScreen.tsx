"use client";

/**
 * Providers Screen
 *
 * Wrapper with three sub-tabs: Doctors, Nurses, Hospitals.
 */

import { useState } from 'react';
import DoctorManageScreen from './DoctorManageScreen';
import NurseConfigScreen from './NurseConfigScreen';
import HospitalManageScreen from './HospitalManageScreen';

type ProviderTab = 'doctors' | 'nurses' | 'hospitals';

export default function ProvidersScreen() {
  const [activeTab, setActiveTab] = useState<ProviderTab>('doctors');

  const tabs: { key: ProviderTab; label: string }[] = [
    { key: 'doctors', label: 'Counsellors' },
    { key: 'nurses', label: 'Assistants' },
    { key: 'hospitals', label: 'Schools' },
  ];

  return (
    <div>
      {/* Sub-tab pills */}
      <div className="flex justify-center gap-2 mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-5 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
              activeTab === tab.key
                ? 'bg-teal-600 text-white shadow-lg shadow-teal-500/30'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'doctors' && <DoctorManageScreen />}
      {activeTab === 'nurses' && <NurseConfigScreen />}
      {activeTab === 'hospitals' && <HospitalManageScreen />}
    </div>
  );
}
