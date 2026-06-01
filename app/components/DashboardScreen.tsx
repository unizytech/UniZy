'use client';

/**
 * Dashboard Screen - School Management Dashboard
 *
 * Main dashboard for tracking intervention opportunities and student retention.
 * Three views:
 * 1. Command Center - Overview metrics and category breakdown
 * 2. Student Info - Student list with interventions
 * 3. Tracking - Intervention status management
 *
 * Based on 6-category dashboard system (remapped from 7 DB categories):
 * - TREATMENT_COMPLIANCE: Treatment adherence (score-based)
 * - DROP_OFF_RISK: Student retention risk (score-based)
 * - FOLLOWUP_DUE: Actionable follow-up needs (intervention-based)
 * - HEALTH_SERVICES: Rx + diagnostics + allied health (intervention-based)
 * - SURGERY_CANDIDATE: OPD to IPD conversion (intervention-based)
 * - QUALITY_RISK: Clinical quality/safety (intervention-based)
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@lib/auth';
import {
  getInterventionSummary,
  getStudentsByCategory,
  getOutcomeMetrics,
  updateInterventionStatus,
  getSchools,
  getCounsellors,
  getSpecializations,
  getStudentLastVisitInfo,
  formatCurrency,
  formatPercentage,
  getPriorityColor,
  getStatusColor,
  getDaysOverdueText,
  CATEGORY_CONFIG,
  InterventionSummaryResponse,
  StudentsListResponse,
  OutcomeMetricsResponse,
  CategoryStats,
  BreakdownStats,
  StudentWithInterventions,
  StudentMetricRow,
  TimePeriod,
  InterventionCategory,
  School,
  Counsellor,
} from '@lib/dashboardApi';

// ============================================================================
// Types
// ============================================================================

type DashboardView = 'command-center' | 'patient-info' | 'tracking';

interface FilterState {
  period: TimePeriod;
  hospitalId?: string;
  departmentId?: string;
  doctorId?: string;
  selectedCategory?: InterventionCategory;
}

// ============================================================================
// Time Period Tabs
// ============================================================================

const TIME_PERIODS: { value: TimePeriod; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'This Week' },
  { value: 'mtd', label: 'Month to Date' },
  { value: 'ytd', label: 'Last 30 Days' },
];

// ============================================================================
// Main Dashboard Component
// ============================================================================

export default function DashboardScreen() {
  const { getAccessToken, isSchoolAdmin, adminSchoolId } = useAuth();
  const accessToken = getAccessToken();

  // State
  const [activeView, setActiveView] = useState<DashboardView>('command-center');
  const [filters, setFilters] = useState<FilterState>({ period: 'mtd' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter options state
  const [hospitals, setSchools] = useState<School[]>([]);
  const [counsellors, setCounsellorsData] = useState<Counsellor[]>([]);
  const [specializations, setSpecializations] = useState<string[]>([]);
  const [hospitalsLoading, setSchoolsLoading] = useState(true);

  // Breakdown view state (for department/counsellor/student table toggle)
  const [breakdownView, setBreakdownView] = useState<'department' | 'doctor' | 'patient'>('department');

  // Data state
  const [summary, setSummary] = useState<InterventionSummaryResponse | null>(null);
  const [students, setStudents] = useState<StudentsListResponse | null>(null);
  const [outcomes, setOutcomes] = useState<OutcomeMetricsResponse | null>(null);

  // Fetch data
  const fetchData = useCallback(async () => {
    if (!accessToken) return;

    setLoading(true);
    setError(null);

    try {
      const [summaryData, outcomesData] = await Promise.all([
        getInterventionSummary(
          {
            period: filters.period,
            hospitalId: filters.hospitalId,
            departmentId: filters.departmentId,
            doctorId: filters.doctorId,
          },
          accessToken
        ),
        getOutcomeMetrics(
          {
            period: filters.period,
            hospitalId: filters.hospitalId,
            departmentId: filters.departmentId,
            doctorId: filters.doctorId,
          },
          accessToken
        ),
      ]);

      setSummary(summaryData);
      setOutcomes(outcomesData);

      // Always fetch students (with or without category filter)
      const patientsData = await getStudentsByCategory(
        filters.selectedCategory, // undefined = all categories
        {
          hospitalId: filters.hospitalId,
          departmentId: filters.departmentId,
          doctorId: filters.doctorId,
          period: filters.period,
        },
        accessToken
      );
      setStudents(patientsData);
    } catch (err) {
      console.error('Dashboard fetch error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, [accessToken, filters]);

  // Only fetch dashboard data after schools are loaded and a school is selected
  useEffect(() => {
    // Wait for schools to load and be selected before fetching dashboard
    if (!hospitalsLoading && filters.hospitalId) {
      fetchData();
    }
  }, [fetchData, hospitalsLoading, filters.hospitalId]);

  // Fetch schools on mount and set default
  useEffect(() => {
    async function loadSchools() {
      if (!accessToken) return;

      setSchoolsLoading(true);
      try {
        if (isSchoolAdmin && adminSchoolId) {
          // School admin: set their school directly, fetch only their school name
          setFilters((prev) => ({ ...prev, hospitalId: adminSchoolId }));
          const hospitalList = await getSchools(accessToken);
          const mySchool = hospitalList.find((h) => h.id === adminSchoolId);
          if (mySchool) {
            setSchools([mySchool]);
          }
        } else {
          // Super admin: load all schools, default to "Guru School"
          const hospitalList = await getSchools(accessToken);
          setSchools(hospitalList);

          const guruSchool = hospitalList.find(
            (h) => h.school_name.toLowerCase().includes('guru') ||
                   h.school_code.toLowerCase().includes('guru')
          );

          if (guruSchool) {
            setFilters((prev) => ({ ...prev, hospitalId: guruSchool.id }));
          } else if (hospitalList.length > 0) {
            setFilters((prev) => ({ ...prev, hospitalId: hospitalList[0].id }));
          }
        }
      } catch (err) {
        console.error('Error loading schools:', err);
      } finally {
        setSchoolsLoading(false);
      }
    }

    loadSchools();
  }, [accessToken, isSchoolAdmin, adminSchoolId]);

  // Fetch counsellors and specializations when school changes
  useEffect(() => {
    async function loadCounsellorsAndSpecializations() {
      if (!accessToken || !filters.hospitalId) return;

      try {
        const [doctorList, specList] = await Promise.all([
          getCounsellors({ hospitalId: filters.hospitalId }, accessToken),
          getSpecializations(accessToken),
        ]);

        setCounsellorsData(doctorList);

        // Filter specializations to those used by counsellors in this school
        const hospitalSpecializations = new Set(
          doctorList.map((d) => d.specialization).filter(Boolean)
        );
        const filteredSpecs = specList.filter((s) => hospitalSpecializations.has(s));
        setSpecializations(filteredSpecs.length > 0 ? filteredSpecs : specList);
      } catch (err) {
        console.error('Error loading counsellors/specializations:', err);
      }
    }

    loadCounsellorsAndSpecializations();
  }, [accessToken, filters.hospitalId]);

  // Handle category click
  const handleCategoryClick = async (category: InterventionCategory | string) => {
    // If empty string or invalid, clear category filter
    if (!category) {
      setFilters((prev) => ({ ...prev, selectedCategory: undefined }));
      setStudents(null);
      return;
    }

    setFilters((prev) => ({ ...prev, selectedCategory: category as InterventionCategory }));
    setActiveView('patient-info');

    if (accessToken) {
      try {
        const patientsData = await getStudentsByCategory(
          category ? (category as InterventionCategory) : undefined,
          {
            hospitalId: filters.hospitalId,
            departmentId: filters.departmentId,
            doctorId: filters.doctorId,
            period: filters.period,
          },
          accessToken
        );
        setStudents(patientsData);
      } catch (err) {
        console.error('Error fetching students:', err);
      }
    }
  };

  // Handle status update
  const handleStatusUpdate = async (interventionId: string, newStatus: string) => {
    if (!accessToken) return;

    try {
      await updateInterventionStatus(
        interventionId,
        { status: newStatus as any },
        accessToken
      );
      // Refresh data
      fetchData();
    } catch (err) {
      console.error('Error updating status:', err);
    }
  };

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {activeView === 'command-center' && 'Command Center'}
              {activeView === 'patient-info' && 'Student Info'}
              {activeView === 'tracking' && 'Tracking'}
            </h1>
            <p className="text-sm text-gray-500">
              {activeView === 'command-center' && 'School intelligence overview'}
              {activeView === 'patient-info' && 'At-risk students'}
              {activeView === 'tracking' && 'Intervention management'}
            </p>
          </div>
          <div className="flex items-center gap-4">
            {/* School Selector */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">🏥</span>
              {isSchoolAdmin ? (
                <span className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 font-medium text-gray-900 min-w-48">
                  {hospitals[0]?.school_name || 'Loading...'}
                </span>
              ) : (
                <select
                  value={filters.hospitalId || ''}
                  onChange={(e) => setFilters((prev) => ({
                    ...prev,
                    hospitalId: e.target.value || undefined,
                    departmentId: undefined,
                    doctorId: undefined,
                  }))}
                  className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white font-medium text-gray-900 min-w-48"
                  disabled={hospitalsLoading}
                >
                  {hospitalsLoading ? (
                    <option>Loading schools...</option>
                  ) : hospitals.length === 0 ? (
                    <option value="">No schools found</option>
                  ) : (
                    hospitals.map((hospital) => (
                      <option key={hospital.id} value={hospital.id}>
                        {hospital.school_name}
                      </option>
                    ))
                  )}
                </select>
              )}
            </div>
            {/* Department Selector */}
            <div className="flex items-center gap-2">
              <select
                value={filters.departmentId || ''}
                onChange={(e) => setFilters((prev) => ({
                  ...prev,
                  departmentId: e.target.value || undefined,
                  doctorId: undefined,
                }))}
                className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white text-gray-700"
              >
                <option value="">All Departments</option>
                {specializations.map((spec) => (
                  <option key={spec} value={spec}>
                    {spec}
                  </option>
                ))}
              </select>
            </div>
            {/* Counsellor Selector */}
            <div className="flex items-center gap-2">
              <select
                value={filters.doctorId || ''}
                onChange={(e) => setFilters((prev) => ({
                  ...prev,
                  doctorId: e.target.value || undefined,
                }))}
                className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white text-gray-700"
              >
                <option value="">All Counsellors</option>
                {counsellors
                  .filter((d) => !filters.departmentId || d.specialization === filters.departmentId)
                  .map((doctor) => (
                    <option key={doctor.id} value={doctor.id}>
                      {doctor.counsellor_name}
                    </option>
                  ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="bg-white border-b border-gray-200 px-6">
        <nav className="flex gap-6">
          {[
            { key: 'command-center', label: 'Command Center', icon: '📊' },
            { key: 'patient-info', label: 'Student Info', icon: '👥' },
            { key: 'tracking', label: 'Tracking', icon: '📋' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveView(tab.key as DashboardView)}
              className={`flex items-center gap-2 py-4 border-b-2 text-sm font-medium transition-colors ${
                activeView === tab.key
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <span>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Time Period Filter */}
      <div className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 mr-2">📅 Time Period:</span>
          {TIME_PERIODS.map((period) => (
            <button
              key={period.value}
              onClick={() => setFilters((prev) => ({ ...prev, period: period.value }))}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                filters.period === period.value
                  ? 'bg-gray-900 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {period.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto p-6 relative">
        {/* Loading overlay - show on top of existing content for better UX */}
        {loading && summary && (
          <div className="absolute inset-0 bg-white/60 z-10 flex items-center justify-center">
            <div className="flex items-center gap-2 bg-white px-4 py-2 rounded-lg shadow-lg">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
              <span className="text-sm text-gray-600">Updating...</span>
            </div>
          </div>
        )}
        {/* Initial loading - no data yet */}
        {loading && !summary ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : error ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        ) : (
          <>
            {activeView === 'command-center' && (
              <CommandCenterView
                summary={summary}
                outcomes={outcomes}
                onCategoryClick={handleCategoryClick}
                breakdownView={breakdownView}
                setBreakdownView={setBreakdownView}
                accessToken={accessToken}
              />
            )}
            {activeView === 'patient-info' && (
              <StudentInfoView
                students={students}
                selectedCategory={filters.selectedCategory}
                onStatusUpdate={handleStatusUpdate}
                onCategoryChange={(cat) =>
                  handleCategoryClick(cat as InterventionCategory)
                }
              />
            )}
            {activeView === 'tracking' && (
              <TrackingView
                summary={summary}
                outcomes={outcomes}
                students={students}
                onCategoryClick={handleCategoryClick}
                filters={{
                  hospitalId: filters.hospitalId,
                  departmentId: filters.departmentId,
                  doctorId: filters.doctorId,
                  period: filters.period,
                }}
                accessToken={accessToken}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Command Center View
// ============================================================================

function CommandCenterView({
  summary,
  outcomes,
  onCategoryClick,
  breakdownView,
  setBreakdownView,
  accessToken,
}: {
  summary: InterventionSummaryResponse | null;
  outcomes: OutcomeMetricsResponse | null;
  onCategoryClick: (category: InterventionCategory) => void;
  breakdownView: 'department' | 'doctor' | 'patient';
  setBreakdownView: (view: 'department' | 'doctor' | 'patient') => void;
  accessToken: string | null;
}) {
  if (!summary) return null;

  const totalVisited = summary.total_students || 0;
  const atRisk = summary.patients_with_interventions || 0;
  const atRiskPercent = totalVisited > 0 ? ((atRisk / totalVisited) * 100).toFixed(1) : '0';

  return (
    <div className="space-y-6">
      {/* Hero Stats Card */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-indigo-200 text-sm font-medium">Total Students at Risk</p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-5xl font-bold">{atRisk.toLocaleString()}</span>
              <span className="text-xl text-indigo-200">/ {totalVisited.toLocaleString()} visited</span>
              <span className="ml-2 px-3 py-1 bg-white/20 rounded-full text-sm font-medium">
                {atRiskPercent}% at risk
              </span>
            </div>
            <p className="text-indigo-200 text-sm mt-2">Across all leakage types</p>
          </div>
          <div className="flex items-center gap-8">
            <div className="text-right">
              <p className="text-4xl font-bold text-green-300">
                {outcomes ? formatPercentage(outcomes.conversion_rate) : '0%'}
              </p>
              <p className="text-sm text-indigo-200">Intervention Rate</p>
            </div>
            <div className="text-right">
              <p className="text-4xl font-bold text-yellow-300">
                {formatCurrency(summary.revenue_potential)}
              </p>
              <p className="text-sm text-indigo-200">Revenue Potential</p>
            </div>
          </div>
        </div>
      </div>

      {/* Category Cards - 6 Dashboard Metrics */}
      <div className="grid grid-cols-6 gap-3">
        {summary.by_category?.map((category) => (
          <CategoryCard
            key={category.category}
            category={category}
            onClick={() => onCategoryClick(category.category as InterventionCategory)}
          />
        ))}
      </div>

      {/* Breakdown Section */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setBreakdownView('department')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                breakdownView === 'department'
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-500 hover:bg-gray-50'
              }`}
            >
              🏢 By Department
            </button>
            <button
              onClick={() => setBreakdownView('doctor')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                breakdownView === 'doctor'
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-500 hover:bg-gray-50'
              }`}
            >
              👨‍⚕️ By Counsellor
            </button>
            <button
              onClick={() => setBreakdownView('patient')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                breakdownView === 'patient'
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-500 hover:bg-gray-50'
              }`}
            >
              👤 By Student
            </button>
          </div>
          {breakdownView !== 'patient' && (
            <input
              type="text"
              placeholder={`Search ${breakdownView === 'department' ? 'departments' : 'counsellors'}...`}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm w-64"
            />
          )}
        </div>

        {breakdownView === 'patient' ? (
          <ByStudentTable students={summary.by_patient || []} accessToken={accessToken} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    {breakdownView === 'department' ? 'Department' : 'Counsellor'}
                  </th>
                  {summary.by_category?.map((cat) => (
                    <th
                      key={cat.category}
                      className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      <span className="flex items-center justify-center gap-1">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            CATEGORY_CONFIG[cat.category as InterventionCategory]?.bgColor?.replace('bg-', 'bg-') ||
                            'bg-gray-400'
                          }`}
                        ></span>
                        {CATEGORY_CONFIG[cat.category as InterventionCategory]?.icon || '📊'}
                      </span>
                    </th>
                  ))}
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Total At-Risk
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {breakdownView === 'department' ? (
                  <>
                    {(summary.by_department?.length || 0) > 0 ? (
                      summary.by_department.map((dept) => (
                        <tr key={dept.id} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                            {dept.name}
                          </td>
                          {summary.by_category?.map((cat) => (
                            <td key={cat.category} className="px-4 py-4 whitespace-nowrap text-center">
                              <span className={`text-sm font-medium ${
                                (dept.by_category?.[cat.category] || 0) > 0 ? 'text-gray-900' : 'text-gray-400'
                              }`}>
                                {dept.by_category?.[cat.category] || 0}
                              </span>
                            </td>
                          ))}
                          <td className="px-6 py-4 whitespace-nowrap text-center text-sm font-bold text-gray-900">
                            {dept.total_at_risk}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr className="hover:bg-gray-50">
                        <td colSpan={(summary.by_category?.length || 0) + 2} className="px-6 py-8 text-center text-sm text-gray-500">
                          No department data available for this period
                        </td>
                      </tr>
                    )}
                  </>
                ) : (
                  <>
                    {(summary.by_doctor?.length || 0) > 0 ? (
                      summary.by_doctor.map((doctor) => (
                        <tr key={doctor.id} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="flex items-center">
                              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-medium text-sm mr-3">
                                {doctor.name?.charAt(0) || '?'}
                              </div>
                              <div>
                                <div className="text-sm font-medium text-gray-900">{doctor.name || 'Unknown'}</div>
                                <div className="text-xs text-gray-500">{doctor.specialization || 'General'}</div>
                              </div>
                            </div>
                          </td>
                          {summary.by_category?.map((cat) => (
                            <td key={cat.category} className="px-4 py-4 whitespace-nowrap text-center">
                              <span className={`text-sm font-medium ${
                                (doctor.by_category?.[cat.category] || 0) > 0 ? 'text-gray-900' : 'text-gray-400'
                              }`}>
                                {doctor.by_category?.[cat.category] || 0}
                              </span>
                            </td>
                          ))}
                          <td className="px-6 py-4 whitespace-nowrap text-center text-sm font-bold text-gray-900">
                            {doctor.total_at_risk}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr className="hover:bg-gray-50">
                        <td colSpan={(summary.by_category?.length || 0) + 2} className="px-6 py-8 text-center text-sm text-gray-500">
                          No counsellor data available for this period
                        </td>
                      </tr>
                    )}
                  </>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Category Card Component
// ============================================================================

function CategoryCard({
  category,
  onClick,
}: {
  category: CategoryStats;
  onClick: () => void;
}) {
  const config = CATEGORY_CONFIG[category.category as InterventionCategory] || {
    label: category.label,
    icon: '📊',
    color: 'gray',
    bgColor: 'bg-gray-50',
    textColor: 'text-gray-700',
    borderColor: 'border-gray-200',
    cardType: 'intervention' as const,
  };

  const isScoreCard = config.cardType === 'score';

  // Icon background color
  const iconBgColor =
    config.color === 'purple' ? 'bg-purple-500'
    : config.color === 'blue' ? 'bg-blue-500'
    : config.color === 'teal' ? 'bg-teal-500'
    : config.color === 'amber' ? 'bg-amber-500'
    : config.color === 'red' ? 'bg-red-500'
    : config.color === 'cyan' ? 'bg-cyan-500'
    : 'bg-gray-500';

  if (isScoreCard) {
    // Score-based card (Treatment Compliance, Drop-off Risk)
    const isCompliance = category.category === 'TREATMENT_COMPLIANCE';
    const scoreValue = isCompliance
      ? category.avg_compliance_score
      : category.avg_dropoff_probability;
    const scoreLabel = isCompliance ? 'avg compliance' : 'avg drop-off';
    const hasScore = scoreValue !== null && scoreValue !== undefined;

    // Color the score text based on value
    const getScoreColor = () => {
      if (!hasScore) return 'text-gray-400';
      if (isCompliance) {
        // Higher compliance = better (green)
        if (scoreValue >= 65) return 'text-green-600';
        if (scoreValue >= 35) return 'text-amber-600';
        return 'text-red-600';
      } else {
        // Higher dropoff = worse (red)
        if (scoreValue >= 60) return 'text-red-600';
        if (scoreValue >= 40) return 'text-amber-600';
        return 'text-green-600';
      }
    };

    return (
      <button
        onClick={onClick}
        className={`${config.bgColor} ${config.borderColor} border rounded-xl p-3 text-left hover:shadow-md transition-shadow w-full`}
      >
        <div className="flex items-start justify-between mb-2">
          <div className={`w-8 h-8 rounded-lg ${iconBgColor} flex items-center justify-center text-white text-sm`}>
            {config.icon}
          </div>
          <span className={`px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded text-xs font-medium`}>
            Score
          </span>
        </div>
        <p className={`text-xs font-medium ${config.textColor} truncate`}>{config.label}</p>
        <div className="flex items-baseline gap-1 mt-1">
          <span className="text-2xl font-bold text-gray-900">
            {category.student_count}
          </span>
          <span className="text-xs text-gray-500">students</span>
        </div>
        {hasScore && (
          <p className={`text-sm font-semibold mt-1 ${getScoreColor()}`}>
            {scoreValue.toFixed(0)}% {scoreLabel}
          </p>
        )}
        <p className="text-xs text-gray-400 mt-1 hover:text-blue-600">
          View →
        </p>
      </button>
    );
  }

  // Intervention-based card (Health Services, Surgery Candidate, Quality & Safety)
  const riskScore = category.aggregate_risk_score || 0;
  const riskBand = category.risk_band || 'LOW';

  const riskBandColors = {
    HIGH: { bg: 'bg-red-100', text: 'text-red-700' },
    MEDIUM: { bg: 'bg-amber-100', text: 'text-amber-700' },
    LOW: { bg: 'bg-green-100', text: 'text-green-700' },
  };
  const riskColors = riskBandColors[riskBand as keyof typeof riskBandColors] || riskBandColors.LOW;

  return (
    <button
      onClick={onClick}
      className={`${config.bgColor} ${config.borderColor} border rounded-xl p-3 text-left hover:shadow-md transition-shadow w-full`}
    >
      <div className="flex items-start justify-between mb-2">
        <div className={`w-8 h-8 rounded-lg ${iconBgColor} flex items-center justify-center text-white text-sm`}>
          {config.icon}
        </div>
        <span className={`px-2 py-0.5 ${riskColors.bg} ${riskColors.text} rounded text-xs font-medium`}>
          {riskScore.toFixed(0)}% risk
        </span>
      </div>
      <p className={`text-xs font-medium ${config.textColor} truncate`}>{config.label}</p>
      <div className="flex items-baseline gap-1 mt-1">
        <span className="text-2xl font-bold text-gray-900">
          {category.student_count}
        </span>
        <span className="text-xs text-gray-500">students</span>
      </div>
      {category.revenue_potential > 0 && (
        <p className="text-xs text-green-600 font-medium mt-1">
          {formatCurrency(category.revenue_potential)}
        </p>
      )}
      <p className="text-xs text-gray-400 mt-1 hover:text-blue-600">
        View →
      </p>
    </button>
  );
}

// ============================================================================
// By Student Table Component
// ============================================================================

function ByStudentTable({ students, accessToken }: { students: StudentMetricRow[]; accessToken: string | null }) {
  const [sortField, setSortField] = useState<string>('dropoff_probability');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  // Nudge Engine modal state
  const [nudgeStudentId, setNudgeStudentId] = useState<string | null>(null);

  // Student info modal state
  const [selectedStudentForInfo, setSelectedStudentForInfo] = useState<string | null>(null);
  const [patientInfoData, setStudentInfoData] = useState<{
    found: boolean;
    diagnosis: any;
    counsellor_name: string | null;
    visit_date: string | null;
    preferred_language: string | null;
  } | null>(null);
  const [patientInfoLoading, setStudentInfoLoading] = useState(false);

  const handleShowStudentInfo = async (patientId: string) => {
    setSelectedStudentForInfo(patientId);
    setStudentInfoData(null);
    setStudentInfoLoading(true);
    try {
      const data = await getStudentLastVisitInfo(patientId, accessToken);
      setStudentInfoData(data);
    } catch {
      setStudentInfoData({ found: false, diagnosis: null, counsellor_name: null, visit_date: null, preferred_language: null });
    } finally {
      setStudentInfoLoading(false);
    }
  };

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const sorted = [...students].sort((a, b) => {
    let aVal: any, bVal: any;
    switch (sortField) {
      case 'patient_name':
        aVal = a.patient_name; bVal = b.patient_name;
        return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      case 'compliance_likelihood':
        const compOrder: Record<string, number> = { 'Very Low': 0, 'Low': 1, 'Moderate': 2, 'High': 3 };
        aVal = compOrder[a.compliance_likelihood || ''] ?? -1;
        bVal = compOrder[b.compliance_likelihood || ''] ?? -1;
        break;
      case 'dropoff_probability':
        aVal = a.dropoff_probability ?? -1; bVal = b.dropoff_probability ?? -1;
        break;
      case 'is_surgery_candidate':
        aVal = a.is_surgery_candidate ? 1 : 0; bVal = b.is_surgery_candidate ? 1 : 0;
        break;
      case 'health_service_count':
        aVal = a.health_service_count; bVal = b.health_service_count;
        break;
      case 'has_followup_due':
        aVal = a.has_followup_due ? 1 : 0; bVal = b.has_followup_due ? 1 : 0;
        break;
      default:
        aVal = 0; bVal = 0;
    }
    return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
  });

  const paginated = sorted.slice(page * pageSize, (page + 1) * pageSize);
  const totalPages = Math.ceil(sorted.length / pageSize);

  const getComplianceColor = (likelihood: string | null) => {
    switch (likelihood) {
      case 'High': return 'bg-green-100 text-green-700';
      case 'Moderate': return 'bg-amber-100 text-amber-700';
      case 'Low': return 'bg-orange-100 text-orange-700';
      case 'Very Low': return 'bg-red-100 text-red-700';
      default: return 'bg-gray-100 text-gray-500';
    }
  };

  const getDropoffColor = (prob: number | null) => {
    if (prob === null) return 'text-gray-400';
    if (prob >= 60) return 'text-red-600 font-semibold';
    if (prob >= 40) return 'text-amber-600 font-medium';
    return 'text-green-600';
  };

  const getHealthLevelColor = (level: string) => {
    switch (level) {
      case 'High': return 'bg-red-100 text-red-700';
      case 'Medium': return 'bg-amber-100 text-amber-700';
      case 'Low': return 'bg-gray-100 text-gray-500';
      default: return 'bg-gray-100 text-gray-500';
    }
  };

  const SortHeader = ({ field, label }: { field: string; label: string }) => (
    <th
      className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
      onClick={() => handleSort(field)}
    >
      <span className="flex items-center gap-1">
        {label}
        {sortField === field && (
          <span className="text-blue-500">{sortDir === 'asc' ? '↑' : '↓'}</span>
        )}
      </span>
    </th>
  );

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <SortHeader field="patient_name" label="Student" />
              <SortHeader field="compliance_likelihood" label="Treatment Compliance" />
              <SortHeader field="dropoff_probability" label="Drop-off Risk" />
              <SortHeader field="has_followup_due" label="Follow-up Due" />
              <SortHeader field="is_surgery_candidate" label="Surgery" />
              <SortHeader field="health_service_count" label="Health Service Needs" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {paginated.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-gray-500">
                  No student data available for this period
                </td>
              </tr>
            ) : (
              paginated.map((patient) => (
                <tr key={patient.student_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="flex items-center gap-1">
                      <div>
                        <p
                          className="text-sm font-medium text-blue-600 hover:text-blue-800 cursor-pointer hover:underline"
                          onClick={() => setNudgeStudentId(patient.student_id)}
                          title="Open Nudge Engine"
                        >
                          {patient.patient_name}
                        </p>
                        {patient.mrn && (
                          <p className="text-xs text-gray-500">MRN: {patient.mrn}</p>
                        )}
                      </div>
                      <button
                        onClick={() => handleShowStudentInfo(patient.student_id)}
                        className="ml-1 text-gray-400 hover:text-blue-500 transition-colors"
                        title="View student info"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </button>
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${getComplianceColor(patient.compliance_likelihood)}`}>
                      {patient.compliance_likelihood || 'N/A'}
                    </span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className={`text-sm ${getDropoffColor(patient.dropoff_probability)}`}>
                      {patient.dropoff_probability !== null
                        ? `${patient.dropoff_probability.toFixed(0)}%`
                        : 'N/A'}
                    </span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-center">
                    {patient.has_followup_due ? (
                      <span className="px-2.5 py-1 bg-cyan-100 text-cyan-700 rounded-full text-xs font-medium">
                        Yes{patient.followup_count > 1 && ` (${patient.followup_count})`}
                      </span>
                    ) : (
                      <span className="px-2.5 py-1 bg-gray-100 text-gray-400 rounded-full text-xs font-medium">
                        No
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-center">
                    {patient.is_surgery_candidate ? (
                      <span className="px-2.5 py-1 bg-purple-100 text-purple-700 rounded-full text-xs font-medium">
                        Yes
                      </span>
                    ) : (
                      <span className="px-2.5 py-1 bg-gray-100 text-gray-400 rounded-full text-xs font-medium">
                        No
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${getHealthLevelColor(patient.health_service_level)}`}>
                      {patient.health_service_level}
                      {patient.health_service_count > 0 && (
                        <span className="ml-1 text-gray-500">({patient.health_service_count})</span>
                      )}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="px-6 py-3 border-t border-gray-200 flex items-center justify-between">
          <span className="text-sm text-gray-500">
            Showing {page * pageSize + 1}-{Math.min((page + 1) * pageSize, sorted.length)} of {sorted.length} students
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm disabled:opacity-50 hover:bg-gray-50"
            >
              Previous
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm disabled:opacity-50 hover:bg-gray-50"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Nudge Engine Modal */}
      {nudgeStudentId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setNudgeStudentId(null)}
        >
          <div
            className="bg-white rounded-xl shadow-xl w-full max-w-4xl mx-4 overflow-hidden"
            style={{ height: '80vh' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">Nudge Engine</h3>
              <button
                onClick={() => setNudgeStudentId(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
            <iframe
              src={`https://nudgeengine.up.railway.app/link/${nudgeStudentId}`}
              className="w-full border-0"
              style={{ height: 'calc(80vh - 57px)' }}
              title="Nudge Engine"
            />
          </div>
        </div>
      )}

      {/* Student Info Modal */}
      {selectedStudentForInfo && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setSelectedStudentForInfo(null)}
        >
          <div
            className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">Student Info</h3>
              <button
                onClick={() => setSelectedStudentForInfo(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-5">
              {patientInfoLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                </div>
              ) : patientInfoData && patientInfoData.found ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Last Visit Date</p>
                    <p className="mt-1 text-sm text-gray-900">
                      {patientInfoData.visit_date
                        ? new Date(patientInfoData.visit_date).toLocaleDateString('en-IN', {
                            day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
                          })
                        : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Counsellor</p>
                    <p className="mt-1 text-sm text-gray-900">{patientInfoData.counsellor_name || 'N/A'}</p>
                  </div>
                  {patientInfoData.preferred_language && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Preferred Language</p>
                      <p className="mt-1 text-sm text-gray-900">{patientInfoData.preferred_language}</p>
                    </div>
                  )}
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Diagnosis</p>
                    <p className="mt-1 text-sm text-gray-900">
                      {patientInfoData.diagnosis || <span className="text-gray-400">No diagnosis available</span>}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8">
                  <p className="text-sm text-gray-500">No visit data found for this student</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Student Info View
// ============================================================================

function StudentInfoView({
  students,
  selectedCategory,
  onStatusUpdate,
  onCategoryChange,
}: {
  students: StudentsListResponse | null;
  selectedCategory?: InterventionCategory;
  onStatusUpdate: (interventionId: string, newStatus: string) => void;
  onCategoryChange: (category: string) => void;
}) {
  const categoryConfig = selectedCategory
    ? CATEGORY_CONFIG[selectedCategory]
    : null;

  // Stats
  const totalStudents = students?.total_count || 0;
  // Overdue = any student with interventions > 0 days old
  const overdueCount = students?.students?.filter(
    (p) => p.interventions.some((i) => i.days_since_generated > 0)
  ).length || 0;
  // Critical = students with interventions > 7 days old
  const criticalCount = students?.students?.filter(
    (p) => p.interventions.some((i) => i.days_since_generated > 7)
  ).length || 0;
  const pendingCount = students?.students?.reduce(
    (sum, p) => sum + p.interventions.length,
    0
  ) || 0;

  return (
    <div className="space-y-6">
      {/* Filter Chip */}
      {selectedCategory && categoryConfig && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">Filtered by:</span>
            <span
              className={`px-3 py-1 ${categoryConfig.bgColor} ${categoryConfig.textColor} rounded-full text-sm font-medium`}
            >
              {categoryConfig.label}
            </span>
          </div>
          <button
            onClick={() => onCategoryChange('')}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            ✕ Clear Filters
          </button>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatsCard
          label="Total Students"
          value={totalStudents}
          color="gray"
        />
        <StatsCard
          label="Overdue"
          value={overdueCount}
          color="orange"
        />
        <StatsCard
          label="Critical (>7 days)"
          value={criticalCount}
          color="red"
        />
        <StatsCard
          label="Pending Interventions"
          value={pendingCount}
          color="blue"
        />
      </div>

      {/* Filters Row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <select
            className="px-4 py-2 border border-gray-200 rounded-lg text-sm bg-white text-gray-900"
            value={selectedCategory || ''}
            onChange={(e) => onCategoryChange(e.target.value)}
          >
            <option value="">All Categories</option>
            {Object.entries(CATEGORY_CONFIG).map(([key, config]) => (
              <option key={key} value={key}>
                {config.icon} {config.label}
              </option>
            ))}
          </select>
          <span className="text-sm text-gray-400">
            (Use header filters for School/Department/Counsellor)
          </span>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            placeholder="Search students..."
            className="px-4 py-2 border border-gray-200 rounded-lg text-sm w-64 text-gray-900"
          />
          <button className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 flex items-center gap-2">
            ↓ Export
          </button>
        </div>
      </div>

      {/* Patients Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto scrollbar-hide" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
        <table className="w-full min-w-[1000px]">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-[130px]">
                Student
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-[140px]">
                Intervention Type
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Reason for Risk
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-[150px]">
                Interventions Needed
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-[70px]">
                Overdue
              </th>
              <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-[60px]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {students?.students?.map((patient) => (
              <StudentRow
                key={patient.student_id}
                patient={patient}
                onStatusUpdate={onStatusUpdate}
              />
            ))}
            {(!students?.students || students.students.length === 0) && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-gray-500">
                  No students found for the selected filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================================
// Stats Card Component
// ============================================================================

function StatsCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: 'gray' | 'orange' | 'red' | 'blue' | 'green';
}) {
  const colorClasses = {
    gray: 'border-l-gray-400 text-gray-900',
    orange: 'border-l-orange-400 text-orange-600',
    red: 'border-l-red-400 text-red-600',
    blue: 'border-l-blue-400 text-blue-600',
    green: 'border-l-green-400 text-green-600',
  };

  return (
    <div
      className={`bg-white rounded-xl border border-gray-200 border-l-4 ${colorClasses[color]} p-4`}
    >
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${colorClasses[color].split(' ')[1]}`}>
        {value}
      </p>
    </div>
  );
}

// ============================================================================
// Student Row Component
// ============================================================================

function StudentRow({
  patient,
  onStatusUpdate,
}: {
  patient: StudentWithInterventions;
  onStatusUpdate: (interventionId: string, newStatus: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [reasonExpanded, setReasonExpanded] = useState(false);

  const maxDays = Math.max(
    ...patient.interventions.map((i) => i.days_since_generated),
    0
  );
  const daysInfo = getDaysOverdueText(maxDays);

  // Deduplicate interventions by code (keep first occurrence)
  const uniqueInterventions = patient.interventions.reduce((acc, intervention) => {
    if (!acc.find((i) => i.code === intervention.code)) {
      acc.push(intervention);
    }
    return acc;
  }, [] as typeof patient.interventions);

  // Get primary intervention info
  const primaryIntervention = uniqueInterventions[0];
  const interventionConfig = primaryIntervention
    ? CATEGORY_CONFIG[primaryIntervention.code as InterventionCategory]
    : null;

  // Interventions to display
  const visibleInterventions = expanded ? uniqueInterventions : uniqueInterventions.slice(0, 2);
  const hiddenCount = uniqueInterventions.length - 2;

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-3 py-3">
        <div>
          <p className="font-medium text-gray-900 text-xs">
            {patient.mrn ? `MRN: ${patient.mrn}` : patient.student_id?.slice(0, 8)}
          </p>
          {patient.counsellor_name && (
            <p className="text-xs text-gray-500">{patient.counsellor_name}</p>
          )}
        </div>
      </td>
      <td className="px-3 py-3">
        {primaryIntervention && (
          <span
            className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
              interventionConfig?.bgColor || 'bg-gray-100'
            } ${interventionConfig?.textColor || 'text-gray-700'}`}
          >
            {interventionConfig?.label || primaryIntervention.code.replace(/_/g, ' ')}
          </span>
        )}
      </td>
      <td className="px-3 py-3">
        {(() => {
          const reason = primaryIntervention?.trigger_reason || 'No details available';
          const isLongText = reason.length > 150;

          if (reasonExpanded) {
            // Expanded state - show full text
            return (
              <div>
                <p className="text-xs text-gray-600 whitespace-normal break-words">
                  {reason}
                </p>
                <button
                  onClick={() => setReasonExpanded(false)}
                  className="text-xs text-blue-600 hover:text-blue-800 font-medium mt-1"
                >
                  Show less
                </button>
              </div>
            );
          }

          // Collapsed state
          return (
            <div>
              <p className="text-xs text-gray-600 whitespace-normal break-words line-clamp-3">
                {isLongText ? reason.slice(0, 150) : reason}
                {isLongText && (
                  <button
                    onClick={() => setReasonExpanded(true)}
                    className="text-blue-600 hover:text-blue-800 font-medium ml-1"
                  >
                    ...more
                  </button>
                )}
              </p>
            </div>
          );
        })()}
      </td>
      <td className="px-3 py-3">
        <div className="flex flex-wrap gap-1">
          {visibleInterventions.map((intervention) => {
            const priorityColor = getPriorityColor(intervention.priority);
            return (
              <span
                key={intervention.id}
                className={`px-2 py-0.5 ${priorityColor.bg} ${priorityColor.text} rounded text-xs font-medium`}
              >
                {intervention.code.replace(/_/g, ' ')}
              </span>
            );
          })}
          {!expanded && hiddenCount > 0 && (
            <button
              onClick={() => setExpanded(true)}
              className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200 cursor-pointer transition-colors"
            >
              +{hiddenCount} more
            </button>
          )}
          {expanded && hiddenCount > 0 && (
            <button
              onClick={() => setExpanded(false)}
              className="px-2 py-0.5 bg-gray-200 text-gray-600 rounded text-xs hover:bg-gray-300 cursor-pointer transition-colors"
            >
              Show less
            </button>
          )}
        </div>
      </td>
      <td className="px-3 py-3">
        <span className={`font-medium text-xs ${daysInfo.color}`}>{daysInfo.text}</span>
      </td>
      <td className="px-3 py-3">
        <div className="flex flex-col gap-1">
          <button className="p-1.5 border border-gray-200 rounded-lg hover:bg-gray-50" title="Call">
            📞
          </button>
          <button className="p-1.5 border border-gray-200 rounded-lg hover:bg-gray-50" title="Message">
            💬
          </button>
          <button className="p-1.5 border border-gray-200 rounded-lg text-gray-400 hover:bg-gray-50" title="View">
            👁️
          </button>
        </div>
      </td>
    </tr>
  );
}

// ============================================================================
// Tracking View
// ============================================================================

function TrackingView({
  summary,
  outcomes,
  students,
  onCategoryClick,
  filters,
  accessToken,
}: {
  summary: InterventionSummaryResponse | null;
  outcomes: OutcomeMetricsResponse | null;
  students: StudentsListResponse | null;
  onCategoryClick: (category: InterventionCategory) => void;
  filters: { hospitalId?: string; departmentId?: string; doctorId?: string; period: TimePeriod };
  accessToken: string | null;
}) {
  const [viewMode, setViewMode] = useState<'intervention' | 'patient'>('intervention');
  const [allStudents, setAllStudents] = useState<StudentsListResponse | null>(null);
  const [loadingMatrix, setLoadingMatrix] = useState(false);

  // Fetch ALL students when switching to Student Matrix view
  useEffect(() => {
    async function fetchAllStudents() {
      if (viewMode !== 'patient' || !accessToken) return;

      setLoadingMatrix(true);
      try {
        const data = await getStudentsByCategory(
          undefined, // No category filter - get ALL students
          {
            hospitalId: filters.hospitalId,
            departmentId: filters.departmentId,
            doctorId: filters.doctorId,
            period: filters.period,
            pageSize: 100, // Get more students for the matrix
          },
          accessToken
        );
        setAllStudents(data);
      } catch (err) {
        console.error('Failed to fetch all students for matrix:', err);
      } finally {
        setLoadingMatrix(false);
      }
    }

    fetchAllStudents();
  }, [viewMode, accessToken, filters.hospitalId, filters.departmentId, filters.doctorId, filters.period]);

  const totalInterventions = outcomes?.total_interventions || 0;
  const pendingCount = outcomes?.by_status?.PENDING || 0;
  const assignedCount =
    (outcomes?.by_status?.CONTACTED || 0) + (outcomes?.by_status?.ACCEPTED || 0);
  const completedCount = outcomes?.by_status?.COMPLETED || 0;

  const completionRate =
    totalInterventions > 0 ? ((completedCount / totalInterventions) * 100).toFixed(0) : 0;
  const pendingPercent =
    totalInterventions > 0 ? ((pendingCount / totalInterventions) * 100).toFixed(0) : 0;

  const totalStudents = summary?.patients_with_interventions || 0;

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-4">
        {/* Total Interventions - Dark Card */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl p-5 text-white">
          <div className="flex items-start justify-between">
            <p className="text-gray-400 text-sm">Total Interventions</p>
            <span className="text-xl">📊</span>
          </div>
          <p className="text-4xl font-bold mt-2">{totalInterventions}</p>
          <p className="text-gray-400 text-sm mt-1">
            Across {totalStudents} students
          </p>
        </div>

        {/* Pending */}
        <div className="bg-white rounded-xl border-l-4 border-l-amber-400 border border-gray-200 p-5">
          <div className="flex items-start justify-between">
            <p className="text-gray-600 text-sm">Pending</p>
            <span className="w-8 h-8 bg-amber-100 rounded-full flex items-center justify-center">
              ⏳
            </span>
          </div>
          <p className="text-4xl font-bold text-amber-600 mt-2">{pendingCount}</p>
          <div className="w-full bg-gray-200 rounded-full h-1.5 mt-3">
            <div
              className="bg-amber-500 h-1.5 rounded-full"
              style={{ width: `${pendingPercent}%` }}
            ></div>
          </div>
          <p className="text-gray-500 text-xs mt-1">{pendingPercent}% of total</p>
        </div>

        {/* Assigned */}
        <div className="bg-white rounded-xl border-l-4 border-l-blue-400 border border-gray-200 p-5">
          <div className="flex items-start justify-between">
            <p className="text-gray-600 text-sm">Assigned</p>
            <span className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
              👤
            </span>
          </div>
          <p className="text-4xl font-bold text-blue-600 mt-2">{assignedCount}</p>
          <div className="w-full bg-gray-200 rounded-full h-1.5 mt-3">
            <div
              className="bg-blue-500 h-1.5 rounded-full"
              style={{
                width: `${totalInterventions > 0 ? (assignedCount / totalInterventions) * 100 : 0}%`,
              }}
            ></div>
          </div>
          <p className="text-gray-500 text-xs mt-1">In progress</p>
        </div>

        {/* Completed */}
        <div className="bg-white rounded-xl border-l-4 border-l-green-400 border border-gray-200 p-5">
          <div className="flex items-start justify-between">
            <p className="text-gray-600 text-sm">Completed</p>
            <span className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
              ✓
            </span>
          </div>
          <p className="text-4xl font-bold text-green-600 mt-2">{completedCount}</p>
          <div className="w-full bg-gray-200 rounded-full h-1.5 mt-3">
            <div
              className="bg-green-500 h-1.5 rounded-full"
              style={{ width: `${completionRate}%` }}
            ></div>
          </div>
          <p className="text-gray-500 text-xs mt-1">{completionRate}% completion rate</p>
        </div>
      </div>

      {/* View Toggle & Export */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 bg-gray-100 p-1 rounded-lg">
          <button
            onClick={() => setViewMode('intervention')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              viewMode === 'intervention'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            📊 Intervention View
          </button>
          <button
            onClick={() => setViewMode('patient')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              viewMode === 'patient'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            👥 Student Matrix
          </button>
        </div>
        <button className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 flex items-center gap-2">
          ↓ Export
        </button>
      </div>

      {/* Conditional View: Category Cards or Student Matrix */}
      {viewMode === 'intervention' ? (
        <div className="grid grid-cols-5 gap-3">
          {summary?.by_category?.map((category) => (
            <TrackingCategoryCard
              key={category.category}
              category={category}
              outcomes={outcomes}
              onClick={() => onCategoryClick(category.category as InterventionCategory)}
            />
          ))}
        </div>
      ) : loadingMatrix ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-gray-500">Loading student matrix...</div>
        </div>
      ) : (
        <StudentMatrixView
          students={allStudents}
          categories={summary?.by_category || []}
        />
      )}
    </div>
  );
}

// ============================================================================
// Student Matrix View Component
// ============================================================================

// Status symbol helper
function getStatusSymbol(status: string): { symbol: string; bg: string; text: string } {
  switch (status?.toUpperCase()) {
    case 'COMPLETED':
    case 'CONVERTED':
      return { symbol: '✓', bg: 'bg-green-100', text: 'text-green-600' };
    case 'CONTACTED':
    case 'ACCEPTED':
    case 'ASSIGNED':
      return { symbol: '👤', bg: 'bg-blue-100', text: 'text-blue-600' };
    case 'PENDING':
    default:
      return { symbol: '⏺', bg: 'bg-amber-100', text: 'text-amber-600' };
  }
}

// Map raw DB intervention categories to 6 dashboard categories
function mapToDisplayCategory(dbCategory: string): InterventionCategory {
  switch (dbCategory) {
    case 'TREATMENT_COMPLIANCE': return 'TREATMENT_COMPLIANCE';
    case 'FOLLOWUP_DUE': return 'FOLLOWUP_DUE';
    case 'RETENTION_RISK': return 'DROP_OFF_RISK';
    case 'DROP_OFF_RISK': return 'DROP_OFF_RISK';
    case 'RX_REFILL':
    case 'DIAGNOSTICS_DUE':
    case 'ALLIED_HEALTH': return 'HEALTH_SERVICES';
    case 'HEALTH_SERVICES': return 'HEALTH_SERVICES';
    case 'OP_TO_IP':
    case 'SURGERY_CANDIDATE': return 'SURGERY_CANDIDATE';
    case 'QUALITY_RISK': return 'QUALITY_RISK';
    default: return 'QUALITY_RISK';
  }
}

function StudentMatrixView({
  students,
  categories,
}: {
  students: StudentsListResponse | null;
  categories: CategoryStats[];
}) {
  // 6 dashboard categories for columns
  const allCategories: InterventionCategory[] = [
    'TREATMENT_COMPLIANCE',
    'DROP_OFF_RISK',
    'FOLLOWUP_DUE',
    'HEALTH_SERVICES',
    'SURGERY_CANDIDATE',
    'QUALITY_RISK',
  ];

  // Build student matrix data - group interventions by dashboard category for each student
  const patientData = students?.students?.map((patient) => {
    const interventionsByCategory: Record<string, { status: string; id: string } | null> = {};

    allCategories.forEach((cat) => {
      // Find any intervention whose DB category maps to this dashboard category
      const intervention = patient.interventions.find((i) => mapToDisplayCategory(i.category) === cat);
      interventionsByCategory[cat] = intervention
        ? { status: intervention.status || 'PENDING', id: intervention.id }
        : null;
    });

    return {
      ...patient,
      interventionsByCategory,
    };
  }) || [];

  // Get student initials
  const getInitials = (mrn: string | null | undefined, patientId: string | null | undefined): string => {
    if (mrn) {
      return mrn.slice(0, 2).toUpperCase();
    }
    return patientId?.slice(0, 2).toUpperCase() || '??';
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Legend */}
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex items-center gap-6">
        <span className="text-sm text-gray-500 font-medium">Status Legend:</span>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-6 h-6 bg-amber-100 rounded flex items-center justify-center text-amber-600 text-xs">⏺</span>
            <span className="text-xs text-gray-600">Pending</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-6 h-6 bg-blue-100 rounded flex items-center justify-center text-blue-600 text-xs">👤</span>
            <span className="text-xs text-gray-600">Assigned</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-6 h-6 bg-green-100 rounded flex items-center justify-center text-green-600 text-xs">✓</span>
            <span className="text-xs text-gray-600">Completed</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-6 h-6 bg-gray-100 rounded flex items-center justify-center text-gray-400 text-xs">-</span>
            <span className="text-xs text-gray-600">No intervention</span>
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px]">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-[180px] sticky left-0 bg-gray-50 z-10">
                Student
              </th>
              {allCategories.map((cat) => {
                const config = CATEGORY_CONFIG[cat];
                return (
                  <th
                    key={cat}
                    className="px-2 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-[90px]"
                  >
                    <div className="flex flex-col items-center gap-1">
                      <span className="text-base">{config?.icon || '📊'}</span>
                      <span className="text-[10px] leading-tight">{config?.label?.split(' ')[0] || cat}</span>
                    </div>
                  </th>
                );
              })}
              <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-[80px]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {patientData.length === 0 ? (
              <tr>
                <td colSpan={allCategories.length + 2} className="px-6 py-12 text-center text-gray-500">
                  No students found for the selected filters.
                </td>
              </tr>
            ) : (
              patientData.map((patient) => (
                <tr key={patient.student_id} className="hover:bg-gray-50">
                  {/* Student Info - Sticky */}
                  <td className="px-4 py-3 sticky left-0 bg-white z-10">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-medium text-xs">
                        {getInitials(patient.mrn, patient.student_id)}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {patient.mrn ? `MRN: ${patient.mrn}` : patient.student_id?.slice(0, 8)}
                        </p>
                        {patient.counsellor_name && (
                          <p className="text-xs text-gray-500 truncate">{patient.counsellor_name}</p>
                        )}
                      </div>
                    </div>
                  </td>
                  {/* Category Cells */}
                  {allCategories.map((cat) => {
                    const intervention = patient.interventionsByCategory[cat];
                    if (!intervention) {
                      return (
                        <td key={cat} className="px-2 py-3 text-center">
                          <span className="w-6 h-6 inline-flex items-center justify-center bg-gray-100 rounded text-gray-400 text-xs">
                            -
                          </span>
                        </td>
                      );
                    }
                    const statusInfo = getStatusSymbol(intervention.status);
                    return (
                      <td key={cat} className="px-2 py-3 text-center">
                        <span
                          className={`w-6 h-6 inline-flex items-center justify-center ${statusInfo.bg} rounded ${statusInfo.text} text-xs cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-blue-300`}
                          title={`${CATEGORY_CONFIG[cat]?.label || cat}: ${intervention.status}`}
                        >
                          {statusInfo.symbol}
                        </span>
                      </td>
                    );
                  })}
                  {/* Actions */}
                  <td className="px-3 py-3">
                    <div className="flex items-center justify-center gap-1">
                      <button
                        className="p-1.5 border border-gray-200 rounded hover:bg-gray-50"
                        title="Call student"
                      >
                        📞
                      </button>
                      <button
                        className="p-1.5 border border-gray-200 rounded hover:bg-gray-50"
                        title="Send message"
                      >
                        💬
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================================
// Tracking Category Card Component
// ============================================================================

function TrackingCategoryCard({
  category,
  outcomes,
  onClick,
}: {
  category: CategoryStats;
  outcomes: OutcomeMetricsResponse | null;
  onClick: () => void;
}) {
  const config = CATEGORY_CONFIG[category.category as InterventionCategory] || {
    label: category.label,
    textColor: 'text-gray-700',
    borderColor: 'border-gray-200',
    cardType: 'intervention' as const,
  };

  // Calculate mock counts for this category (would come from real data)
  const total = category.intervention_count;
  const pending = Math.floor(total * 0.65);
  const assigned = Math.floor(total * 0.25);
  const completed = total - pending - assigned;
  const completionRate = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <button
      onClick={onClick}
      className={`bg-white rounded-xl border ${config.borderColor} border-t-4 p-4 text-left hover:shadow-md transition-shadow w-full`}
      style={{
        borderTopColor:
          config.textColor === 'text-purple-700'
            ? '#7c3aed'
            : config.textColor === 'text-blue-700'
            ? '#1d4ed8'
            : config.textColor === 'text-orange-700'
            ? '#c2410c'
            : config.textColor === 'text-teal-700'
            ? '#0f766e'
            : config.textColor === 'text-green-700'
            ? '#15803d'
            : config.textColor === 'text-amber-700'
            ? '#b45309'
            : config.textColor === 'text-red-700'
            ? '#b91c1c'
            : '#6b7280',
      }}
    >
      <div className="mb-4">
        <p className={`font-semibold ${config.textColor}`}>{config.label}</p>
        <p className="text-xs text-gray-500">
          {category.intervention_types?.length || 0} intervention types
        </p>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm text-gray-600">
            <span className="w-2 h-2 bg-amber-400 rounded-full"></span>
            Pending
          </span>
          <span className="font-semibold text-amber-600">{pending}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm text-gray-600">
            <span className="w-2 h-2 bg-blue-400 rounded-full"></span>
            Assigned
          </span>
          <span className="font-semibold text-blue-600">{assigned}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm text-gray-600">
            <span className="w-2 h-2 bg-green-400 rounded-full"></span>
            Completed
          </span>
          <span className="font-semibold text-green-600">{completed}</span>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-gray-100">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-500">Completion</span>
          <span className="font-semibold text-gray-900">{completionRate}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
          <div
            className="bg-green-500 h-1.5 rounded-full transition-all"
            style={{ width: `${completionRate}%` }}
          ></div>
        </div>
      </div>
    </button>
  );
}
