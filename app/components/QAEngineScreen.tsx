'use client';

/**
 * Q&A Engine Screen
 *
 * RAG-based medical query interface for counsellors.
 * Features:
 * - Chat-style interface with message history
 * - Suggested questions by category
 * - Support for narrative, table, and chart responses
 * - Export functionality (CSV/PDF)
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import { qaApi } from '@lib/apiClient';
import { getSchools, getCounsellors, School, Counsellor } from '@lib/dashboardApi';
import { getConsultationTypes } from '@lib/summaryApi';
import { searchStudents, StudentSearchResult } from '@lib/studentHistoryApi';
import type {
  QAMessage,
  QAQueryResponse,
  QAPriorContext,
  SuggestedQuestion,
  QuestionCategory,
  ConsultationType,
  StudentVisit,
} from '@lib/types';
import QASuggestedQuestions from './qa/QASuggestedQuestions';
import QAChatMessage from './qa/QAChatMessage';
import QAResultsTable from './qa/QAResultsTable';
import QAChart from './qa/QAChart';
import QAExportButtons from './qa/QAExportButtons';

// ============================================================================
// Main Q&A Engine Component
// ============================================================================

export default function QAEngineScreen() {
  const { getAccessToken } = useAuth();
  const accessToken = getAccessToken();

  // School state
  const [hospitals, setSchools] = useState<School[]>([]);
  const [selectedSchoolId, setSelectedSchoolId] = useState<string | null>(null);
  const [hospitalsLoading, setSchoolsLoading] = useState(true);

  // Counsellor and Student filter state
  const [doctors, setCounsellors] = useState<Counsellor[]>([]);
  const [patients, setStudents] = useState<StudentSearchResult[]>([]);
  const [selectedCounsellorId, setSelectedCounsellorId] = useState<string | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [doctorsLoading, setCounsellorsLoading] = useState(false);
  const [patientsLoading, setStudentsLoading] = useState(false);

  // Consultation Type and Visit filter state (for temporal/longitudinal queries)
  const [consultationTypes, setConsultationTypes] = useState<ConsultationType[]>([]);
  const [selectedConsultationTypeId, setSelectedConsultationTypeId] = useState<string | null>(null);
  const [patientVisits, setStudentVisits] = useState<StudentVisit[]>([]);
  const [selectedVisitId, setSelectedVisitId] = useState<string | null>(null);
  const [visitsLoading, setVisitsLoading] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<QAMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState<SuggestedQuestion[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<QuestionCategory | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(true);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load schools on mount
  useEffect(() => {
    async function loadSchools() {
      if (!accessToken) return;

      try {
        const hospitalList = await getSchools(accessToken);
        setSchools(hospitalList);

        // Auto-select first school or find a default
        if (hospitalList.length > 0) {
          const defaultSchool = hospitalList.find(h => h.school_name?.toLowerCase().includes('guru')) || hospitalList[0];
          setSelectedSchoolId(defaultSchool.id);
        }
      } catch (err) {
        console.error('Failed to load schools:', err);
      } finally {
        setSchoolsLoading(false);
      }
    }

    loadSchools();
  }, [accessToken]);

  // Load counsellors when school changes
  useEffect(() => {
    async function loadCounsellors() {
      if (!accessToken || !selectedSchoolId) {
        setCounsellors([]);
        return;
      }

      setCounsellorsLoading(true);
      try {
        const doctorList = await getCounsellors({ hospitalId: selectedSchoolId }, accessToken);
        setCounsellors(doctorList);
      } catch (err) {
        console.error('Failed to load counsellors:', err);
        setCounsellors([]);
      } finally {
        setCounsellorsLoading(false);
      }
    }

    // Reset counsellor and student selection when school changes
    setSelectedCounsellorId(null);
    setSelectedStudentId(null);
    loadCounsellors();
  }, [accessToken, selectedSchoolId]);

  // Load students when counsellor is selected (counsellor_id is required by the API)
  useEffect(() => {
    async function loadStudents() {
      // Counsellor ID is required for student search API
      if (!accessToken || !selectedSchoolId || !selectedCounsellorId) {
        setStudents([]);
        return;
      }

      setStudentsLoading(true);
      try {
        // Search students for the selected counsellor
        const response = await searchStudents(
          '', // empty query to get all
          selectedCounsellorId,
          1, // page
          100, // page size - limit to 100 for dropdown
          accessToken
        );
        setStudents(response.students || []);
      } catch (err) {
        console.error('Failed to load students:', err);
        setStudents([]);
      } finally {
        setStudentsLoading(false);
      }
    }

    // Reset student selection when counsellor changes
    setSelectedStudentId(null);
    loadStudents();
  }, [accessToken, selectedSchoolId, selectedCounsellorId]);

  // Load consultation types when school changes
  useEffect(() => {
    async function loadConsultationTypes() {
      if (!accessToken || !selectedSchoolId) {
        setConsultationTypes([]);
        return;
      }

      try {
        const response = await getConsultationTypes(accessToken);
        setConsultationTypes(response.consultation_types || []);
      } catch (err) {
        console.error('Failed to load consultation types:', err);
        setConsultationTypes([]);
      }
    }

    setSelectedConsultationTypeId(null);
    loadConsultationTypes();
  }, [accessToken, selectedSchoolId]);

  // Load student visits when student is selected
  useEffect(() => {
    async function loadStudentVisits() {
      if (!accessToken || !selectedSchoolId || !selectedStudentId) {
        setStudentVisits([]);
        return;
      }

      setVisitsLoading(true);
      try {
        const response = await qaApi.getStudentVisits(
          { accessToken },
          selectedStudentId,
          selectedSchoolId,
          selectedCounsellorId || undefined,
          selectedConsultationTypeId || undefined
        );
        setStudentVisits(response.visits || []);
      } catch (err) {
        console.error('Failed to load student visits:', err);
        setStudentVisits([]);
      } finally {
        setVisitsLoading(false);
      }
    }

    // Reset visit selection when student changes
    setSelectedVisitId(null);
    loadStudentVisits();
  }, [accessToken, selectedSchoolId, selectedStudentId, selectedCounsellorId, selectedConsultationTypeId]);

  // Scroll to bottom when messages change
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Load suggested questions on mount
  useEffect(() => {
    async function loadSuggestedQuestions() {
      if (!accessToken) return;

      try {
        const response = await qaApi.getSuggestedQuestions(
          { accessToken },
          selectedCategory || undefined
        );
        setSuggestedQuestions(response.questions || []);
      } catch (err) {
        console.error('Failed to load suggested questions:', err);
      }
    }

    loadSuggestedQuestions();
  }, [accessToken, selectedCategory]);

  // Hide suggestions when there are messages
  useEffect(() => {
    setShowSuggestions(messages.length === 0);
  }, [messages]);

  // Handle query submission
  const handleSubmit = async (query: string) => {
    if (!query.trim() || !accessToken || isLoading) return;

    // Clear input
    setInputValue('');
    setError(null);

    // Add user message
    const userMessage: QAMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: new Date(),
    };

    // Add loading assistant message
    const loadingMessage: QAMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMessage, loadingMessage]);
    setIsLoading(true);

    try {
      // Build prior_context from last completed Q&A exchange
      let priorContext: QAPriorContext | undefined;
      const completedMessages = messages.filter(m => !m.isLoading);
      if (completedMessages.length >= 2) {
        // Find the last user-assistant pair
        const lastAssistant = [...completedMessages].reverse().find(m => m.role === 'assistant' && m.response);
        const lastUser = [...completedMessages].reverse().find(m => m.role === 'user');
        if (lastUser && lastAssistant) {
          priorContext = {
            query: lastUser.content,
            narrative: lastAssistant.response?.narrative || lastAssistant.content || undefined,
            intent: lastAssistant.response?.intent || undefined,
            extraction_id: lastAssistant.response?.referenced_visits?.[0]?.extraction_id
              || lastAssistant.response?.referenced_extraction_ids?.[0]
              || undefined,
          };
        }
      }

      const response = await qaApi.query({ accessToken }, {
        query,
        school_id: selectedSchoolId || undefined,
        counsellor_id: selectedCounsellorId || undefined,
        student_id: selectedStudentId || undefined,
        consultation_type_id: selectedConsultationTypeId || undefined,
        extraction_id: selectedVisitId || undefined,
        prior_context: priorContext,
        limit: 20,
      });

      // Update the loading message with the response
      setMessages((prev) => {
        const updated = [...prev];
        const loadingIdx = updated.findIndex((m) => m.isLoading);
        if (loadingIdx !== -1) {
          updated[loadingIdx] = {
            ...updated[loadingIdx],
            content: response.narrative || formatResponseContent(response),
            response,
            isLoading: false,
          };
        }
        return updated;
      });
    } catch (err) {
      console.error('Query failed:', err);
      const errorMessage = err instanceof Error ? err.message : 'Query failed';
      setError(errorMessage);

      // Update loading message to error state
      setMessages((prev) => {
        const updated = [...prev];
        const loadingIdx = updated.findIndex((m) => m.isLoading);
        if (loadingIdx !== -1) {
          updated[loadingIdx] = {
            ...updated[loadingIdx],
            content: `Error: ${errorMessage}`,
            isLoading: false,
          };
        }
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Handle suggested question click
  const handleSuggestedClick = (question: SuggestedQuestion) => {
    handleSubmit(question.question);
  };

  // Handle category filter
  const handleCategoryChange = (category: QuestionCategory | null) => {
    setSelectedCategory(category);
  };

  // Handle export
  const handleExport = async (format: 'csv' | 'pdf') => {
    if (!accessToken || messages.length === 0) return;

    // Find the last assistant message with results
    const lastAssistant = [...messages]
      .reverse()
      .find((m) => m.role === 'assistant' && m.response?.results);

    if (!lastAssistant?.response?.results) {
      setError('No results to export');
      return;
    }

    try {
      const result = await qaApi.exportResults(
        { accessToken },
        lastAssistant.response.query,
        lastAssistant.response.results,
        format
      );

      if (result.success && result.content) {
        // Download the file
        const blob = new Blob([result.content], {
          type: format === 'csv' ? 'text/csv' : 'application/pdf',
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = result.filename || `qa_export.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } else {
        setError(result.error_message || 'Export failed');
      }
    } catch (err) {
      console.error('Export failed:', err);
      setError(err instanceof Error ? err.message : 'Export failed');
    }
  };

  // Clear chat
  const handleClearChat = () => {
    setMessages([]);
    setError(null);
    setShowSuggestions(true);
    inputRef.current?.focus();
  };

  // Show loading state while schools are loading
  if (hospitalsLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-center p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-rose-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading schools...</p>
        </div>
      </div>
    );
  }

  // Check for school context
  if (!selectedSchoolId) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-center p-8">
          <div className="text-4xl mb-4">🏥</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            School Context Required
          </h2>
          <p className="text-gray-600">
            Please select a school to use the Q&A Engine.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        {/* Title Row */}
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <span className="text-rose-600">Q&A Engine</span>
            </h1>
            <p className="text-sm text-gray-500">
              Ask questions about your extractions using natural language
            </p>
          </div>
          <div className="flex items-center gap-3">
            {messages.length > 0 && (
              <>
                <QAExportButtons onExport={handleExport} disabled={isLoading} />
                <button
                  onClick={handleClearChat}
                  className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  Clear Chat
                </button>
              </>
            )}
          </div>
        </div>

        {/* Filter Selectors Row */}
        <div className="flex flex-wrap items-center gap-3">
          {/* School Selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-sm text-gray-500">🏥</span>
            <select
              value={selectedSchoolId || ''}
              onChange={(e) => {
                setSelectedSchoolId(e.target.value || null);
                setMessages([]);
                setError(null);
              }}
              className="w-[150px] px-2 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-transparent bg-white text-gray-700"
            >
              {hospitals.map((hospital) => (
                <option key={hospital.id} value={hospital.id}>
                  {hospital.school_name || 'Unnamed School'}
                </option>
              ))}
            </select>
          </div>

          {/* Counsellor Selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-sm text-gray-500">👨‍⚕️</span>
            <select
              value={selectedCounsellorId || ''}
              onChange={(e) => setSelectedCounsellorId(e.target.value || null)}
              disabled={doctorsLoading || doctors.length === 0}
              className="w-[130px] px-2 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-transparent bg-white text-gray-700 disabled:bg-gray-100 disabled:cursor-not-allowed"
            >
              <option value="">All Counsellors</option>
              {doctors.map((doctor) => (
                <option key={doctor.id} value={doctor.id}>
                  {doctor.full_name || doctor.counsellor_name || 'Unknown'}
                </option>
              ))}
            </select>
          </div>

          {/* Student Selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-sm text-gray-500">👤</span>
            <select
              value={selectedStudentId || ''}
              onChange={(e) => setSelectedStudentId(e.target.value || null)}
              disabled={!selectedCounsellorId || patientsLoading}
              className="w-[140px] px-2 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-transparent bg-white text-gray-700 disabled:bg-gray-100 disabled:cursor-not-allowed"
            >
              <option value="">
                {!selectedCounsellorId ? 'Select counsellor first' : 'All Students'}
              </option>
              {patients.map((patient) => (
                <option key={patient.id} value={patient.student_id}>
                  {patient.full_name || patient.student_id || 'Unknown'}
                  {patient.school_name ? ` (${patient.school_name})` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Consultation Type Selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-sm text-gray-500">📋</span>
            <select
              value={selectedConsultationTypeId || ''}
              onChange={(e) => setSelectedConsultationTypeId(e.target.value || null)}
              disabled={consultationTypes.length === 0}
              className="w-[120px] px-2 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-transparent bg-white text-gray-700 disabled:bg-gray-100 disabled:cursor-not-allowed"
            >
              <option value="">All Types</option>
              {consultationTypes.map((ct) => (
                <option key={ct.id} value={ct.id}>
                  {ct.type_name}
                </option>
              ))}
            </select>
          </div>

          {/* Visit Selector (Only shows when student is selected) */}
          {selectedStudentId && (
            <div className="flex items-center gap-1.5">
              <span className="text-sm text-gray-500">📅</span>
              <select
                value={selectedVisitId || ''}
                onChange={(e) => setSelectedVisitId(e.target.value || null)}
                disabled={visitsLoading || patientVisits.length === 0}
                className="w-[180px] px-2 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-transparent bg-white text-gray-700 disabled:bg-gray-100 disabled:cursor-not-allowed"
              >
                <option value="">All Visits</option>
                {patientVisits.map((visit) => (
                  <option key={visit.extraction_id} value={visit.extraction_id}>
                    {formatVisitDate(visit.created_at)} - {visit.consultation_type_name || 'Visit'}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.length === 0 && showSuggestions ? (
            <div className="max-w-4xl mx-auto">
              {/* Welcome Message */}
              <div className="text-center mb-8">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-rose-100 text-rose-600 mb-4">
                  <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <h2 className="text-2xl font-bold text-gray-900 mb-2">
                  What would you like to know?
                </h2>
                <p className="text-gray-600 max-w-lg mx-auto">
                  Ask questions about diagnoses, prescriptions, student trends,
                  or any insights from your extractions.
                </p>
              </div>

              {/* Suggested Questions */}
              <QASuggestedQuestions
                questions={suggestedQuestions}
                onQuestionClick={handleSuggestedClick}
                selectedCategory={selectedCategory}
                onCategoryChange={handleCategoryChange}
              />
            </div>
          ) : (
            <div className="max-w-4xl mx-auto space-y-6">
              {messages.map((message) => (
                <QAChatMessage
                  key={message.id}
                  message={message}
                  renderContent={() => {
                    if (message.role === 'user') {
                      return <p className="text-gray-900">{message.content}</p>;
                    }

                    if (message.isLoading) {
                      return (
                        <div className="flex items-center gap-2 text-gray-500">
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-rose-600"></div>
                          <span>Thinking...</span>
                        </div>
                      );
                    }

                    const response = message.response;
                    if (!response) {
                      return <p className="text-gray-700">{message.content}</p>;
                    }

                    return (
                      <div className="space-y-4">
                        {/* Narrative Response */}
                        {response.narrative && (
                          <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-line">
                            {response.narrative}
                          </div>
                        )}

                        {/* Chart Response */}
                        {response.chart && (
                          <QAChart data={response.chart} />
                        )}

                        {/* Stat Card Response */}
                        {response.stat_card && (
                          <div className="bg-gradient-to-br from-rose-50 to-rose-100 rounded-xl p-6 border border-rose-200">
                            <p className="text-sm text-rose-600 font-medium">{response.stat_card.title}</p>
                            <p className="text-4xl font-bold text-rose-700 mt-2">{response.stat_card.value}</p>
                            {response.stat_card.subtitle && (
                              <p className="text-sm text-rose-500 mt-1">{response.stat_card.subtitle}</p>
                            )}
                            {response.stat_card.change_percent !== undefined && (
                              <p className={`text-sm mt-2 ${
                                response.stat_card.trend === 'up' ? 'text-green-600' :
                                response.stat_card.trend === 'down' ? 'text-red-600' :
                                'text-gray-600'
                              }`}>
                                {response.stat_card.trend === 'up' ? '↑' : response.stat_card.trend === 'down' ? '↓' : ''}
                                {' '}{response.stat_card.change_percent}% from previous period
                              </p>
                            )}
                          </div>
                        )}

                        {/* Table Response */}
                        {response.results && response.results.length > 0 && (
                          <QAResultsTable
                            results={response.results}
                            totalCount={response.total_count || response.results.length}
                            referencedIds={response.referenced_extraction_ids}
                          />
                        )}

                        {/* Temporal References - Show resolved time context */}
                        {response.temporal_references && response.temporal_references.length > 0 && (
                          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm">
                            <div className="flex items-start gap-2">
                              <span className="text-blue-600 flex-shrink-0">📅</span>
                              <div className="flex-1">
                                <p className="text-blue-800 font-medium mb-1">Temporal context:</p>
                                <div className="flex flex-wrap gap-2">
                                  {response.temporal_references.map((ref, idx) => (
                                    <span
                                      key={idx}
                                      className="inline-flex items-center px-2 py-1 rounded text-xs bg-blue-100 text-blue-700"
                                    >
                                      <span className="font-medium">&quot;{ref.raw_text}&quot;</span>
                                      {ref.resolved_date && (
                                        <>
                                          <span className="mx-1">→</span>
                                          <span>{formatTemporalDate(ref.resolved_date)}</span>
                                        </>
                                      )}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Longitudinal Data Summary - Show comparison info */}
                        {response.longitudinal_data && !response.longitudinal_data.error && (
                          <div className="mt-3 p-3 bg-purple-50 border border-purple-200 rounded-lg text-sm">
                            <div className="flex items-start gap-2">
                              <span className="text-purple-600 flex-shrink-0">📊</span>
                              <div className="flex-1">
                                <p className="text-purple-800 font-medium mb-2">Comparison Summary:</p>
                                <div className="grid grid-cols-2 gap-4 text-xs">
                                  {response.longitudinal_data.time_span_days !== undefined && (
                                    <div className="bg-purple-100 p-2 rounded">
                                      <span className="text-purple-600">Time span:</span>
                                      <span className="ml-1 font-medium text-purple-800">
                                        {response.longitudinal_data.time_span_days} days
                                      </span>
                                    </div>
                                  )}
                                  {response.longitudinal_data.medication_changes && (
                                    <div className="bg-purple-100 p-2 rounded">
                                      <span className="text-purple-600">Medication changes:</span>
                                      <span className="ml-1 font-medium text-purple-800">
                                        +{response.longitudinal_data.medication_changes.added?.length || 0} /
                                        -{response.longitudinal_data.medication_changes.removed?.length || 0}
                                      </span>
                                    </div>
                                  )}
                                  {response.longitudinal_data.new_diagnoses && response.longitudinal_data.new_diagnoses.length > 0 && (
                                    <div className="bg-purple-100 p-2 rounded col-span-2">
                                      <span className="text-purple-600">New diagnoses:</span>
                                      <span className="ml-1 font-medium text-purple-800">
                                        {response.longitudinal_data.new_diagnoses.join(', ')}
                                      </span>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Reframing Info - Show if query was transformed */}
                        {response.reframed_query && (
                          <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm">
                            <div className="flex items-start gap-2">
                              <span className="text-amber-600 flex-shrink-0">✨</span>
                              <div className="flex-1">
                                <p className="text-amber-800 font-medium mb-1">Query enhanced:</p>
                                <p className="text-amber-700 italic">&quot;{response.reframed_query}&quot;</p>
                                {/* Show expansions */}
                                {response.reframe_expansions && response.reframe_expansions.length > 0 && (
                                  <div className="mt-2 flex flex-wrap gap-1">
                                    {response.reframe_expansions.map((exp, idx) => (
                                      <span
                                        key={idx}
                                        className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-700"
                                      >
                                        <span className="font-mono">{exp.original}</span>
                                        <span className="mx-1">→</span>
                                        <span>{exp.expanded}</span>
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {/* Show corrections */}
                                {response.reframe_corrections && response.reframe_corrections.length > 0 && (
                                  <div className="mt-2 flex flex-wrap gap-1">
                                    {response.reframe_corrections.map((corr, idx) => (
                                      <span
                                        key={idx}
                                        className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-red-100 text-red-700"
                                      >
                                        <span className="font-mono line-through">{corr.original}</span>
                                        <span className="mx-1">→</span>
                                        <span>{corr.corrected}</span>
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Timing Info */}
                        {response.total_time_ms && (
                          <p className="text-xs text-gray-400 mt-2">
                            Response time: {response.total_time_ms}ms
                            {response.reframe_time_ms && ` (reframe: ${response.reframe_time_ms}ms)`}
                            {response.embedding_time_ms && ` (embed: ${response.embedding_time_ms}ms)`}
                            {response.search_time_ms && ` (search: ${response.search_time_ms}ms)`}
                            {response.synthesis_time_ms && ` (synthesis: ${response.synthesis_time_ms}ms)`}
                          </p>
                        )}
                      </div>
                    );
                  }}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Error Banner */}
        {error && (
          <div className="px-6 py-2">
            <div className="max-w-4xl mx-auto">
              <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm text-red-700 flex items-center justify-between">
                <span>{error}</span>
                <button
                  onClick={() => setError(null)}
                  className="text-red-500 hover:text-red-700"
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Collapsed Suggestions (when chat has messages) */}
        {messages.length > 0 && !showSuggestions && (
          <div className="px-6 py-2 border-t border-gray-200 bg-white">
            <div className="max-w-4xl mx-auto">
              <button
                onClick={() => setShowSuggestions(true)}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Show suggested questions
              </button>
              {showSuggestions && (
                <div className="mt-2">
                  <QASuggestedQuestions
                    questions={suggestedQuestions.slice(0, 6)}
                    onQuestionClick={handleSuggestedClick}
                    selectedCategory={selectedCategory}
                    onCategoryChange={handleCategoryChange}
                    compact
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="border-t border-gray-200 bg-white px-6 py-4">
          <div className="max-w-4xl mx-auto">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSubmit(inputValue);
              }}
              className="flex items-center gap-3"
            >
              <div className="flex-1 relative">
                <input
                  ref={inputRef}
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Ask a question about your data..."
                  className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-transparent text-gray-900"
                  disabled={isLoading}
                />
              </div>
              <button
                type="submit"
                disabled={!inputValue.trim() || isLoading}
                className="px-6 py-3 bg-rose-600 text-white font-medium rounded-xl hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {isLoading ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Processing
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                    </svg>
                    Send
                  </>
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatResponseContent(response: QAQueryResponse): string {
  if (response.error_message) {
    return `Error: ${response.error_message}`;
  }

  if (response.narrative) {
    return response.narrative;
  }

  if (response.results && response.results.length > 0) {
    return `Found ${response.total_count || response.results.length} matching records.`;
  }

  if (response.stat_card) {
    return `${response.stat_card.title}: ${response.stat_card.value}`;
  }

  return 'No results found.';
}

function formatVisitDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return dateString;
  }
}

function formatTemporalDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  } catch {
    return dateString;
  }
}
