'use client';

/**
 * QA Suggested Questions Component
 *
 * Displays pre-defined question templates organized by category.
 * Supports category filtering via pills.
 */

import React from 'react';
import type { SuggestedQuestion, QuestionCategory } from '@lib/types';

// ============================================================================
// Types
// ============================================================================

interface QASuggestedQuestionsProps {
  questions: SuggestedQuestion[];
  onQuestionClick: (question: SuggestedQuestion) => void;
  selectedCategory: QuestionCategory | null;
  onCategoryChange: (category: QuestionCategory | null) => void;
  compact?: boolean;
}

// ============================================================================
// Category Configuration
// ============================================================================

const CATEGORY_CONFIG: Record<QuestionCategory, {
  label: string;
  icon: string;
  color: string;
  bgColor: string;
}> = {
  clinical: {
    label: 'Clinical',
    icon: '🩺',
    color: 'text-blue-700',
    bgColor: 'bg-blue-50 hover:bg-blue-100 border-blue-200',
  },
  risk: {
    label: 'Risk',
    icon: '⚠️',
    color: 'text-amber-700',
    bgColor: 'bg-amber-50 hover:bg-amber-100 border-amber-200',
  },
  referrals: {
    label: 'Referrals',
    icon: '🔀',
    color: 'text-purple-700',
    bgColor: 'bg-purple-50 hover:bg-purple-100 border-purple-200',
  },
  interventions: {
    label: 'Interventions',
    icon: '💡',
    color: 'text-green-700',
    bgColor: 'bg-green-50 hover:bg-green-100 border-green-200',
  },
  triage: {
    label: 'Triage',
    icon: '🚨',
    color: 'text-red-700',
    bgColor: 'bg-red-50 hover:bg-red-100 border-red-200',
  },
  analytics: {
    label: 'Analytics',
    icon: '📊',
    color: 'text-indigo-700',
    bgColor: 'bg-indigo-50 hover:bg-indigo-100 border-indigo-200',
  },
};

// ============================================================================
// Component
// ============================================================================

export default function QASuggestedQuestions({
  questions,
  onQuestionClick,
  selectedCategory,
  onCategoryChange,
  compact = false,
}: QASuggestedQuestionsProps) {
  // Group questions by category
  const groupedQuestions = questions.reduce((acc, q) => {
    if (!acc[q.category]) {
      acc[q.category] = [];
    }
    acc[q.category].push(q);
    return acc;
  }, {} as Record<QuestionCategory, SuggestedQuestion[]>);

  // Filter questions by selected category
  const filteredQuestions = selectedCategory
    ? questions.filter((q) => q.category === selectedCategory)
    : questions;

  // Limit display in compact mode
  const displayQuestions = compact ? filteredQuestions.slice(0, 6) : filteredQuestions;

  return (
    <div className={compact ? 'space-y-3' : 'space-y-6'}>
      {/* Category Pills */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-gray-500 font-medium">Filter by:</span>
        <button
          onClick={() => onCategoryChange(null)}
          className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors border ${
            selectedCategory === null
              ? 'bg-gray-900 text-white border-gray-900'
              : 'bg-gray-100 text-gray-700 border-gray-200 hover:bg-gray-200'
          }`}
        >
          All
        </button>
        {Object.entries(CATEGORY_CONFIG).map(([category, config]) => (
          <button
            key={category}
            onClick={() => onCategoryChange(
              selectedCategory === category ? null : category as QuestionCategory
            )}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors border flex items-center gap-1.5 ${
              selectedCategory === category
                ? 'bg-gray-900 text-white border-gray-900'
                : `${config.bgColor} ${config.color}`
            }`}
          >
            <span>{config.icon}</span>
            {config.label}
          </button>
        ))}
      </div>

      {/* Question Cards */}
      {compact ? (
        <div className="flex flex-wrap gap-2">
          {displayQuestions.map((question) => {
            const config = CATEGORY_CONFIG[question.category];
            return (
              <button
                key={question.id}
                onClick={() => onQuestionClick(question)}
                className={`px-3 py-2 rounded-lg text-sm text-left border transition-all hover:shadow-sm ${config.bgColor} ${config.color}`}
              >
                <span className="mr-1">{config.icon}</span>
                {question.question}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {displayQuestions.map((question) => {
            const config = CATEGORY_CONFIG[question.category];
            return (
              <button
                key={question.id}
                onClick={() => onQuestionClick(question)}
                className={`p-4 rounded-xl border text-left transition-all hover:shadow-md group ${config.bgColor}`}
              >
                <div className="flex items-start gap-3">
                  <span className="text-xl flex-shrink-0">{config.icon}</span>
                  <div className="flex-1 min-w-0">
                    <p className={`font-medium ${config.color} group-hover:underline`}>
                      {question.question}
                    </p>
                    {question.description && (
                      <p className="text-sm text-gray-500 mt-1">
                        {question.description}
                      </p>
                    )}
                  </div>
                  <svg
                    className="w-5 h-5 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M14 5l7 7m0 0l-7 7m7-7H3"
                    />
                  </svg>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {displayQuestions.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <p>No suggested questions available for this category.</p>
        </div>
      )}
    </div>
  );
}
