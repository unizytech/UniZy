#!/usr/bin/env node

/**
 * Cancel a specific Chirp3 operation using CancelOperation RPC
 * Usage: node cancel-operation-direct.js test_3-326d874fdf88556d-b4891
 */

require('dotenv').config({ path: '.env.local' });
const jwt = require('jsonwebtoken');

// Get operation ID from command line
const OPERATION_ID = process.argv[2] || 'test_3-326d874fdf88556d-b4891';

async function getGoogleAccessToken() {
  const credentials = JSON.parse(process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON || '{}');

  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iss: credentials.client_email,
    scope: 'https://www.googleapis.com/auth/cloud-platform',
    aud: 'https://oauth2.googleapis.com/token',
    exp: now + 3600,
    iat: now,
  };

  const token = jwt.sign(payload, credentials.private_key, { algorithm: 'RS256' });

  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=${token}`,
  });

  const data = await response.json();
  return data.access_token;
}

async function cancelOperation(operationId) {
  try {
    console.log('\n╔═══════════════════════════════════════════════════╗');
    console.log('║     Cancel Chirp3 Operation                       ║');
    console.log('╚═══════════════════════════════════════════════════╝\n');

    console.log('🔑 Getting access token...');
    const accessToken = await getGoogleAccessToken();
    console.log('✅ Access token obtained\n');

    const projectId = process.env.GOOGLE_CLOUD_PROJECT_ID || 'gen-lang-client-0903977370';
    const region = 'us';

    // Construct the full operation name
    const operationName = `projects/${projectId}/locations/${region}/operations/${operationId}`;

    console.log(`📋 Operation ID: ${operationId}`);
    console.log(`📋 Full name: ${operationName}\n`);

    // Cancel endpoint
    const cancelUrl = `https://${region}-speech.googleapis.com/v2/${operationName}:cancel`;

    console.log(`🔴 Sending cancel request...`);
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
      console.log('✅ SUCCESS! Operation cancelled!\n');
      console.log('The operation has been stopped and will be marked as CANCELLED.');
      console.log('Check the Transcriptions page in Google Cloud Console.\n');
      return;
    }

    const responseText = await response.text();

    if (!response.ok) {
      console.error('❌ Failed to cancel operation\n');

      try {
        const errorData = JSON.parse(responseText);
        console.error('Error details:');
        console.error(JSON.stringify(errorData, null, 2));
      } catch {
        console.error('Response:', responseText);
      }

      if (response.status === 404) {
        console.log('\n⚠️  Operation not found. Possible reasons:');
        console.log('   • Operation ID is incorrect');
        console.log('   • Operation already completed or deleted');
        console.log('   • Wrong project or region');
      } else if (response.status === 403) {
        console.log('\n⚠️  Permission denied.');
        console.log('   • Service account may lack speech.operations.cancel permission');
      } else if (response.status === 501 || response.status === 405) {
        console.log('\n⚠️  CancelOperation not supported.');
        console.log('   • Use the Delete button in Google Cloud Console instead');
      }
      return;
    }

    console.log('Response:', responseText);

  } catch (error) {
    console.error('\n❌ Exception:', error.message);
    console.error(error.stack);
  }
}

if (!OPERATION_ID) {
  console.error('❌ Usage: node cancel-operation-direct.js <operation-id>');
  console.error('   Example: node cancel-operation-direct.js test_3-326d874fdf88556d-b4891');
  process.exit(1);
}

cancelOperation(OPERATION_ID);
