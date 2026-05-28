import { GoogleGenAI, Type } from "@google/genai";
import {
    MEDICAL_EXTRACTION_PROMPT_TEMPLATE,
    MEDICAL_EXTRACTION_PROMPT_BASE,
    MEDICAL_EXTRACTION_PROMPT_CONCISE,
    MEDICAL_EXTRACTION_PROMPT_DETAILED,
} from './prompts';

const API_KEY = process.env.GEMINI_API_KEY;

if (!API_KEY) {
  throw new Error("GEMINI_API_KEY environment variable not set.");
}

const ai = new GoogleGenAI({ apiKey: API_KEY });

// Backend-only functions for API routes
// Client-side live session functions remain in services/geminiService.ts

const medicalInsightsSchema = {
    type: Type.OBJECT,
    properties: {
      patient_info: {
        type: Type.OBJECT,
        properties: {
          name: { type: Type.STRING, description: "Full name or N/A" },
          phone: { type: Type.STRING, description: "10-digit number or empty" },
          email: { type: Type.STRING, description: "Email or empty" }
        },
        required: ['name', 'phone', 'email']
      },
      insights: {
        type: Type.OBJECT,
        properties: {
          Context: { type: Type.ARRAY, items: { type: Type.STRING } },
          Analysis: { type: Type.ARRAY, items: { type: Type.STRING } },
          "Treatment Plan": { type: Type.ARRAY, items: { type: Type.STRING } },
          Investigation: { type: Type.ARRAY, items: { type: Type.STRING } },
          Summary: { type: Type.ARRAY, items: { type: Type.STRING } },
          Diagnosis: { type: Type.ARRAY, items: { type: Type.STRING } },
          History: { type: Type.ARRAY, items: { type: Type.STRING } },
          Examination: { type: Type.ARRAY, items: { type: Type.STRING } },
          "Key Facts": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Timestamped Transcription": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Prescription Data": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Chief Complaint(s)": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Present Illness Information": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Preliminary Assessment": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Next Steps": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Associated Symptoms": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Past Medical History": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Doctor's Observations": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Referral Details": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Subtext Analysis": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Patient Details": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Hospital/Doctor Details": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Additional Observations": { type: Type.ARRAY, items: { type: Type.STRING } },
          "Clinical Information": {
            type: Type.OBJECT,
            properties: {
              chief_complaint: { type: Type.STRING },
              nature_of_illness: { type: Type.STRING },
              duration_of_illness: { type: Type.STRING },
            },
            required: ['chief_complaint', 'nature_of_illness', 'duration_of_illness']
          },
          "Start Date": { type: Type.ARRAY, items: { type: Type.STRING } },
          Protocol: {
            type: Type.ARRAY,
            items: {
              type: Type.OBJECT,
              properties: {
                id: { type: Type.NULL },
                displayName: { type: Type.STRING },
                blocks: {
                  type: Type.ARRAY,
                  items: {
                    type: Type.OBJECT,
                    properties: {
                      displayName: { type: Type.STRING },
                      description: { type: Type.STRING },
                      frequencies: {
                        type: Type.ARRAY,
                        items: {
                          type: Type.OBJECT,
                          properties: {
                            subActivity: { type: Type.OBJECT, properties: { displayName: { type: Type.STRING } }, required: ['displayName'] },
                            displayName: { type: Type.STRING },
                            description: { type: Type.STRING },
                            instruction: { type: Type.STRING },
                            triggerPoint: { type: Type.INTEGER },
                            triggerPointUnits: { type: Type.STRING },
                            frequency: { type: Type.INTEGER },
                            interval: { type: Type.INTEGER },
                            intervalUnits: { type: Type.STRING },
                            createdBy: { type: Type.NULL },
                            updatedBy: { type: Type.NULL },
                            isDeleted: { type: Type.BOOLEAN },
                            media: { type: Type.NULL },
                            createdOn: { type: Type.STRING },
                            updatedOn: { type: Type.STRING },
                          },
                        }
                      },
                      patientActions: { type: Type.ARRAY, items: { type: Type.STRING } },
                      doctorActions: { type: Type.ARRAY, items: { type: Type.STRING } },
                      createdBy: { type: Type.NULL },
                      updatedBy: { type: Type.NULL },
                      isDeleted: { type: Type.BOOLEAN },
                      createdOn: { type: Type.STRING },
                      updatedOn: { type: Type.STRING },
                    }
                  }
                },
                isDeleted: { type: Type.BOOLEAN },
                createdBy: { type: Type.NULL },
                updatedBy: { type: Type.NULL },
                isDefault: { type: Type.BOOLEAN },
                createdOn: { type: Type.STRING },
                updatedOn: { type: Type.STRING },
              }
            }
          }
        },
      }
    },
    required: ['patient_info', 'insights']
  };

// =============================================================================
// SERVER-SIDE FUNCTIONS (for Next.js API routes)
// =============================================================================

export async function translateText(textToTranslate: string): Promise<string> {
    try {
        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash',
            contents: [{ parts: [{ text: textToTranslate }] }],
            config: {
                systemInstruction: 'You are a translation assistant. Translate the user\'s text to English. Output ONLY the translated text, without any additional formatting or conversational phrases.',
            }
        });
        return response.text?.trim() ?? '[Translation Error]';
    } catch (error) {
        console.error('Error translating text:', error);
        return `[Translation Error]`;
    }
}


export async function transcribeAudioFile(
    base64Audio: string, 
    mimeType: string
): Promise<string> {
    const model = 'gemini-2.5-flash';
    try {
        const audioPart = {
            inlineData: {
                mimeType: mimeType,
                data: base64Audio,
            },
        };

        const response = await ai.models.generateContent({
            model: model,
            contents: { parts: [audioPart] },
            config: {
                systemInstruction: "You are an expert transcription and translation AI. Transcribe the provided audio and translate it into English. Your entire output MUST be in English, regardless of the language spoken in the audio.",
            }
        });

        if (!response.text) {
            throw new Error('Failed to transcribe audio - no text returned.');
        }
        return response.text;
    } catch (error) {
        console.error(`Error transcribing with ${model}:`, error);
        throw new Error(`Failed to transcribe audio. Please try again.`);
    }
}

export async function extractMedicalInsights(
    transcript: string,
    promptTemplate: string = MEDICAL_EXTRACTION_PROMPT_TEMPLATE,
    model: string = 'gemini-2.5-pro'
): Promise<any> {
    console.log(`[GeminiService] Starting medical insight extraction with ${model}...`);
    try {
        const prompt = promptTemplate.replace('${transcript}', transcript);

        const response = await ai.models.generateContent({
            model: model,
            contents: [{ parts: [{ text: prompt }] }],
            config: {
                responseMimeType: "application/json",
                responseSchema: medicalInsightsSchema,
                temperature: 0.1,
            }
        });

        const jsonText = response.text;
        if (!jsonText) {
            throw new Error('No text response received from model');
        }
        let cleanedJsonText = jsonText.trim();
        if (cleanedJsonText.startsWith('```json')) {
            cleanedJsonText = cleanedJsonText.substring(7).trim();
        }
        if (cleanedJsonText.endsWith('```')) {
            cleanedJsonText = cleanedJsonText.slice(0, -3).trim();
        }

        const result = JSON.parse(cleanedJsonText);
        console.log('[GeminiService] Medical insight extraction successful.');
        return result;

    } catch (error) {
        console.error(`Error extracting medical insights with ${model}:`, error);
        return { error: 'Failed to parse medical insights. The model may have returned an invalid format or the request failed.' };
    }
}

// Specialized extraction functions for comparison

export async function extractMedicalInsights_Base(transcript: string): Promise<any> {
    return extractMedicalInsights(transcript, MEDICAL_EXTRACTION_PROMPT_BASE, 'gemini-2.5-pro');
}

export async function extractMedicalInsights_Concise(transcript: string): Promise<any> {
    return extractMedicalInsights(transcript, MEDICAL_EXTRACTION_PROMPT_CONCISE, 'gemini-2.5-flash');
}

export async function extractMedicalInsights_Detailed(transcript: string): Promise<any> {
    return extractMedicalInsights(transcript, MEDICAL_EXTRACTION_PROMPT_DETAILED, 'gemini-2.5-pro');
}

// Direct extraction from audio without transcription (for performance comparison)
export async function extractInsightsFromAudio(audioBase64: string, mimeType: string): Promise<any> {
    const model = 'gemini-2.5-flash';
    console.log('[GeminiService] Starting direct insight extraction from audio...');

    try {
        const prompt = MEDICAL_EXTRACTION_PROMPT_CONCISE.replace('${transcript}',
            'AUDIO FILE PROVIDED - Extract medical insights directly from the audio conversation in English.');

        const response = await ai.models.generateContent({
            model: model,
            contents: [{
                parts: [
                    { text: prompt },
                    {
                        inlineData: {
                            data: audioBase64,
                            mimeType: mimeType
                        }
                    }
                ]
            }],
            config: {
                responseMimeType: "application/json",
                responseSchema: medicalInsightsSchema,
                temperature: 0.1,
            }
        });

        const jsonText = response.text;
        if (!jsonText) {
            throw new Error('No text response received from model');
        }
        let cleanedJsonText = jsonText.trim();
        if (cleanedJsonText.startsWith('```json')) {
            cleanedJsonText = cleanedJsonText.substring(7).trim();
        }
        if (cleanedJsonText.endsWith('```')) {
            cleanedJsonText = cleanedJsonText.slice(0, -3).trim();
        }

        const result = JSON.parse(cleanedJsonText);
        console.log('[GeminiService] Direct insight extraction successful.');
        return result;

    } catch (error) {
        console.error(`Error extracting insights directly from audio with ${model}:`, error);
        throw new Error(`Failed to extract insights from audio. Please try again.`);
    }
}