/**
 * Processing Modes Configuration
 * Defines model selection for transcription and extraction based on processing mode
 */

export type ProcessingMode = 'ultra' | 'fast' | 'default' | 'thorough';

export interface ProcessingModeConfig {
  transcriptionModel: string;
  extractionModel: string;
  description: string;
  estimatedTime: string;
}

export const PROCESSING_MODES: Record<ProcessingMode, ProcessingModeConfig> = {
  ultra: {
    transcriptionModel: 'gemini-2.5-pro',  // Native Audio API (Coming Soon)
    extractionModel: 'gemini-2.5-pro',
    description: 'Ultra-fast with Native Audio API',
    estimatedTime: '~10-15s'
  },
  fast: {
    transcriptionModel: 'gemini-2.5-flash',
    extractionModel: 'gemini-2.5-flash',
    description: 'Fast processing with Flash models',
    estimatedTime: '~20-30s'
  },
  default: {
    transcriptionModel: 'gemini-2.5-flash',
    extractionModel: 'gemini-2.5-pro',
    description: 'Balanced speed and quality',
    estimatedTime: '~30-45s'
  },
  thorough: {
    transcriptionModel: 'gemini-2.5-pro',
    extractionModel: 'gemini-2.5-pro',
    description: 'Maximum quality with Pro models',
    estimatedTime: '~45-60s'
  }
};

/**
 * Get extraction model for a given processing mode
 * Use this for Medical Summary screen (extraction only)
 */
export function getExtractionModel(mode: ProcessingMode): string {
  return PROCESSING_MODES[mode].extractionModel;
}

/**
 * Get transcription model for a given processing mode
 * Use this for Home screen (transcription + extraction)
 */
export function getTranscriptionModel(mode: ProcessingMode): string {
  return PROCESSING_MODES[mode].transcriptionModel;
}

/**
 * Get both models for a given processing mode
 */
export function getModels(mode: ProcessingMode): { transcription: string; extraction: string } {
  const config = PROCESSING_MODES[mode];
  return {
    transcription: config.transcriptionModel,
    extraction: config.extractionModel
  };
}
