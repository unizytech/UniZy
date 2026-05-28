#!/usr/bin/env node

/**
 * Cancel a specific Chirp3 operation using the CancelOperation RPC
 */

const { getGoogleAccessToken } = require('../app/api/compare-transcribe/route.ts');

// You can change this to any operation ID
const OPERATION_ID = 'test_3-326d874fdf88556d-b4891';

async function cancelOperation(operationId) {
  try {
    console.log('╔═══════════════════════════════════════════════════╗');
    console.log('║     Cancel Chirp3 Operation                       ║');
    console.log('╚═══════════════════════════════════════════════════╝\n');

    const accessToken = await getGoogleAccessToken();
    const projectId = process.env.GOOGLE_CLOUD_PROJECT_ID || 'gen-lang-client-0903977370';
    const region = 'us';

    // Construct the full operation name
    const operationName = `projects/${projectId}/locations/${region}/operations/${operationId}`;

    console.log(`📋 Operation: ${operationName}\n`);

    // Cancel endpoint
    const cancelUrl = `https://${region}-speech.googleapis.com/v2/${operationName}:cancel`;

    console.log(`🔴 Cancelling operation...\n`);
    console.log(`📡 POST ${cancelUrl}\n`);

    const response = await fetch(cancelUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
    });

    console.log(`📊 Response: ${response.status} ${response.statusText}\n`);

    if (response.status === 200 || response.status === 204) {
      console.log('✅ Operation cancelled successfully!\n');
      console.log('The operation will stop processing and be marked as CANCELLED.');
      console.log('It will appear in the Transcriptions list with an error status.\n');
      return;
    }

    const responseText = await response.text();

    if (!response.ok) {
      console.error('❌ Failed to cancel operation\n');
      console.error('Response:', responseText);

      if (response.status === 404) {
        console.log('\n⚠️  Operation not found. It may have already completed or been deleted.');
      } else if (response.status === 403) {
        console.log('\n⚠️  Permission denied. Check your service account permissions.');
      } else if (response.status === 501) {
        console.log('\n⚠️  CancelOperation not implemented for this API version.');
      }
      return;
    }

    console.log('Response:', responseText);

  } catch (error) {
    console.error('❌ Exception:', error.message);
  }
}

// Run with operation ID from command line or use default
const opId = process.argv[2] || OPERATION_ID;

console.log('\n');
cancelOperation(opId);
