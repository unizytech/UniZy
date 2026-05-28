'use client';

import React, { useState, useEffect } from 'react';
import { useAuth } from '@lib/auth';
import RecordTab from './components/RecordTab';
import CompareTranscriptTab from './components/CompareTranscriptTab';
import { VHRScreen } from './components/VHRScreen';
import DoctorTemplateConfigScreen from './components/DoctorTemplateConfigScreen';
import { TemplateAdminScreen } from './components/TemplateAdminScreen';
import { SystemPromptAdminScreen } from './components/SystemPromptAdminScreen';
import { MedicineListAdminScreen } from './components/MedicineListAdminScreen';
import { InvestigationListAdminScreen } from './components/InvestigationListAdminScreen';
import { ExtractionHistoryScreen } from './components/ExtractionHistoryScreen';
import { UsageSummaryScreen } from './components/UsageSummaryScreen';
import { PocMetricsScreen } from './components/PocMetricsScreen';
import { PatientHistoryScreen } from './components/PatientHistoryScreen';
import { LoginScreen } from './components/LoginScreen';
import { APIKeysScreen } from './components/APIKeysScreen';
import { ProcessingModesAdminScreen } from './components/ProcessingModesAdminScreen';
import ProvidersScreen from './components/ProvidersScreen';
import { PatientCreateScreen } from './components/PatientCreateScreen';
import DashboardScreen from './components/DashboardScreen';
import { HospitalDefaultTemplateScreen } from './components/HospitalDefaultTemplateScreen';
import QAEngineScreen from './components/QAEngineScreen';
import { TriageLayersAdminScreen } from './components/TriageLayersAdminScreen';
import DoctorSharingScreen from './components/DoctorSharingScreen';
import { TemplateFieldConfigScreen } from './components/TemplateFieldConfigScreen';
import { AppMode } from '@lib/types';

export default function Home() {
  const { user, adminUser, loading, signOut, isAdmin, isHospitalAdmin } = useAuth();
  const [mode, setMode] = useState<AppMode>(AppMode.VHR);

  // Force Dashboard mode for hospital admins once auth loads
  useEffect(() => {
    if (isHospitalAdmin) {
      setMode(AppMode.Dashboard);
    }
  }, [isHospitalAdmin]);

  // Show loading spinner while checking auth
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-slate-400">Loading...</p>
        </div>
      </div>
    );
  }

  // Show login screen if not authenticated
  if (!user || !isAdmin) {
    return <LoginScreen />;
  }

  // Use admin user ID for components that need it
  const userId = adminUser?.id || 'admin-user-1';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white p-4 sm:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div className="text-center flex-1">
            <h1 className="text-3xl sm:text-4xl font-bold mb-2 bg-gradient-to-r from-blue-400 to-purple-400 text-transparent bg-clip-text">
              Internal Test Environment - Unizy AI
            </h1>
            <p className="text-slate-400 text-sm sm:text-base">
              AI-powered medical consultation transcription & insights extraction
            </p>
          </div>

          {/* User Menu */}
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-sm font-medium text-white">{adminUser?.full_name || adminUser?.email}</p>
              <p className="text-xs text-slate-400">{adminUser?.role?.replace('_', ' ')}</p>
            </div>
            <button
              onClick={() => signOut()}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
              title="Sign out"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="space-y-4 mb-8">
          {/* Hospital Admin: Only Dashboard tab */}
          {isHospitalAdmin ? (
            <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-700/50">
              <div className="flex flex-wrap justify-center gap-2">
                <button
                  onClick={() => setMode(AppMode.Dashboard)}
                  className="px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 bg-violet-600 text-white shadow-lg shadow-violet-500/50"
                >
                  Dashboard
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* User Test Category */}
              <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-700/50">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">User Test</span>
                  <div className="flex-1 h-px bg-slate-700"></div>
                </div>
                <div className="flex flex-wrap justify-center gap-2">
                  <button
                    onClick={() => setMode(AppMode.VHR)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.VHR
                        ? 'bg-cyan-600 text-white shadow-lg shadow-cyan-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    VHR
                  </button>
                  <button
                    onClick={() => setMode(AppMode.Live)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.Live
                        ? 'bg-green-600 text-white shadow-lg shadow-green-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Live
                  </button>
                  <button
                    onClick={() => setMode(AppMode.PatientHistory)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.PatientHistory
                        ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Patient
                  </button>
                  <button
                    onClick={() => setMode(AppMode.PatientCreate)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.PatientCreate
                        ? 'bg-lime-600 text-white shadow-lg shadow-lime-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Add Patient
                  </button>
                  <button
                    onClick={() => setMode(AppMode.Dashboard)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.Dashboard
                        ? 'bg-violet-600 text-white shadow-lg shadow-violet-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Dashboard
                  </button>
                  <button
                    onClick={() => setMode(AppMode.QAEngine)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.QAEngine
                        ? 'bg-rose-600 text-white shadow-lg shadow-rose-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Q&A
                  </button>
                  <button
                    onClick={() => setMode(AppMode.DoctorConfig)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.DoctorConfig
                        ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Doctor Config
                  </button>
                  <button
                    onClick={() => setMode(AppMode.MedicineAdmin)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.MedicineAdmin
                        ? 'bg-teal-600 text-white shadow-lg shadow-teal-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Medicines
                  </button>
                  <button
                    onClick={() => setMode(AppMode.InvestigationAdmin)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.InvestigationAdmin
                        ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Investigations
                  </button>
                </div>
              </div>

              {/* Admin Category */}
              <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-700/50">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Admin</span>
                  <div className="flex-1 h-px bg-slate-700"></div>
                </div>
                <div className="flex flex-wrap justify-center gap-2">
                  <button
                    onClick={() => setMode(AppMode.TemplateAdmin)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.TemplateAdmin
                        ? 'bg-pink-600 text-white shadow-lg shadow-pink-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Config
                  </button>
                  <button
                    onClick={() => setMode(AppMode.SystemPromptAdmin)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.SystemPromptAdmin
                        ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Prompts
                  </button>
                  <button
                    onClick={() => setMode(AppMode.ProcessingModes)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.ProcessingModes
                        ? 'bg-cyan-700 text-white shadow-lg shadow-cyan-600/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Models
                  </button>
                  <button
                    onClick={() => setMode(AppMode.APIKeys)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.APIKeys
                        ? 'bg-rose-600 text-white shadow-lg shadow-rose-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    API Keys
                  </button>
                  <button
                    onClick={() => setMode(AppMode.ExtractionHistory)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.ExtractionHistory
                        ? 'bg-amber-600 text-white shadow-lg shadow-amber-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Usage
                  </button>
                  <button
                    onClick={() => setMode(AppMode.UsageSummary)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.UsageSummary
                        ? 'bg-yellow-600 text-white shadow-lg shadow-yellow-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Billing
                  </button>
                  <button
                    onClick={() => setMode(AppMode.Compare)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.Compare
                        ? 'bg-orange-600 text-white shadow-lg shadow-orange-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Compare
                  </button>
                  <button
                    onClick={() => setMode(AppMode.PocMetrics)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.PocMetrics
                        ? 'bg-pink-600 text-white shadow-lg shadow-pink-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    POC Metrics
                  </button>
                  <button
                    onClick={() => setMode(AppMode.Providers)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.Providers
                        ? 'bg-teal-600 text-white shadow-lg shadow-teal-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Providers
                  </button>
                  <button
                    onClick={() => setMode(AppMode.HospitalTemplates)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.HospitalTemplates
                        ? 'bg-sky-600 text-white shadow-lg shadow-sky-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Hospitals
                  </button>
                  <button
                    onClick={() => setMode(AppMode.TriageLayers)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.TriageLayers
                        ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Triage
                  </button>
                  <button
                    onClick={() => setMode(AppMode.DoctorSharing)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.DoctorSharing
                        ? 'bg-fuchsia-600 text-white shadow-lg shadow-fuchsia-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Dr Sharing
                  </button>
                  <button
                    onClick={() => setMode(AppMode.TemplateFieldConfig)}
                    className={`px-4 sm:px-6 py-2 sm:py-3 rounded-lg font-medium transition-all duration-200 ${
                      mode === AppMode.TemplateFieldConfig
                        ? 'bg-amber-600 text-white shadow-lg shadow-amber-500/50'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    Field Config
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Feature Description */}
        <div className="mb-6 p-4 bg-slate-800/50 rounded-lg">
          <p className="text-sm text-slate-300">
            {mode === AppMode.VHR && (
              <>
                <strong className="text-cyan-400">VHR:</strong> Virtual Health Record - Unified medical documentation with voice recording and file upload.
                Supports both WebSocket recording (Ultra mode) and chunked recording (Fast/Default/Thorough modes) with progressive extraction.
              </>
            )}
            {mode === AppMode.Live && (
              <>
                <strong className="text-green-400">Live:</strong> Real-time audio transcription and insights extraction.
                Medical extraction happens via secure backend API after recording stops.
              </>
            )}
            {mode === AppMode.PatientHistory && (
              <>
                <strong className="text-emerald-400">Patient:</strong> View complete patient medical history.
                Access last prescription, diagnosis, investigations, case summary, emotion analysis, and recommended interventions.
              </>
            )}
            {mode === AppMode.PatientCreate && (
              <>
                <strong className="text-lime-400">Add Patient:</strong> Create a new patient in the system.
                Enter patient ID (UHID), name, date of birth, gender, IP/OP IDs, and additional metadata.
              </>
            )}
            {mode === AppMode.Dashboard && (
              <>
                <strong className="text-violet-400">Dashboard:</strong> Hospital intelligence overview with intervention tracking.
                View patients at risk, track conversion opportunities, and manage intervention outcomes.
              </>
            )}
            {mode === AppMode.QAEngine && (
              <>
                <strong className="text-rose-400">Q&A Engine:</strong> Ask questions about your medical data using natural language.
                Get insights on diagnoses, prescriptions, patient trends, and more with AI-powered search and analytics.
              </>
            )}
            {mode === AppMode.DoctorConfig && (
              <>
                <strong className="text-indigo-400">Doctor Config:</strong> View preset visibility for doctors based on hospital and specialization.
                Shows platform-wide common templates, specialization-specific templates, and hospital-based peer templates.
              </>
            )}
            {mode === AppMode.TemplateAdmin && (
              <>
                <strong className="text-pink-400">Config:</strong> Create and configure templates from basic segments or inherit from consultation types.
                Drag-and-drop segment configuration with CORE, ADDITIONAL, and EXCLUDED categories.
              </>
            )}
            {mode === AppMode.SystemPromptAdmin && (
              <>
                <strong className="text-purple-400">Prompts:</strong> Manage dynamic system prompts with composable components.
                Create, version, and assign prompt configurations to consultation types with A/B testing support.
              </>
            )}
            {mode === AppMode.MedicineAdmin && (
              <>
                <strong className="text-teal-400">Medicines:</strong> Manage doctor and hospital medicine lists.
                Upload CSV, review AI matching feedback, and configure medicine name normalization.
              </>
            )}
            {mode === AppMode.InvestigationAdmin && (
              <>
                <strong className="text-blue-400">Investigations:</strong> Manage doctor and hospital investigation lists.
                Upload CSV with lab tests, imaging studies, and other investigations. Review AI matching feedback.
              </>
            )}
            {mode === AppMode.ExtractionHistory && (
              <>
                <strong className="text-amber-400">Usage:</strong> View past extractions with LLM usage data.
                Track token costs, cache savings, and processing times for each extraction.
              </>
            )}
            {mode === AppMode.UsageSummary && (
              <>
                <strong className="text-yellow-400">Billing:</strong> View aggregated LLM usage by API client, hospital, or doctor.
                Track total costs, recording hours, and export data for billing purposes.
              </>
            )}
            {mode === AppMode.ProcessingModes && (
              <>
                <strong className="text-cyan-500">Models:</strong> Configure processing modes with Gemini model assignments.
                Set models for transcription, extraction, triage, merge, and comparison operations.
              </>
            )}
            {mode === AppMode.APIKeys && (
              <>
                <strong className="text-rose-400">API Keys:</strong> Create and manage API keys for hospital EHR integrations.
                Generate keys, rotate credentials, and monitor usage for secure API access.
              </>
            )}
            {mode === AppMode.Compare && (
              <>
                <strong className="text-orange-400">Compare:</strong> View an extraction&apos;s original AI output, latest doctor edits,
                and the formatted EHR payload sent to the hospital — side-by-side, by extraction ID.
              </>
            )}
            {mode === AppMode.Providers && (
              <>
                <strong className="text-teal-400">Providers:</strong> Manage doctors, nurses, and hospitals.
                Create and edit provider profiles, link nurses to doctors, and manage hospital configurations.
              </>
            )}
            {mode === AppMode.HospitalTemplates && (
              <>
                <strong className="text-sky-400">Hospitals:</strong> Set default extraction templates for hospitals.
                Hospital defaults apply to all doctors in that hospital unless the doctor has their own default set.
              </>
            )}
            {mode === AppMode.TriageLayers && (
              <>
                <strong className="text-emerald-400">Triage Layers:</strong> Configure multi-layer triage engine.
                Enable/disable layers for doctor practice patterns, hospital peer intelligence, and RAG clinical guidelines.
                Adjust layer weights for conflict resolution.
              </>
            )}
            {mode === AppMode.DoctorSharing && (
              <>
                <strong className="text-fuchsia-400">Doctor Sharing:</strong> Manage cross-doctor patient sharing links.
                Link doctors to share all patients (practice-wide) or specific patients (selective handoff).
                Enables continuation detection and context sharing across linked doctors.
              </>
            )}
            {mode === AppMode.TemplateFieldConfig && (
              <>
                <strong className="text-amber-400">Field Config:</strong> Pick which fields are tracked by the
                public extraction-gaps API and which segments are sent in the empty-payload template-schema API.
                Defaults keep both APIs backward-compatible for external consumers.
              </>
            )}
          </p>
        </div>

        {/* Content Area */}
        <div className="bg-slate-800/30 rounded-xl p-4 sm:p-8 backdrop-blur-sm border border-slate-700">
          {mode === AppMode.VHR && <VHRScreen />}
          {mode === AppMode.Live && <RecordTab />}
          {mode === AppMode.PatientHistory && <PatientHistoryScreen />}
          {mode === AppMode.PatientCreate && <PatientCreateScreen />}
          {mode === AppMode.Dashboard && <DashboardScreen />}
          {mode === AppMode.QAEngine && <QAEngineScreen />}
          {mode === AppMode.DoctorConfig && <DoctorTemplateConfigScreen />}
          {mode === AppMode.TemplateAdmin && <TemplateAdminScreen userId={userId} />}
          {mode === AppMode.SystemPromptAdmin && <SystemPromptAdminScreen />}
          {mode === AppMode.MedicineAdmin && <MedicineListAdminScreen />}
          {mode === AppMode.InvestigationAdmin && <InvestigationListAdminScreen />}
          {mode === AppMode.ExtractionHistory && <ExtractionHistoryScreen />}
          {mode === AppMode.UsageSummary && <UsageSummaryScreen />}
          {mode === AppMode.PocMetrics && <PocMetricsScreen />}
          {mode === AppMode.ProcessingModes && <ProcessingModesAdminScreen />}
          {mode === AppMode.APIKeys && <APIKeysScreen />}
          {mode === AppMode.Compare && <CompareTranscriptTab />}
          {mode === AppMode.Providers && <ProvidersScreen />}
          {mode === AppMode.HospitalTemplates && <HospitalDefaultTemplateScreen />}
          {mode === AppMode.TriageLayers && <TriageLayersAdminScreen />}
          {mode === AppMode.DoctorSharing && <DoctorSharingScreen />}
          {mode === AppMode.TemplateFieldConfig && <TemplateFieldConfigScreen />}
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-slate-500 text-sm">
          <p>Unizy proprietary AI models</p>
          <p className="mt-1">
            See <span className="text-blue-400 font-mono">MOBILE_API.md</span> for mobile integration guide
          </p>
        </div>
      </div>
    </div>
  );
}
