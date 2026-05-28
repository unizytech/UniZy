'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@lib/auth';
import {
  type ExtractionPhoto,
  ExtractionPhotoError,
  PHOTO_ALLOWED_MIME,
  PHOTO_MAX_BYTES,
  deleteExtractionPhoto,
  listExtractionPhotos,
  uploadExtractionPhoto,
} from '@lib/extractionPhotosApi';

interface Props {
  extractionId: string;
}

const PHOTO_ACCEPT = PHOTO_ALLOWED_MIME.join(',');

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ExtractionPhotosSection({ extractionId }: Props) {
  const { getAccessToken } = useAuth();

  const [photos, setPhotos] = useState<ExtractionPhoto[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [label, setLabel] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  const [previewPhoto, setPreviewPhoto] = useState<ExtractionPhoto | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await listExtractionPhotos(extractionId, getAccessToken());
      setPhotos(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load photos');
    } finally {
      setIsLoading(false);
    }
  }, [extractionId, getAccessToken]);

  useEffect(() => {
    if (extractionId) refresh();
  }, [extractionId, refresh]);

  const validateFile = (file: File): string | null => {
    if (!PHOTO_ALLOWED_MIME.includes(file.type as (typeof PHOTO_ALLOWED_MIME)[number])) {
      return `Unsupported image type. Allowed: ${PHOTO_ALLOWED_MIME.join(', ')}`;
    }
    if (file.size > PHOTO_MAX_BYTES) {
      return `Image is larger than the 10 MB limit (${formatBytes(file.size)}). Please choose a smaller file.`;
    }
    return null;
  };

  const handleFileChange = (file: File | null) => {
    setError(null);
    if (!file) {
      setSelectedFile(null);
      return;
    }
    const err = validateFile(file);
    if (err) {
      setError(err);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    const trimmedLabel = label.trim();
    if (!trimmedLabel) {
      setError('Please enter a name for this photo.');
      return;
    }

    setIsUploading(true);
    setError(null);
    try {
      const created = await uploadExtractionPhoto(
        extractionId,
        selectedFile,
        trimmedLabel,
        getAccessToken(),
      );
      setPhotos((prev) => [...prev, created]);
      setSelectedFile(null);
      setLabel('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (e) {
      if (e instanceof ExtractionPhotoError) setError(e.message);
      else setError(e instanceof Error ? e.message : 'Failed to upload photo');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (photoId: string) => {
    setPendingDeleteId(photoId);
    setError(null);
    try {
      await deleteExtractionPhoto(extractionId, photoId, getAccessToken());
      setPhotos((prev) => prev.filter((p) => p.id !== photoId));
      if (previewPhoto?.id === photoId) setPreviewPhoto(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete photo');
    } finally {
      setPendingDeleteId(null);
    }
  };

  return (
    <div className="mt-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-gray-800">
          Photos {photos.length > 0 && <span className="text-gray-500">({photos.length})</span>}
        </h3>
      </div>

      {/* Upload form */}
      <div className="mb-4 grid grid-cols-1 gap-3 rounded-md border border-dashed border-gray-300 bg-gray-50 p-3 sm:grid-cols-[1fr_1fr_auto]">
        <input
          ref={fileInputRef}
          type="file"
          accept={PHOTO_ACCEPT}
          onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
          className="block w-full text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
          disabled={isUploading}
        />
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Photo name (e.g., Lab report front)"
          maxLength={200}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-800 focus:border-blue-500 focus:outline-none"
          disabled={isUploading}
        />
        <button
          type="button"
          onClick={handleUpload}
          disabled={!selectedFile || !label.trim() || isUploading}
          className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          {isUploading ? 'Uploading...' : 'Upload'}
        </button>
      </div>

      {selectedFile && (
        <div className="mb-3 text-xs text-gray-600">
          Selected: <span className="font-medium">{selectedFile.name}</span> ({formatBytes(selectedFile.size)})
        </div>
      )}

      {error && (
        <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Photos grid */}
      {isLoading ? (
        <div className="py-6 text-center text-sm text-gray-500">Loading photos...</div>
      ) : photos.length === 0 ? (
        <div className="py-6 text-center text-sm text-gray-500">No photos attached yet.</div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {photos.map((photo) => (
            <div
              key={photo.id}
              className="group relative overflow-hidden rounded-md border border-gray-200 bg-gray-100"
            >
              {photo.signed_url ? (
                <button
                  type="button"
                  onClick={() => setPreviewPhoto(photo)}
                  className="block h-32 w-full"
                  title="Click to preview"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={photo.signed_url}
                    alt={photo.label}
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                </button>
              ) : (
                <div className="flex h-32 items-center justify-center text-xs text-gray-500">
                  Preview unavailable
                </div>
              )}
              <div className="px-2 py-1.5">
                <div
                  className="truncate text-xs font-medium text-gray-800"
                  title={photo.label}
                >
                  {photo.label}
                </div>
                <div className="text-[10px] text-gray-500">
                  {formatBytes(photo.file_size_bytes)}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (window.confirm(`Delete "${photo.label}"?`)) handleDelete(photo.id);
                }}
                disabled={pendingDeleteId === photo.id}
                className="absolute right-1 top-1 rounded bg-white/90 px-1.5 py-0.5 text-[11px] font-medium text-red-600 opacity-0 shadow transition-opacity hover:bg-white group-hover:opacity-100 disabled:cursor-not-allowed disabled:text-gray-400"
                title="Delete photo"
              >
                {pendingDeleteId === photo.id ? '...' : 'Delete'}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {previewPhoto && previewPhoto.signed_url && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setPreviewPhoto(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="relative max-h-[90vh] max-w-[90vw]"
            onClick={(e) => e.stopPropagation()}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewPhoto.signed_url}
              alt={previewPhoto.label}
              className="max-h-[85vh] max-w-[90vw] rounded-md object-contain"
            />
            <div className="mt-2 text-center text-sm text-white">
              {previewPhoto.label}
            </div>
            <button
              type="button"
              onClick={() => setPreviewPhoto(null)}
              className="absolute right-2 top-2 rounded-full bg-white/90 px-3 py-1 text-sm font-medium text-gray-800 hover:bg-white"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
