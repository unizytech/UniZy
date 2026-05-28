'use client';

import React from 'react';

// 7-category system for dashboard
// OP_TO_IP, FOLLOWUP_DUE, RX_REFILL, DIAGNOSTICS_DUE, ALLIED_HEALTH, RETENTION_RISK, QUALITY_RISK
export interface InterventionData {
  id?: string;
  code: string;
  name: string;
  description: string;
  category: string;  // 7 categories: OP_TO_IP, FOLLOWUP_DUE, RX_REFILL, DIAGNOSTICS_DUE, ALLIED_HEALTH, RETENTION_RISK, QUALITY_RISK
  priority: string;
  priority_score: number;
  trigger_reason: string;
  is_top_3: boolean;
  analysis_mode: string;
  rationale_sources: Record<string, unknown> | Array<{ segment: string; source_mode: string; content: string }>;
  created_at?: string;
  // New fields for insights-based interventions
  intervention_sub_type?: string;
  action?: string;
  revenue_estimate?: number;
  take_up_likelihood?: number;  // 0-100 predicted take-up likelihood (for dashboard risk segmentation)
}

interface InterventionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  interventions: InterventionData[];
  loading: boolean;
  error?: string;
  extractionId?: string | null;
  onRefresh?: () => void;
  insightsEnabled?: boolean;  // Whether consultation insights is enabled for this consultation type
}

export function InterventionsModal({
  isOpen,
  onClose,
  interventions,
  loading,
  error,
  extractionId,
  onRefresh,
  insightsEnabled = true,
}: InterventionsModalProps) {
  const [activeCategory, setActiveCategory] = React.useState<string | null>(null);

  if (!isOpen) return null;

  // Group interventions by new 7-category system
  const categoryCounts = {
    OP_TO_IP: interventions.filter(i => i.category === 'OP_TO_IP').length,
    FOLLOWUP_DUE: interventions.filter(i => i.category === 'FOLLOWUP_DUE').length,
    RX_REFILL: interventions.filter(i => i.category === 'RX_REFILL').length,
    DIAGNOSTICS_DUE: interventions.filter(i => i.category === 'DIAGNOSTICS_DUE').length,
    ALLIED_HEALTH: interventions.filter(i => i.category === 'ALLIED_HEALTH').length,
    RETENTION_RISK: interventions.filter(i => i.category === 'RETENTION_RISK').length,
    QUALITY_RISK: interventions.filter(i => i.category === 'QUALITY_RISK').length,
  };

  // Revenue-related categories for calculating potential
  const revenueCategoryNames = ['OP_TO_IP', 'FOLLOWUP_DUE', 'RX_REFILL', 'DIAGNOSTICS_DUE', 'ALLIED_HEALTH'];
  const totalRevenuePotential = interventions
    .filter(i => revenueCategoryNames.includes(i.category) && i.revenue_estimate)
    .reduce((sum, i) => sum + (i.revenue_estimate || 0), 0);

  // Filter interventions based on active category
  const displayInterventions = activeCategory
    ? interventions.filter(i => i.category === activeCategory)
    : interventions;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={onClose}
        />

        {/* Modal */}
        <div className="relative inline-block w-full max-w-4xl my-8 text-left align-middle bg-white rounded-2xl shadow-xl transform transition-all">
          {/* Header */}
          <div className="bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-4 rounded-t-2xl">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🎯</span>
                <div>
                  <h2 className="text-xl font-bold text-white">Patient Interventions</h2>
                  <p className="text-indigo-200 text-sm">
                    {interventions.length} recommended actions based on consultation analysis
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {onRefresh && (
                  <button
                    onClick={onRefresh}
                    className="p-2 text-white hover:bg-white/20 rounded-lg transition-colors"
                    title="Refresh interventions"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                )}
                <button
                  onClick={onClose}
                  className="p-2 text-white hover:bg-white/20 rounded-lg transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Category Summary Cards - 7 categories in 2 rows */}
            <div className="mt-4 space-y-2">
              {/* Revenue Categories (Top Row) */}
              <div className="flex flex-wrap gap-2">
                <CategoryCard
                  title="OP to IP"
                  count={categoryCounts.OP_TO_IP}
                  icon="🏥"
                  color="purple"
                  isActive={activeCategory === 'OP_TO_IP'}
                  onClick={() => setActiveCategory(activeCategory === 'OP_TO_IP' ? null : 'OP_TO_IP')}
                />
                <CategoryCard
                  title="Follow-up"
                  count={categoryCounts.FOLLOWUP_DUE}
                  icon="📅"
                  color="blue"
                  isActive={activeCategory === 'FOLLOWUP_DUE'}
                  onClick={() => setActiveCategory(activeCategory === 'FOLLOWUP_DUE' ? null : 'FOLLOWUP_DUE')}
                />
                <CategoryCard
                  title="Rx Refill"
                  count={categoryCounts.RX_REFILL}
                  icon="💊"
                  color="teal"
                  isActive={activeCategory === 'RX_REFILL'}
                  onClick={() => setActiveCategory(activeCategory === 'RX_REFILL' ? null : 'RX_REFILL')}
                />
                <CategoryCard
                  title="Diagnostics"
                  count={categoryCounts.DIAGNOSTICS_DUE}
                  icon="🔬"
                  color="cyan"
                  isActive={activeCategory === 'DIAGNOSTICS_DUE'}
                  onClick={() => setActiveCategory(activeCategory === 'DIAGNOSTICS_DUE' ? null : 'DIAGNOSTICS_DUE')}
                />
                <CategoryCard
                  title="Allied Health"
                  count={categoryCounts.ALLIED_HEALTH}
                  icon="🏃"
                  color="emerald"
                  isActive={activeCategory === 'ALLIED_HEALTH'}
                  onClick={() => setActiveCategory(activeCategory === 'ALLIED_HEALTH' ? null : 'ALLIED_HEALTH')}
                />
              </div>
              {/* Risk Categories (Bottom Row) */}
              <div className="flex flex-wrap gap-2">
                <CategoryCard
                  title="Retention Risk"
                  count={categoryCounts.RETENTION_RISK}
                  icon="⚠️"
                  color="amber"
                  isActive={activeCategory === 'RETENTION_RISK'}
                  onClick={() => setActiveCategory(activeCategory === 'RETENTION_RISK' ? null : 'RETENTION_RISK')}
                />
                <CategoryCard
                  title="Quality Risk"
                  count={categoryCounts.QUALITY_RISK}
                  icon="🚨"
                  color="red"
                  isActive={activeCategory === 'QUALITY_RISK'}
                  onClick={() => setActiveCategory(activeCategory === 'QUALITY_RISK' ? null : 'QUALITY_RISK')}
                />
                {totalRevenuePotential > 0 && (
                  <div className="bg-green-500/30 border border-green-400/50 rounded-lg px-3 py-1.5 flex items-center gap-1.5">
                    <span className="text-lg">💰</span>
                    <span className="text-white text-sm font-medium">₹{totalRevenuePotential.toLocaleString()} potential</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="px-6 py-4 max-h-[60vh] overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                <span className="ml-3 text-gray-600">Loading interventions...</span>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                {error}
              </div>
            ) : !insightsEnabled ? (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-6 text-center">
                <svg className="w-12 h-12 text-amber-500 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.072 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
                <h3 className="text-lg font-semibold text-amber-800 mt-2">Consultation Insights Not Enabled</h3>
                <p className="text-amber-600 mt-1">
                  Consultation insights (and interventions) are not enabled for this consultation type. Enable it in the Config screen.
                </p>
              </div>
            ) : interventions.length === 0 ? (
              <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
                <span className="text-4xl">✅</span>
                <h3 className="text-lg font-semibold text-green-800 mt-2">No Interventions Required</h3>
                <p className="text-green-600 mt-1">
                  Based on the consultation analysis, no specific interventions are recommended at this time.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {activeCategory && (
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-gray-500">
                      Showing {displayInterventions.length} {activeCategory.toLowerCase()} interventions
                    </span>
                    <button
                      onClick={() => setActiveCategory(null)}
                      className="text-sm text-indigo-600 hover:text-indigo-800"
                    >
                      Show all
                    </button>
                  </div>
                )}
                {displayInterventions
                  .sort((a, b) => b.priority_score - a.priority_score)
                  .map((intervention, idx) => (
                    <InterventionCard
                      key={intervention.id || `${intervention.code}-${idx}`}
                      intervention={intervention}
                      rank={idx + 1}
                    />
                  ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="bg-gray-50 px-6 py-3 rounded-b-2xl border-t border-gray-200 flex justify-between items-center">
            <span className="text-xs text-gray-500">
              {extractionId ? `Extraction: ${extractionId.slice(0, 8)}...` : ''}
            </span>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Category Card Component
interface CategoryCardProps {
  title: string;
  count: number;
  icon: string;
  color: 'emerald' | 'amber' | 'blue' | 'purple' | 'teal' | 'cyan' | 'red';
  isActive: boolean;
  onClick: () => void;
}

function CategoryCard({ title, count, icon, color, isActive, onClick }: CategoryCardProps) {
  const colorClasses: Record<string, { bg: string; text: string; border: string }> = {
    purple: {
      bg: isActive ? 'bg-purple-500' : 'bg-white/20',
      text: 'text-white',
      border: isActive ? 'border-purple-400' : 'border-white/30',
    },
    blue: {
      bg: isActive ? 'bg-blue-500' : 'bg-white/20',
      text: 'text-white',
      border: isActive ? 'border-blue-400' : 'border-white/30',
    },
    teal: {
      bg: isActive ? 'bg-teal-500' : 'bg-white/20',
      text: 'text-white',
      border: isActive ? 'border-teal-400' : 'border-white/30',
    },
    cyan: {
      bg: isActive ? 'bg-cyan-500' : 'bg-white/20',
      text: 'text-white',
      border: isActive ? 'border-cyan-400' : 'border-white/30',
    },
    emerald: {
      bg: isActive ? 'bg-emerald-500' : 'bg-white/20',
      text: 'text-white',
      border: isActive ? 'border-emerald-400' : 'border-white/30',
    },
    amber: {
      bg: isActive ? 'bg-amber-500' : 'bg-white/20',
      text: 'text-white',
      border: isActive ? 'border-amber-400' : 'border-white/30',
    },
    red: {
      bg: isActive ? 'bg-red-500' : 'bg-white/20',
      text: 'text-white',
      border: isActive ? 'border-red-400' : 'border-white/30',
    },
  };

  const classes = colorClasses[color] || colorClasses.blue;

  // Don't show categories with 0 count (except when active)
  if (count === 0 && !isActive) return null;

  return (
    <button
      onClick={onClick}
      className={`${classes.bg} ${classes.border} border rounded-lg px-3 py-1.5 text-left transition-all hover:scale-105`}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-lg">{icon}</span>
        <span className={`font-medium text-sm ${classes.text}`}>
          {title} ({count})
        </span>
      </div>
    </button>
  );
}

// Intervention Card Component
interface InterventionCardProps {
  intervention: InterventionData;
  rank: number;
}

function InterventionCard({ intervention, rank }: InterventionCardProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);

  const getPriorityConfig = (priority: string) => {
    switch (priority?.toUpperCase()) {
      case 'CRITICAL':
        return { bg: 'bg-red-50', text: 'text-red-800', border: 'border-red-200', badge: 'bg-red-600 text-white', icon: '🚨' };
      case 'HIGH':
        return { bg: 'bg-orange-50', text: 'text-orange-800', border: 'border-orange-200', badge: 'bg-orange-500 text-white', icon: '⚠️' };
      case 'MEDIUM':
        return { bg: 'bg-yellow-50', text: 'text-yellow-800', border: 'border-yellow-200', badge: 'bg-yellow-500 text-white', icon: '📋' };
      case 'LOW':
        return { bg: 'bg-blue-50', text: 'text-blue-800', border: 'border-blue-200', badge: 'bg-blue-500 text-white', icon: '💡' };
      default:
        return { bg: 'bg-gray-50', text: 'text-gray-800', border: 'border-gray-200', badge: 'bg-gray-500 text-white', icon: '•' };
    }
  };

  const getCategoryConfig = (category: string) => {
    switch (category?.toUpperCase()) {
      case 'OP_TO_IP':
        return { bg: 'bg-purple-100', text: 'text-purple-800', icon: '🏥', label: 'OP to IP' };
      case 'FOLLOWUP_DUE':
        return { bg: 'bg-blue-100', text: 'text-blue-800', icon: '📅', label: 'Follow-up' };
      case 'RX_REFILL':
        return { bg: 'bg-teal-100', text: 'text-teal-800', icon: '💊', label: 'Rx Refill' };
      case 'DIAGNOSTICS_DUE':
        return { bg: 'bg-cyan-100', text: 'text-cyan-800', icon: '🔬', label: 'Diagnostics' };
      case 'ALLIED_HEALTH':
        return { bg: 'bg-emerald-100', text: 'text-emerald-800', icon: '🏃', label: 'Allied Health' };
      case 'RETENTION_RISK':
        return { bg: 'bg-amber-100', text: 'text-amber-800', icon: '⚠️', label: 'Retention Risk' };
      case 'QUALITY_RISK':
        return { bg: 'bg-red-100', text: 'text-red-800', icon: '🚨', label: 'Quality Risk' };
      // Legacy categories (for backward compatibility)
      case 'REVENUE':
        return { bg: 'bg-emerald-100', text: 'text-emerald-800', icon: '💰', label: 'Revenue' };
      case 'RETENTION':
        return { bg: 'bg-amber-100', text: 'text-amber-800', icon: '🤝', label: 'Retention' };
      case 'QUALITY':
        return { bg: 'bg-blue-100', text: 'text-blue-800', icon: '⚕️', label: 'Quality' };
      default:
        return { bg: 'bg-gray-100', text: 'text-gray-800', icon: '📌', label: category };
    }
  };

  const config = getPriorityConfig(intervention.priority);
  const categoryConfig = getCategoryConfig(intervention.category);

  // Format rationale sources - handle both dict and array formats
  const formatRationale = () => {
    const sources = intervention.rationale_sources;
    if (!sources) return null;

    // If it's an array (old format)
    if (Array.isArray(sources)) {
      return sources
        .map(s => s.content)
        .filter(c => c && c.length > 0)
        .join(' • ');
    }

    // If it's a dict (new insights-based format)
    if (typeof sources === 'object') {
      const entries: string[] = [];
      for (const [key, value] of Object.entries(sources)) {
        // Skip take_up_prediction - it's shown separately
        if (key === 'take_up_prediction') continue;

        if (Array.isArray(value)) {
          entries.push(`${formatKey(key)}: ${value.join(', ')}`);
        } else if (value !== null && value !== undefined) {
          // Handle nested objects
          if (typeof value === 'object') {
            entries.push(`${formatKey(key)}: ${JSON.stringify(value)}`);
          } else {
            entries.push(`${formatKey(key)}: ${String(value)}`);
          }
        }
      }
      return entries.join(' • ');
    }

    return null;
  };

  const formatKey = (key: string) => {
    return key
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  };

  const rationaleText = formatRationale();
  const hasRationale = rationaleText && rationaleText.length > 0;

  return (
    <div className={`${config.bg} ${config.border} border rounded-lg overflow-hidden`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-start justify-between hover:bg-opacity-80 transition-colors text-left"
      >
        <div className="flex items-start gap-3 flex-1">
          {/* Rank Badge */}
          <div className={`flex-shrink-0 w-7 h-7 ${config.badge} rounded-full flex items-center justify-center text-sm font-bold`}>
            {rank}
          </div>

          <div className="flex-1 min-w-0">
            {/* Tags Row */}
            <div className="flex items-center gap-2 flex-wrap mb-1">
              {/* Category Tag */}
              <span className={`${categoryConfig.bg} ${categoryConfig.text} text-xs px-2 py-0.5 rounded-full font-medium`}>
                {categoryConfig.icon} {categoryConfig.label}
              </span>
              {/* Priority Tag */}
              <span className={`${config.badge} text-xs px-2 py-0.5 rounded`}>
                {intervention.priority.toUpperCase()}
              </span>
              {/* Sub-type Tag */}
              {intervention.intervention_sub_type && (
                <span className="bg-gray-200 text-gray-700 text-xs px-2 py-0.5 rounded">
                  {intervention.intervention_sub_type.replace(/_/g, ' ')}
                </span>
              )}
              {/* Revenue Estimate */}
              {intervention.revenue_estimate && intervention.revenue_estimate > 0 && (
                <span className="bg-green-100 text-green-700 text-xs px-2 py-0.5 rounded font-medium">
                  ₹{intervention.revenue_estimate.toLocaleString()}
                </span>
              )}
              {/* Take-Up Likelihood Badge */}
              {(() => {
                const sources = intervention.rationale_sources;
                if (!sources || Array.isArray(sources) || typeof sources !== 'object') return null;
                const prediction = sources.take_up_prediction as { likelihood?: number } | undefined;
                if (!prediction?.likelihood) return null;
                const likelihood = prediction.likelihood;
                const colorClass = likelihood >= 70 ? 'bg-green-100 text-green-700' :
                                   likelihood >= 40 ? 'bg-amber-100 text-amber-700' :
                                   'bg-red-100 text-red-700';
                return (
                  <span className={`${colorClass} text-xs px-2 py-0.5 rounded font-medium`}>
                    📊 {likelihood}% take-up
                  </span>
                );
              })()}
            </div>

            {/* Intervention Name */}
            <div className="flex items-center gap-2">
              <span className="text-lg">{config.icon}</span>
              <span className={`font-semibold ${config.text}`}>
                {intervention.name}
              </span>
            </div>

            {/* Trigger Reason */}
            {intervention.trigger_reason && (
              <p className="text-sm text-gray-600 mt-1">
                <span className="font-medium">Trigger:</span> {intervention.trigger_reason}
              </p>
            )}

            {/* Action */}
            {intervention.action && (
              <p className="text-sm text-indigo-700 mt-1">
                <span className="font-medium">Action:</span> {intervention.action}
              </p>
            )}
          </div>
        </div>

        {/* Expand Button */}
        <svg
          className={`w-5 h-5 ${config.text} transition-transform flex-shrink-0 mt-1 ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="px-4 pb-4 border-t border-gray-200 bg-white bg-opacity-50">
          <div className="pt-3 space-y-3">
            {/* Description */}
            {intervention.description && (
              <div>
                <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                  Description
                </div>
                <p className="text-sm text-gray-700">{intervention.description}</p>
              </div>
            )}

            {/* Rationale */}
            {hasRationale && (
              <div>
                <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                  Rationale & Evidence
                </div>
                <div className="bg-white rounded p-3 border border-gray-200 text-sm">
                  <p className="text-gray-700 leading-relaxed">{rationaleText}</p>
                </div>
              </div>
            )}

            {/* Take-Up Prediction */}
            {intervention.rationale_sources &&
             typeof intervention.rationale_sources === 'object' &&
             !Array.isArray(intervention.rationale_sources) &&
             'take_up_prediction' in intervention.rationale_sources && (
              <div>
                <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                  Take-Up Prediction
                </div>
                {(() => {
                  const prediction = intervention.rationale_sources.take_up_prediction as {
                    likelihood?: number;
                    signal_contributions?: Record<string, number>;
                    rules_applied?: string[];
                    priority_modifier?: number;
                    fear_distress_boost?: number;
                    original_priority_score?: number;
                    adjusted_priority_score?: number;
                  };
                  if (!prediction) return null;

                  const likelihood = prediction.likelihood ?? 0;
                  const likelihoodColor = likelihood >= 70 ? 'text-green-600 bg-green-50' :
                                          likelihood >= 40 ? 'text-amber-600 bg-amber-50' :
                                          'text-red-600 bg-red-50';
                  const likelihoodLabel = likelihood >= 70 ? 'High' : likelihood >= 40 ? 'Medium' : 'Low';

                  return (
                    <div className="bg-white rounded p-3 border border-gray-200 space-y-2">
                      {/* Likelihood Score */}
                      <div className="flex items-center gap-3">
                        <span className={`${likelihoodColor} px-2 py-1 rounded font-medium text-sm`}>
                          {likelihood}% ({likelihoodLabel})
                        </span>
                        {prediction.priority_modifier && prediction.priority_modifier !== 1.0 && (
                          <span className="text-xs text-gray-500">
                            Priority {prediction.priority_modifier > 1 ? '↑' : '↓'}
                            {Math.abs((prediction.priority_modifier - 1) * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>

                      {/* Signal Contributions */}
                      {prediction.signal_contributions && Object.keys(prediction.signal_contributions).length > 0 && (
                        <div className="text-xs text-gray-600">
                          <span className="font-medium">Signals: </span>
                          {Object.entries(prediction.signal_contributions)
                            .filter(([, v]) => v > 0)
                            .map(([k, v]) => `${k.replace(/_/g, ' ')} (${v})`)
                            .join(', ')}
                        </div>
                      )}

                      {/* Rules Applied */}
                      {prediction.rules_applied && prediction.rules_applied.length > 0 && (
                        <div className="text-xs text-gray-600">
                          <span className="font-medium">Rules: </span>
                          {prediction.rules_applied.join(', ')}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Raw Rationale Sources (for debugging) */}
            {intervention.rationale_sources && typeof intervention.rationale_sources === 'object' && !Array.isArray(intervention.rationale_sources) && (
              <div>
                <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                  Source Data
                </div>
                <pre className="bg-gray-100 rounded p-2 text-xs text-gray-600 overflow-x-auto">
                  {JSON.stringify(intervention.rationale_sources, null, 2)}
                </pre>
              </div>
            )}

            {/* Metadata */}
            <div className="flex items-center gap-4 text-xs text-gray-500 pt-2 border-t border-gray-200">
              <span>Code: {intervention.code}</span>
              <span>Score: {intervention.priority_score}</span>
              <span>Mode: {intervention.analysis_mode}</span>
              {intervention.created_at && (
                <span>Created: {new Date(intervention.created_at).toLocaleString()}</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default InterventionsModal;
