"use client";

/**
 * Providers Screen
 *
 * Wrapper with three sub-tabs: Counsellors, Assistants, Schools.
 */

import { useState } from 'react';
import CounsellorManageScreen from './CounsellorManageScreen';
import AssistantConfigScreen from './AssistantConfigScreen';
import SchoolManageScreen from './SchoolManageScreen';

type ProviderTab = 'counsellors' | 'assistants' | 'schools';

export default function ProvidersScreen() {
  const [activeTab, setActiveTab] = useState<ProviderTab>('counsellors');

  const tabs: { key: ProviderTab; label: string }[] = [
    { key: 'counsellors', label: 'Counsellors' },
    { key: 'assistants', label: 'Assistants' },
    { key: 'schools', label: 'Schools' },
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
      {activeTab === 'counsellors' && <CounsellorManageScreen />}
      {activeTab === 'assistants' && <AssistantConfigScreen />}
      {activeTab === 'schools' && <SchoolManageScreen />}
    </div>
  );
}
