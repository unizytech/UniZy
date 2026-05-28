# Transcription Prompt Architecture

This document describes how system prompts and schemas are assembled for different transcription and emotion analysis modes.

## Mode Matrix

| Emotion Mode | Audio Emotion Mode | Transcription Function | Emotion Analysis |
|--------------|-------------------|------------------------|------------------|
| `none` | N/A | `transcribe_audio()` | None |
| `text_only` | N/A | `transcribe_audio()` | Text only (after) |
| `audio_only` | `during_transcription` | `transcribe_audio_with_emotions()` | Audio (combined) |
| `audio_only` | `after_transcription` | `transcribe_audio()` | Audio (standalone) |
| `both` | `during_transcription` | `transcribe_audio_with_emotions()` | Audio (combined) + Text |
| `both` | `after_transcription` | `transcribe_audio()` | Audio (standalone) + Text |

---

## 1. Simple Transcription (`transcribe_audio()`)

**Used when:** `emotion_extraction_mode = none` OR `text_only` OR (`audio_only`/`both` + `after_transcription`)

| Level | Source | Config/Component |
|-------|--------|------------------|
| **System Prompt** | `system_prompt_configurations` | `TRANSCRIPTION_ONLY_PROMPT` |
| **Fallback** | `system_prompt_components` | `TRANSCRIPTION_BASE_PROMPT` |
| **User Prompt** | Runtime generated | `generate_transcription_user_prompt(target_language)` |

**No pre-assembly in templates table** - simple transcription uses config/component directly.

---

## 2. Text Emotion Analysis (`get_text_emotion_prompt_with_fallback`)

**Used when:** `emotion_extraction_mode = text_only` OR `both`

| Level | Source | Table/Column |
|-------|--------|--------------|
| **Level 1 (Fast)** | Pre-assembled | `templates.assembled_text_emotion_prompt` + `templates.assembled_text_emotion_schema_json` |
| **Level 2 (Fallback)** | Dynamic assembly | `segment_definitions` (TEXT_* segments) |
| **Base Prompt** | Config | `TEXT_EMOTION_PROMPT` → `TEXT_EMOTION_BASE_PROMPT` |
| **Level 3 (Hardcoded)** | Code | `emotion_prompts.py` |

**Schema:** `templates.assembled_text_emotion_schema_json` or dynamically built from `segment_definitions`

---

## 3. Audio Emotion - Combined Mode (`get_audio_transcription_prompt_with_fallback`)

**Used when:** (`audio_only` OR `both`) + `audio_emotion_mode = during_transcription`

| Level | Source | Table/Column |
|-------|--------|--------------|
| **Level 1 (Fast)** | Pre-assembled | `templates.assembled_audio_prompt` + `templates.assembled_audio_schema_json` |
| **Level 2 (Fallback)** | Dynamic assembly | `segment_definitions` (AUDIO_* segments) |
| **Base Prompt** | Config | `AUDIO_EMOTION_PROMPT_COMBINED` → `AUDIO_EMOTION_BASE_PROMPT_COMBINED` |
| **User Prompt** | Runtime generated | `generate_audio_emotion_transcription_prompt(target_language)` |

**Schema:** `templates.assembled_audio_schema_json` or dynamically built

---

## 4. Audio Emotion - Standalone Mode (`get_audio_emotion_prompt_with_fallback`)

**Used when:** (`audio_only` OR `both`) + `audio_emotion_mode = after_transcription`

| Level | Source | Table/Column |
|-------|--------|--------------|
| **Level 1 (Fast)** | Pre-assembled | `templates.assembled_audio_prompt` + `templates.assembled_audio_schema_json` |
| **Level 2 (Fallback)** | Dynamic assembly | `segment_definitions` (AUDIO_* segments) |
| **Base Prompt** | Config | `AUDIO_EMOTION_PROMPT_STANDALONE` → `AUDIO_EMOTION_BASE_PROMPT_STANDALONE` |
| **User Prompt** | Runtime generated | `generate_audio_emotion_standalone_prompt(transcript)` |

**Schema:** `templates.assembled_audio_schema_json` or dynamically built

---

## Prompt Stitching Pattern

For modes 2, 3, and 4, the full system prompt is constructed by concatenating:

```
Base Prompt (from database config/component)
+
Segment Guidelines (from templates table or dynamic assembly from segment_definitions)
```

### Code References

| Mode | Function | Stitching Code |
|------|----------|----------------|
| **2. Text Emotion** | `get_text_emotion_prompt_with_fallback` | `full_prompt = base_prompt + preassembled["assembled_text_emotion_prompt"]` |
| **3. Audio Combined** | `get_audio_transcription_prompt_with_fallback` | `combined_prompt = base_prompt + preassembled["assembled_audio_prompt"]` |
| **4. Audio Standalone** | `get_audio_emotion_prompt_with_fallback` | `full_prompt = base_prompt + preassembled["assembled_audio_prompt"]` |

The `base_prompt` is always fetched from the database first (config → component fallback), then the segment-specific content is appended to form the complete system prompt.

---

## Database Tables Summary

| Table | Purpose |
|-------|---------|
| `templates` | Pre-assembled prompts & schemas per template |
| `segment_definitions` | Individual segment prompts for dynamic assembly |
| `system_prompt_configurations` | Assembled base prompt configs |
| `system_prompt_components` | Raw base prompt components |
| `system_prompt_config_components` | Junction table linking configs ↔ components |

---

## Pre-assembled Columns in `templates` Table

| Column | Used For |
|--------|----------|
| `assembled_full_prompt` | Main extraction prompt |
| `assembled_schema_json` | Main extraction schema |
| `assembled_text_emotion_prompt` | Text emotion segment guidelines |
| `assembled_text_emotion_schema_json` | Text emotion schema |
| `assembled_audio_prompt` | Audio emotion segment guidelines |
| `assembled_audio_schema_json` | Audio emotion schema |

---

## System Prompt Configurations (Database)

| Config Code | Component Code | Used For |
|-------------|----------------|----------|
| `TRANSCRIPTION_ONLY_PROMPT` | `TRANSCRIPTION_BASE_PROMPT` | Simple transcription |
| `TEXT_EMOTION_PROMPT` | `TEXT_EMOTION_BASE_PROMPT` | Text emotion analysis |
| `AUDIO_EMOTION_PROMPT_COMBINED` | `AUDIO_EMOTION_BASE_PROMPT_COMBINED` | Audio+Transcription combined |
| `AUDIO_EMOTION_PROMPT_STANDALONE` | `AUDIO_EMOTION_BASE_PROMPT_STANDALONE` | Audio emotion after transcription |

---

## Related Migrations

- `20251226072000_add_text_emotion_base_prompt_component.sql` - TEXT_EMOTION_BASE_PROMPT
- `20251226090000_add_audio_emotion_base_prompt_components.sql` - AUDIO_EMOTION_BASE_PROMPT_STANDALONE & COMBINED
- `20251226110000_add_transcription_base_prompt_component.sql` - TRANSCRIPTION_BASE_PROMPT
