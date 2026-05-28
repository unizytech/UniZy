/**
 * Calculate Word Error Rate (WER) and Character Error Rate (CER)
 * between reference (ground truth) and hypothesis (transcription)
 */

/**
 * Calculate the Levenshtein distance between two arrays
 */
function levenshteinDistance(arr1: string[], arr2: string[]): number {
  const m = arr1.length;
  const n = arr2.length;
  const dp: number[][] = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0));

  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (arr1[i - 1] === arr2[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1];
      } else {
        dp[i][j] = 1 + Math.min(
          dp[i - 1][j],     // deletion
          dp[i][j - 1],     // insertion
          dp[i - 1][j - 1]  // substitution
        );
      }
    }
  }

  return dp[m][n];
}

/**
 * Normalize text for comparison:
 * - Lowercase
 * - Remove punctuation
 * - Trim whitespace
 */
function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s]/g, '') // Remove punctuation
    .replace(/\s+/g, ' ')    // Normalize whitespace
    .trim();
}

/**
 * Calculate Word Error Rate (WER)
 * WER = (Substitutions + Deletions + Insertions) / Total Words in Reference
 * Returns a percentage (0-100)
 */
export function calculateWER(reference: string, hypothesis: string): number {
  const refWords = normalizeText(reference).split(' ').filter(w => w.length > 0);
  const hypWords = normalizeText(hypothesis).split(' ').filter(w => w.length > 0);

  if (refWords.length === 0) return 0;

  const distance = levenshteinDistance(refWords, hypWords);
  const wer = (distance / refWords.length) * 100;

  return Math.min(100, parseFloat(wer.toFixed(2)));
}

/**
 * Calculate Character Error Rate (CER)
 * CER = (Substitutions + Deletions + Insertions) / Total Characters in Reference
 * Returns a percentage (0-100)
 */
export function calculateCER(reference: string, hypothesis: string): number {
  const refChars = normalizeText(reference).split('');
  const hypChars = normalizeText(hypothesis).split('');

  if (refChars.length === 0) return 0;

  const distance = levenshteinDistance(refChars, hypChars);
  const cer = (distance / refChars.length) * 100;

  return Math.min(100, parseFloat(cer.toFixed(2)));
}

/**
 * Calculate accuracy percentage (100 - WER)
 */
export function calculateAccuracy(reference: string, hypothesis: string): number {
  const wer = calculateWER(reference, hypothesis);
  return parseFloat((100 - wer).toFixed(2));
}

/**
 * Calculate all metrics at once
 */
export interface AccuracyMetrics {
  wer: number;        // Word Error Rate (%)
  cer: number;        // Character Error Rate (%)
  accuracy: number;   // Accuracy (100 - WER) (%)
}

export function calculateAllMetrics(reference: string, hypothesis: string): AccuracyMetrics {
  const wer = calculateWER(reference, hypothesis);
  const cer = calculateCER(reference, hypothesis);
  const accuracy = parseFloat((100 - wer).toFixed(2));

  return { wer, cer, accuracy };
}
