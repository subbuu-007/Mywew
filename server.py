from http.server import SimpleHTTPRequestHandler, HTTPServer
import json
from urllib.parse import urlparse, parse_qs
from transformers import pipeline
import os
import subprocess

UPLOAD_FOLDER = 'downloads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

class CustomHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers['Content-Length'])
        data = json.loads(self.rfile.read(length))
        if self.path == '/fetch':
            self.handle_fetch(data)
        elif self.path == '/summarize':
            self.handle_summarize(data)

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if self.path.startswith('/download'):
            self.handle_download(query)

    def handle_fetch(self, data):
        video_url = data['url']
        try:
            # Use yt-dlp to fetch captions
            transcript = self.fetch_captions(video_url)
            self.respond({'transcript': transcript})
        except Exception as e:
            self.respond({'error': str(e)}, status=500)

    def fetch_captions(self, url):
        """Fetch captions using yt-dlp."""
        command = [
            "yt-dlp",
            "--write-auto-sub",
            "--skip-download",
            "--sub-lang", "en",
            "--output", "%(id)s",
            "--quiet",
            url,
        ]
        subprocess.run(command, check=True)
        video_id = self.extract_video_id(url)
        caption_file = f"{video_id}.en.vtt"

        if not os.path.exists(caption_file):
            raise FileNotFoundError("Captions not available for this video.")

        with open(caption_file, 'r') as f:
            captions = f.read()

        # Clean up the caption file
        os.remove(caption_file)

        # Extract plain text from VTT format
        return self.parse_vtt(captions)

    def parse_vtt(self, vtt_data):
        """Extract plain text from VTT captions."""
        lines = vtt_data.splitlines()
        text_lines = [line for line in lines if not line.startswith("NOTE") and "-->" not in line and line.strip()]
        return " ".join(text_lines)

    def handle_summarize(self, data):
        text, length = data['text'], data['length']
        max_len = {'short': 50, 'medium': 100, 'long': 200}.get(length, 100)
        summary = summarizer(text, max_length=max_len, min_length=30, do_sample=False)
        self.respond({'summary': summary[0]['summary_text']})

    def handle_download(self, query):
        summary = query.get('summary', [''])[0]
        fmt = query.get('format', ['txt'])[0]
        path = os.path.join(UPLOAD_FOLDER, f'summary.{fmt}')
        with open(path, 'w') as f:
            f.write(summary)
        self.send_response(200)
        self.end_headers()

    def extract_video_id(self, url):
        import re
        match = re.search(r'v=([^&]+)', url)
        return match.group(1) if match else None

    def respond(self, response, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 8080), CustomHandler).serve_forever()
