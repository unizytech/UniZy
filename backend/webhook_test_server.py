#!/usr/bin/env python3
"""
Simple webhook test server for testing webhook integration.

This server receives webhook POST requests and displays the payload
in a formatted way for debugging purposes.

Usage:
    python webhook_test_server.py

Then configure your backend/.env:
    WEBHOOK_URL=http://localhost:5001/webhook,http://localhost:5002/webhook
    WEBHOOK_ENABLED=true

Or expose with ngrok for testing:
    ngrok http 5001
    WEBHOOK_URL=https://your-ngrok-url.ngrok.io/webhook
"""

from flask import Flask, request, jsonify
from datetime import datetime
import json
import os
import multiprocessing
import sys

def create_app(port):
    """Create Flask app instance for a specific port."""
    app = Flask(f"webhook_server_{port}")

    # Store received webhooks for review (per-server)
    webhooks_received = []

    # Get expected token from environment (should match backend's WEBHOOK_TOKEN)
    EXPECTED_TOKEN = os.getenv('WEBHOOK_TOKEN', '')

    # Color codes for different servers
    colors = {
        5001: '\033[94m',  # Blue
        5002: '\033[92m',  # Green
    }
    RESET = '\033[0m'
    COLOR = colors.get(port, '\033[0m')

    @app.route('/webhook', methods=['POST'])
    def webhook():
        """Receive and display webhook payload."""
        try:
            # Validate Authorization header
            auth_header = request.headers.get('Authorization', '')
            if EXPECTED_TOKEN:
                if not auth_header.startswith('Bearer '):
                    print(f"{COLOR}[Port {port}]{RESET} ❌ Missing or invalid Authorization header")
                    return jsonify({
                        'status': 'error',
                        'message': 'Missing Authorization header'
                    }), 401

                token = auth_header.replace('Bearer ', '')
                if token != EXPECTED_TOKEN:
                    print(f"{COLOR}[Port {port}]{RESET} ❌ Invalid webhook token")
                    return jsonify({
                        'status': 'error',
                        'message': 'Invalid webhook token'
                    }), 401

                print(f"{COLOR}[Port {port}]{RESET} ✅ Token validated successfully")

            payload = request.json

            # Store webhook
            webhooks_received.append({
                'timestamp': datetime.utcnow().isoformat(),
                'payload': payload
            })

            # Print formatted output with port identifier
            print("\n" + COLOR + "=" * 80 + RESET)
            print(f"{COLOR}🔔 WEBHOOK RECEIVED - PORT {port}{RESET}")
            print(COLOR + "=" * 80 + RESET)
            print(f"Time: {datetime.utcnow().isoformat()}Z")

            # Metadata (standardized structure)
            metadata = payload.get('metadata', {})
            print(f"Source: {metadata.get('source', 'N/A')}")
            print(f"Timestamp: {metadata.get('timestamp', 'N/A')}")
            print(COLOR + "-" * 80 + RESET)

            # Session/extraction info from metadata
            print("METADATA:")
            print(f"  Correlation ID: {metadata.get('correlation_id', 'N/A')}")
            print(f"  Submission ID: {metadata.get('submission_id', 'N/A')}")
            print(f"  Extraction ID: {metadata.get('extraction_id', 'N/A')}")
            print(f"  Counsellor ID: {metadata.get('counsellor_id', 'N/A')}")
            print(f"  Student ID: {metadata.get('student_id', 'N/A')}")
            print(f"  Template Code: {metadata.get('template_code', 'N/A')}")
            print(f"  Mode: {metadata.get('mode', 'N/A')}")
            print(f"  Processing Mode: {metadata.get('processing_mode', 'N/A')}")
            print(f"  Segment Count: {metadata.get('segment_count', 'N/A')}")
            print("-" * 80)

            # Insights
            insights = payload.get('insights', {})
            print("INSIGHTS:")
            if isinstance(insights, dict):
                print(f"  Total Segments: {len(insights)}")
                print(f"  Segments: {', '.join(insights.keys())}")
            else:
                print(f"  Type: {type(insights).__name__}")

            # Show sample data from first 3 segments
            print("\n  Sample Data (first 3 segments):")
            items = list(insights.items())[:3] if isinstance(insights, dict) else []
            for i, (segment_key, segment_data) in enumerate(items):
                # Handle different data structures
                if isinstance(segment_data, dict):
                    # If it's a dict, try to get 'data' key or stringify the dict
                    data = segment_data.get('data', segment_data)
                elif isinstance(segment_data, list):
                    # If it's a list, show length or first item
                    data = f"[List with {len(segment_data)} items]" if len(segment_data) > 3 else str(segment_data)
                else:
                    # Otherwise use the value directly (string, number, etc.)
                    data = segment_data

                # Truncate long strings
                if isinstance(data, str) and len(data) > 100:
                    data = data[:100] + "..."
                elif not isinstance(data, str):
                    # Convert non-strings to string for display
                    data = str(data)[:100]

                print(f"    {segment_key}: {data}")

            print(COLOR + "=" * 80 + RESET + "\n")

            # Return success response
            return jsonify({
                'status': 'success',
                'message': f'Webhook received successfully on port {port}',
                'port': port,
                'received_at': datetime.utcnow().isoformat() + 'Z'
            }), 200

        except Exception as e:
            print(f"{COLOR}[Port {port}]{RESET} ❌ ERROR processing webhook: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e),
                'port': port
            }), 500


    @app.route('/webhooks', methods=['GET'])
    def list_webhooks():
        """List all received webhooks."""
        return jsonify({
            'port': port,
            'total': len(webhooks_received),
            'webhooks': webhooks_received
        }), 200


    @app.route('/webhooks/clear', methods=['POST'])
    def clear_webhooks():
        """Clear webhook history."""
        webhooks_received.clear()
        return jsonify({
            'status': 'success',
            'message': f'Webhook history cleared (port {port})',
            'port': port
        }), 200


    @app.route('/', methods=['GET'])
    def home():
        """Home page with instructions."""
        return f"""
    <html>
    <head>
        <title>Webhook Test Server</title>
        <style>
            body { font-family: monospace; padding: 20px; max-width: 800px; margin: 0 auto; }
            pre { background: #f4f4f4; padding: 10px; border-radius: 5px; }
            .status { color: green; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>🔔 Webhook Test Server - Port {port}</h1>
        <p class="status">✅ Server is running</p>

        <h2>Endpoints:</h2>
        <ul>
            <li><strong>POST /webhook</strong> - Receive webhooks</li>
            <li><strong>GET /webhooks</strong> - List received webhooks</li>
            <li><strong>POST /webhooks/clear</strong> - Clear webhook history</li>
        </ul>

        <h2>Configuration:</h2>
        <pre>
# Add to backend/.env:
WEBHOOK_URL=http://localhost:{port}/webhook
WEBHOOK_ENABLED=true
WEBHOOK_TIMEOUT=10
        </pre>

        <h2>Usage:</h2>
        <ol>
            <li>Configure webhook URL in backend/.env</li>
            <li>Restart backend server</li>
            <li>Record audio or upload file in VHR screen</li>
            <li>Watch console output for webhook payloads</li>
        </ol>

        <h2>Stats:</h2>
        <p>Webhooks received: <strong>{{count}}</strong></p>
        <p><a href="/webhooks">View all webhooks</a></p>
    </body>
    </html>
    """.format(port=port, count=len(webhooks_received))

    return app


def run_server(port):
    """Run a Flask server on the specified port."""
    app = create_app(port)

    # Get expected token from environment
    EXPECTED_TOKEN = os.getenv('WEBHOOK_TOKEN', '')

    # Color codes for different servers
    colors = {
        5001: '\033[94m',  # Blue
        5002: '\033[92m',  # Green
    }
    RESET = '\033[0m'
    COLOR = colors.get(port, '\033[0m')

    print(f"{COLOR}{'=' * 80}{RESET}")
    print(f"{COLOR}🔔 WEBHOOK TEST SERVER - PORT {port}{RESET}")
    print(f"{COLOR}{'=' * 80}{RESET}")
    print(f"Server starting on {COLOR}http://localhost:{port}{RESET}")
    print()
    print("Configuration:")
    print(f"  WEBHOOK_URL=http://localhost:{port}/webhook")
    print("  WEBHOOK_ENABLED=true")
    print("  WEBHOOK_TOKEN=<same_token_as_backend>")
    print()
    if EXPECTED_TOKEN:
        print(f"{COLOR}✅ Token authentication: ENABLED{RESET}")
    else:
        print(f"⚠️  Token authentication: DISABLED (set WEBHOOK_TOKEN env var)")
    print()
    print("Endpoints:")
    print(f"  POST http://localhost:{port}/webhook     - Receive webhooks")
    print(f"  GET  http://localhost:{port}/webhooks    - List received webhooks")
    print(f"  POST http://localhost:{port}/webhooks/clear - Clear webhook history")
    print(f"{COLOR}{'=' * 80}{RESET}")
    print()

    # Disable Flask's default logger to reduce noise
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    # Read ports from environment or use defaults
    ports_str = os.getenv('WEBHOOK_PORTS', '5001,5002')
    ports = [int(p.strip()) for p in ports_str.split(',') if p.strip()]

    print("\n" + "=" * 80)
    print("🔔 MULTI-PORT WEBHOOK TEST SERVER")
    print("=" * 80)
    print(f"Starting {len(ports)} webhook servers: {', '.join(map(str, ports))}")
    print()
    print("Configuration for backend/.env:")
    print(f"  WEBHOOK_URL={','.join([f'http://localhost:{p}/webhook' for p in ports])}")
    print("  WEBHOOK_ENABLED=true")
    print("=" * 80)
    print()

    if len(ports) == 1:
        # Run single server without multiprocessing
        run_server(ports[0])
    else:
        # Start multiple servers using multiprocessing
        processes = []
        for port in ports:
            p = multiprocessing.Process(target=run_server, args=(port,))
            p.start()
            processes.append(p)

        try:
            # Wait for all processes
            for p in processes:
                p.join()
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down all webhook servers...")
            for p in processes:
                p.terminate()
            for p in processes:
                p.join()
            print("✅ All servers stopped")
