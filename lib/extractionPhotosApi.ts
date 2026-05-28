/**
 * Extraction Photos API Client
 *
 * Upload, list, and delete photos attached to a medical extraction.
 */

import { API_BASE_URL, authFetch, type AuthOptions } from './apiClient';

export const PHOTO_MAX_BYTES = 10 * 1024 * 1024; // 10 MB

export const PHOTO_ALLOWED_MIME = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
  'image/heif',
] as const;

export type PhotoMimeType = typeof PHOTO_ALLOWED_MIME[number];

export interface ExtractionPhoto {
  id: string;
  extraction_id: string;
  label: string;
  original_filename: string | null;
  mime_type: string;
  file_size_bytes: number;
  signed_url: string | null;
  created_at: string;
}

export interface ExtractionPhotoListResponse {
  photos: ExtractionPhoto[];
  total: number;
}

export class ExtractionPhotoError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ExtractionPhotoError';
  }
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail) && data.detail[0]?.msg) return data.detail[0].msg;
  } catch {
    /* ignore */
  }
  return fallback;
}

export async function uploadExtractionPhoto(
  extractionId: string,
  file: File,
  label: string,
  auth: string | AuthOptions | null,
): Promise<ExtractionPhoto> {
  if (file.size > PHOTO_MAX_BYTES) {
    throw new ExtractionPhotoError(
      413,
      'Image is larger than the 10 MB limit. Please upload a smaller file.',
    );
  }
  if (!PHOTO_ALLOWED_MIME.includes(file.type as PhotoMimeType)) {
    throw new ExtractionPhotoError(
      400,
      `Unsupported image type. Allowed: ${PHOTO_ALLOWED_MIME.join(', ')}`,
    );
  }
  const trimmed = label.trim();
  if (!trimmed) {
    throw new ExtractionPhotoError(400, 'Label is required');
  }

  const form = new FormData();
  form.append('file', file);
  form.append('label', trimmed);

  const response = await authFetch(
    `${API_BASE_URL}/api/v1/extractions/${extractionId}/photos`,
    auth,
    { method: 'POST', body: form },
  );

  if (!response.ok) {
    const fallback =
      response.status === 413
        ? 'Image is larger than the 10 MB limit. Please upload a smaller file.'
        : response.status === 507
          ? 'Photo storage is full. Please try again later or contact support.'
          : 'Failed to upload photo';
    throw new ExtractionPhotoError(response.status, await readError(response, fallback));
  }

  return response.json();
}

export async function listExtractionPhotos(
  extractionId: string,
  auth: string | AuthOptions | null,
): Promise<ExtractionPhoto[]> {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/extractions/${extractionId}/photos`,
    auth,
  );
  if (!response.ok) {
    throw new ExtractionPhotoError(
      response.status,
      await readError(response, 'Failed to load photos'),
    );
  }
  const data: ExtractionPhotoListResponse = await response.json();
  return data.photos;
}

export async function deleteExtractionPhoto(
  extractionId: string,
  photoId: string,
  auth: string | AuthOptions | null,
): Promise<void> {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/extractions/${extractionId}/photos/${photoId}`,
    auth,
    { method: 'DELETE' },
  );
  if (!response.ok && response.status !== 204) {
    throw new ExtractionPhotoError(
      response.status,
      await readError(response, 'Failed to delete photo'),
    );
  }
}
