// Client-side Gemini service for real-time features
// 🔒 SECURITY: This code uses ephemeral tokens from backend (secure, NOT exposed)
// The backend generates short-lived tokens using the server-side GEMINI_API_KEY
// For batch processing and server-side operations, use backend API routes

'use client';

import { GoogleGenAI, LiveServerMessage, Modality } from "@google/genai";
import { encode, decode, decodeAudioData } from '../utils/audioUtils';
import type { LiveSessionManager, ConversationUpdate, TreatmentTask } from "@lib/types";

const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;

const NUDGE_NURSE_PROMPT = `
You are a highly skilled and empathetic AI nurse practitioner. Your primary role is to have a supportive, bidirectional voice conversation with a patient to encourage adherence to their prescribed medical protocol.

**Core Persona & Expertise:**
- **Identity:** You are a caring, patient, and knowledgeable nurse practitioner.
- **Specialization:** You are an expert in behavioral science, particularly the concepts of choice architecture and libertarian paternalism as described in the book 'Nudge' by Richard Thaler and Cass Sunstein.
- **Primary Objective:** Your goal is to gently guide the patient through the specific tasks in their treatment plan for the day, nudging them towards better health choices and consistent adherence.

**Today's Treatment Protocol:**
Your main goal is to guide the patient through the tasks in the following treatment protocol.

\${treatment_protocol}

**Your Task for this Conversation:**
1.  **Assume the Time:** For this conversation, assume the current time is the **morning of 22/10/2025**.
2.  **Initiate the Conversation:** Review the protocol and identify the tasks scheduled for this morning.
3.  **Start with the First Task:** Begin the conversation by gently checking in with the patient (e.g., "Good morning! How are you feeling today?") and then nudging them towards the first relevant task for the morning (e.g., taking their morning medication).

**Key Behavioral Guidelines:**
1.  **Language Matching:** You MUST detect the primary language the patient is speaking (e.g., Tamil, Hindi, English, etc.) and conduct the entire conversation in that language. Your responses should feel natural and fluent.
2.  **Empathetic Tone:** Always maintain a warm, encouraging, and non-judgmental tone. Your voice should convey empathy and understanding.
3.  **Nudge, Don't Push:**
    - **Avoid Directives:** Do not say "You must take your medicine." Instead, frame it as a choice or a simple, easy step. For example: "It's about that time for your morning tablet, isn't it? Having it with your breakfast can make it easy to remember."
    - **Simplify Choices:** Break down complex protocols into small, manageable steps. Focus on one task at a time.
    - **Use Social Norms (gently):** "Many patients find that setting a reminder on their phone helps them stay on track. It's a popular trick that seems to work well."
    - **Focus on a Positive Future:** "Sticking with this plan is the quickest way to get you back to feeling your best."
    - **Loss Aversion:** Subtly remind them of the benefits they might lose by not adhering. "We've made such good progress; let's keep that momentum going."
4.  **Conversational Flow:**
    - **Listen First:** Allow the patient to speak fully. Do not interrupt.
    - **Ask Open-Ended Questions:** Encourage the patient to share their feelings or any difficulties they are facing. "How have you been feeling since we last spoke?" or "Have you found a good routine for taking the medication?"
    - **Be Responsive:** Your responses should directly address the patient's statements and concerns. Do not sound like a pre-recorded script.
    - **Keep it Concise:** Your spoken turns should be relatively short and easy to understand. Avoid long, complex medical explanations unless asked.

**Interaction Example (Patient speaking Tamil):**
- **Patient:** "இந்த மாத்திரை எல்லாம் எடுக்கவே பிடிக்கல, ஒரே கசப்பா இருக்கு." (I don't like taking these tablets at all, they are so bitter.)
- **Your (Correct) Response in Tamil:** "ஆமாம், சில மாத்திரைகள் அப்படித்தான் இருக்கும், நான் புரிந்துகொள்கிறேன். அதை சாப்பாட்டிற்குப் பிறகு odane எடுத்துக்கொண்டால், அந்த கசப்பு தெரியாது. ஒரு டம்ளர் தண்ணீர் உடன் முழுதாக விழுங்கிப் பாருங்களேன்." (Yes, some tablets can be like that, I understand. If you take it right after your meal, you might not notice the bitterness. Why don't you try swallowing it whole with a full glass of water?)
- **Your (Incorrect) Response:** "You have to take the medicine. It is important for your health." (This is pushy and ignores the patient's language and specific complaint).

Your ultimate goal is to act as a supportive partner in the patient's health journey, using the provided protocol and subtle nudges to foster a sense of autonomy and commitment.
`;

// =============================================================================
// CLIENT-SIDE REAL-TIME FUNCTIONS
// =============================================================================

export async function startLiveTranscriptionSession(
  onTranscriptionUpdate: (text: string, isFinal: boolean) => void,
  onError: (error: Error) => void,
  onOpen: () => void,
  ephemeralToken: string,
  resumeHandle?: string,
  onChunkReady?: (chunkData: string, chunkIndex: number) => Promise<void>  // NEW: Audio chunk upload callback
): Promise<LiveSessionManager> {
  const inputAudioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: INPUT_SAMPLE_RATE });
  let scriptProcessor: ScriptProcessorNode | null = null;
  let mediaStream: MediaStream | null = null;
  let isPaused = false;
  let currentSessionHandle: string | null = resumeHandle || null;
  let source: MediaStreamAudioSourceNode | null = null;

  // NEW: Chunk buffering for audio upload (parallel to Gemini streaming)
  // Buffer ~4 seconds of audio before uploading (16kHz * 4s = 64000 samples)
  const CHUNK_SIZE_SAMPLES = 64000;
  let chunkBuffer: Int16Array[] = [];
  let chunkIndex = 0;

  if (!ephemeralToken) {
    throw new Error("Ephemeral token is required for Gemini Live API");
  }
  const client = new GoogleGenAI({
    apiKey: ephemeralToken,
    httpOptions: { apiVersion: 'v1alpha' }
  });

  const sessionPromise = client.live.connect({
    model: 'gemini-2.5-flash-native-audio-preview-09-2025',
    callbacks: {
      onopen: async () => {
        console.log('[GeminiClient] Session opened.');
        onOpen();
        try {
          if (inputAudioContext.state === 'suspended') {
            await inputAudioContext.resume();
          }

          mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          source = inputAudioContext.createMediaStreamSource(mediaStream);
          scriptProcessor = inputAudioContext.createScriptProcessor(4096, 1, 1);

          scriptProcessor.onaudioprocess = (audioProcessingEvent) => {
            // Skip sending audio when paused
            if (isPaused) return;

            const inputData = audioProcessingEvent.inputBuffer.getChannelData(0);
            const l = inputData.length;
            const int16 = new Int16Array(l);
            for (let i = 0; i < l; i++) {
                int16[i] = inputData[i] * 32767;
            }
            const pcmBlob = {
              data: encode(new Uint8Array(int16.buffer)),
              mimeType: `audio/pcm;rate=${INPUT_SAMPLE_RATE}`,
            };

            // Send to Gemini (existing behavior)
            sessionPromise.then((session) => {
              session.sendRealtimeInput({ media: pcmBlob });
            });

            // NEW: Buffer for chunk upload (parallel to Gemini streaming)
            if (onChunkReady) {
              chunkBuffer.push(int16.slice());  // Copy to buffer

              const totalSamples = chunkBuffer.reduce((sum, arr) => sum + arr.length, 0);
              if (totalSamples >= CHUNK_SIZE_SAMPLES) {
                // Combine and upload
                const combined = new Int16Array(totalSamples);
                let offset = 0;
                for (const arr of chunkBuffer) {
                  combined.set(arr, offset);
                  offset += arr.length;
                }

                // Convert to base64
                const uint8 = new Uint8Array(combined.buffer);
                let binary = '';
                for (let i = 0; i < uint8.length; i++) {
                  binary += String.fromCharCode(uint8[i]);
                }
                const base64 = btoa(binary);

                // Fire-and-forget upload
                onChunkReady(base64, chunkIndex++).catch((err) => {
                  console.warn('[GeminiClient] Chunk upload failed (non-fatal):', err);
                });

                chunkBuffer = [];
              }
            }
          };

          source.connect(scriptProcessor);
          scriptProcessor.connect(inputAudioContext.destination);
        } catch (err) {
          console.error('[GeminiClient] Error during media setup:', err);
          onError(err as Error);
        }
      },
      onmessage: (message: LiveServerMessage) => {
        const content = message.serverContent;
        if (content) {
            if (content.inputTranscription) {
                const text = content.inputTranscription.text;
                if (text) {
                    onTranscriptionUpdate(text, false);
                }
            }

            if (content.turnComplete) {
                onTranscriptionUpdate('', true);
            }
        }

        // Listen for session resumption updates
        const resumptionUpdate = message.sessionResumptionUpdate;
        if (resumptionUpdate) {
            if (resumptionUpdate.resumable && resumptionUpdate.newHandle) {
                currentSessionHandle = resumptionUpdate.newHandle;
                console.log('[GeminiClient] Session handle updated:', currentSessionHandle);
            } else {
                console.log('[GeminiClient] Session not resumable at this point');
            }
        }
      },
      onerror: (e: ErrorEvent) => {
        console.error('[GeminiClient] Live session error:', e);
        onError(e.error || new Error('An unknown live session error occurred.'));
      },
      onclose: () => {
        console.log('[GeminiClient] Session closed.');
      },
    },
    config: {
      responseModalities: [Modality.AUDIO],  // AUDIO required for native audio models
      inputAudioTranscription: {},
      systemInstruction: 'You are a highly accurate medical transcription assistant specializing in multilingual conversations, particularly Tamil and English. Your primary task is to transcribe the user\'s audio input with the highest possible accuracy, paying close attention to medical terminology and code-switching between languages. For example, correctly differentiate between similar-sounding words like "swelling" (வீக்கம்) and "weak". Do not generate any spoken audio response. Your audio output stream must be empty.',
      sessionResumption: {
        handle: resumeHandle || ''  // Use provided handle to resume, or start new session
      },
    }
  });

  const session = await sessionPromise;

  const pause = () => {
    isPaused = true;
    console.log('[GeminiClient] Recording paused');
  };

  const resume = () => {
    isPaused = false;
    console.log('[GeminiClient] Recording resumed');
  };

  const getSessionHandle = () => {
    return currentSessionHandle;
  };

  const close = () => {
    // NEW: Flush remaining audio buffer before closing
    if (onChunkReady && chunkBuffer.length > 0) {
      const totalSamples = chunkBuffer.reduce((sum, arr) => sum + arr.length, 0);
      if (totalSamples > 0) {
        const combined = new Int16Array(totalSamples);
        let offset = 0;
        for (const arr of chunkBuffer) {
          combined.set(arr, offset);
          offset += arr.length;
        }

        // Convert to base64
        const uint8 = new Uint8Array(combined.buffer);
        let binary = '';
        for (let i = 0; i < uint8.length; i++) {
          binary += String.fromCharCode(uint8[i]);
        }
        const base64 = btoa(binary);

        // Fire-and-forget final chunk upload
        onChunkReady(base64, chunkIndex).catch((err) => {
          console.warn('[GeminiClient] Final chunk upload failed (non-fatal):', err);
        });

        console.log(`[GeminiClient] Flushed final chunk ${chunkIndex} (${totalSamples} samples)`);
      }
      chunkBuffer = [];
    }

    if (scriptProcessor) {
      scriptProcessor.disconnect();
      scriptProcessor = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
    }
    if (inputAudioContext.state !== 'closed') {
      inputAudioContext.close();
    }
    if (session) {
      session.close();
    }
  };

  return {
    session,
    close,
    pause,
    resume,
    getSessionHandle,
    isPaused: () => isPaused
  };
}

export async function startLiveConversationSession(
  onUpdate: (update: ConversationUpdate) => void,
  onError: (error: Error) => void,
  onOpen: () => void,
  context: TreatmentTask[],
  ephemeralToken: string,
  resumeHandle?: string
): Promise<LiveSessionManager> {
  const inputAudioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: INPUT_SAMPLE_RATE });
  const outputAudioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: OUTPUT_SAMPLE_RATE });
  const outputNode = outputAudioContext.createGain();
  outputNode.connect(outputAudioContext.destination);

  let scriptProcessor: ScriptProcessorNode | null = null;
  let mediaStream: MediaStream | null = null;
  let nextStartTime = 0;
  const sources = new Set<AudioBufferSourceNode>();
  let isPaused = false;
  let currentSessionHandle: string | null = resumeHandle || null;
  let source: MediaStreamAudioSourceNode | null = null;

  if (!ephemeralToken) {
    throw new Error("Ephemeral token is required for Gemini Live API");
  }
  const client = new GoogleGenAI({
    apiKey: ephemeralToken,
    httpOptions: { apiVersion: 'v1alpha' }
  });

  let systemInstruction = NUDGE_NURSE_PROMPT;
  if (context && context.length > 0) {
    const protocolHeader = `| Task | When to do the task | Instructions for the task |\n|---|---|---|`;
    const protocolRows = context.map(t => `| ${t.task} | ${t.when} | ${t.instructions} |`).join('\n');
    const fullProtocolString = `${protocolHeader}\n${protocolRows}`;
    systemInstruction = systemInstruction.replace('${treatment_protocol}', fullProtocolString);
  } else {
    systemInstruction = systemInstruction.replace('${treatment_protocol}', 'No treatment protocol has been provided for today.');
  }

  const sessionPromise = client.live.connect({
    model: 'gemini-2.5-flash-native-audio-preview-09-2025',
    callbacks: {
      onopen: async () => {
        console.log('[GeminiClient] Conversation session opened.');
        onOpen();
        try {
          if (inputAudioContext.state === 'suspended') await inputAudioContext.resume();
          if (outputAudioContext.state === 'suspended') await outputAudioContext.resume();

          mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          source = inputAudioContext.createMediaStreamSource(mediaStream);
          scriptProcessor = inputAudioContext.createScriptProcessor(4096, 1, 1);

          scriptProcessor.onaudioprocess = (audioProcessingEvent) => {
            // Skip sending audio when paused
            if (isPaused) return;

            const inputData = audioProcessingEvent.inputBuffer.getChannelData(0);
            const l = inputData.length;
            const int16 = new Int16Array(l);
            for (let i = 0; i < l; i++) {
              int16[i] = inputData[i] * 32767;
            }
            const pcmBlob = {
              data: encode(new Uint8Array(int16.buffer)),
              mimeType: `audio/pcm;rate=${INPUT_SAMPLE_RATE}`,
            };
            sessionPromise.then((session) => session.sendRealtimeInput({ media: pcmBlob }));
          };

          source.connect(scriptProcessor);
          scriptProcessor.connect(inputAudioContext.destination);

        } catch (err) {
          console.error('[GeminiClient] Error during conversation media setup:', err);
          onError(err as Error);
        }
      },
      onmessage: async (message: LiveServerMessage) => {
        const content = message.serverContent;
        if (content) {
          if (content.inputTranscription?.text) {
            onUpdate({ speaker: 'user', text: content.inputTranscription.text, isFinal: false });
          }
          if (content.outputTranscription?.text) {
            onUpdate({ speaker: 'ai', text: content.outputTranscription.text, isFinal: false });
          }
          if (content.turnComplete) {
            onUpdate({ speaker: 'user', text: '', isFinal: true });
            onUpdate({ speaker: 'ai', text: '', isFinal: true });
          }

          const audioData = content.modelTurn?.parts?.[0]?.inlineData?.data;
          if (audioData) {
            nextStartTime = Math.max(nextStartTime, outputAudioContext.currentTime);
            const audioBuffer = await decodeAudioData(decode(audioData), outputAudioContext, OUTPUT_SAMPLE_RATE, 1);
            const source = outputAudioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(outputNode);
            source.addEventListener('ended', () => { sources.delete(source); });
            source.start(nextStartTime);
            nextStartTime += audioBuffer.duration;
            sources.add(source);
          }

          if (content.interrupted) {
            for (const source of sources.values()) {
              source.stop();
              sources.delete(source);
            }
            nextStartTime = 0;
          }
        }

        // Listen for session resumption updates
        const resumptionUpdate = message.sessionResumptionUpdate;
        if (resumptionUpdate) {
            if (resumptionUpdate.resumable && resumptionUpdate.newHandle) {
                currentSessionHandle = resumptionUpdate.newHandle;
                console.log('[GeminiClient] Conversation session handle updated:', currentSessionHandle);
            } else {
                console.log('[GeminiClient] Conversation session not resumable at this point');
            }
        }
      },
      onerror: (e: ErrorEvent) => {
        console.error('[GeminiClient] Live conversation error:', e);
        onError(e.error || new Error('An unknown live conversation error occurred.'));
      },
      onclose: () => {
        console.log('[GeminiClient] Conversation session closed.');
      },
    },
    config: {
      responseModalities: [Modality.AUDIO],
      inputAudioTranscription: {},
      outputAudioTranscription: {},
      systemInstruction: systemInstruction,
      sessionResumption: {
        handle: resumeHandle || ''  // Use provided handle to resume, or start new session
      },
    }
  });

  const session = await sessionPromise;

  const pause = () => {
    isPaused = true;
    console.log('[GeminiClient] Conversation paused');
  };

  const resume = () => {
    isPaused = false;
    console.log('[GeminiClient] Conversation resumed');
  };

  const getSessionHandle = () => {
    return currentSessionHandle;
  };

  const close = () => {
    if (scriptProcessor) {
      scriptProcessor.disconnect();
      scriptProcessor = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
    }
    if (inputAudioContext.state !== 'closed') inputAudioContext.close();
    if (outputAudioContext.state !== 'closed') outputAudioContext.close();
    if (session) session.close();
  };

  return {
    session,
    close,
    pause,
    resume,
    getSessionHandle,
    isPaused: () => isPaused
  };
}

