# from flask import Flask, request, send_file, jsonify, url_for
# import os
# from werkzeug.utils import secure_filename
# import datetime

# # Import the analyze_video function from main.py
# from main import analyze_video

# UPLOAD_FOLDER = 'uploads'
# OUTPUT_FOLDER = 'outputs'
# ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

# app = Flask(__name__)
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# # Ensure the upload and output directories exist
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# @app.route('/analyze', methods=['POST'])
# def handle_analysis_request():
#     """Handles the video upload, analysis, and returns stats and video URL."""
#     if 'video' not in request.files:
#         return jsonify({'error': 'No video file provided'}), 400
    
#     video = request.files['video']
    
#     if video.filename == '':
#         return jsonify({'error': 'No selected file'}), 400
        
#     if not video.filename or not allowed_file(video.filename):
#         return jsonify({'error': 'Unsupported file type'}), 400
    
#     # Create a unique filename to avoid conflicts
#     timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
#     original_filename = secure_filename(video.filename)
#     input_filename = f"{timestamp}_{original_filename}"
#     output_filename = f"{timestamp}_processed_{original_filename}"
    
#     input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
#     output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
    
#     video.save(input_path)
    
#     try:
#         # Call the refactored analysis function
#         analysis_stats = analyze_video(input_path, output_path)
#     except Exception as e:
#         # Log the full error for debugging
#         print(f"Error during video processing: {e}")
#         return jsonify({'error': f'Processing failed: {str(e)}'}), 500
    
#     if not os.path.exists(output_path):
#         return jsonify({'error': 'Analysis ran, but the output file was not created.'}), 500
        
#     # Generate the full URL for the processed video
#     video_url = url_for('get_processed_video', filename=output_filename, _external=True)

#     # Combine stats and video URL into a single response
#     response_data = {
#         'message': 'Analysis complete',
#         'processed_video_url': video_url,
#         'analysis_data': analysis_stats
#     }
    
#     return jsonify(response_data), 200

# @app.route('/videos/<filename>')
# def get_processed_video(filename):
#     """Serves the processed video files."""
#     return send_file(os.path.join(app.config['OUTPUT_FOLDER'], filename), as_attachment=True)

# @app.route('/')
# def index():
#     return 'Cricket Ball Tracking API. POST a video to /analyze.'

# @app.route('/health')
# def health_check():
#     """Health check endpoint for Railway"""
#     return jsonify({'status': 'healthy', 'message': 'Cricket Ball Tracking API is running'})

# if __name__ == '__main__':
#     # Get port from environment variable or default to 5000
#     port = int(os.environ.get('PORT', 5000))
#     app.run(host='0.0.0.0', port=port, debug=False)




from flask import Flask, request, send_file, jsonify, url_for
import os
from werkzeug.utils import secure_filename
import datetime
import uuid
import threading

# Import the analyze_video function from main.py
from main import analyze_video

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# Ensure the upload and output directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# In-memory dictionary to store job statuses.
# In a production-grade application, you would use a database or Redis for this.
JOBS = {}

def run_analysis_in_background(job_id, input_path, output_path):
    """A wrapper function to run video analysis and update job status."""
    try:
        print(f"--- Starting background analysis for job {job_id} ---")
        analysis_stats = analyze_video(input_path, output_path)
        JOBS[job_id] = {
            'status': 'complete',
            'stats': analysis_stats,
            'output_filename': os.path.basename(output_path)
        }
        print(f"--- Finished background analysis for job {job_id} ---")
    except Exception as e:
        print(f"!!! Analysis failed for job {job_id}: {e} !!!")
        JOBS[job_id] = {'status': 'failed', 'error': str(e)}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/analyze', methods=['POST'])
def handle_analysis_request():
    """
    Handles video upload, starts analysis in the background, 
    and returns a job ID.
    """
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    video = request.files['video']
    
    if video.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if not video.filename or not allowed_file(video.filename):
        return jsonify({'error': 'Unsupported file type'}), 400
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    original_filename = secure_filename(video.filename)
    input_filename = f"{timestamp}_{original_filename}"
    output_filename = f"{timestamp}_processed_{original_filename}"
    
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
    
    video.save(input_path)
    
    job_id = str(uuid.uuid4())
    
    # Start the analysis in a background thread
    thread = threading.Thread(
        target=run_analysis_in_background,
        args=(job_id, input_path, output_path)
    )
    thread.start()
    
    # Store initial job status
    JOBS[job_id] = {'status': 'processing'}
    
    # Return the job ID to the client
    return jsonify({
        'message': 'Analysis started.',
        'job_id': job_id,
        'status_url': url_for('get_analysis_result', job_id=job_id, _external=True)
    }), 202

@app.route('/results/<job_id>', methods=['GET'])
def get_analysis_result(job_id):
    """Provides the status and result of an analysis job."""
    job = JOBS.get(job_id)

    if not job:
        return jsonify({'error': 'Invalid job ID'}), 404

    if job['status'] == 'processing':
        return jsonify({'status': 'processing', 'message': 'Analysis is still in progress.'})
    
    if job['status'] == 'failed':
        return jsonify({'status': 'failed', 'error': job.get('error', 'An unknown error occurred.')}), 500

    if job['status'] == 'complete':
        video_url = url_for('get_processed_video', filename=job['output_filename'], _external=True)
        return jsonify({
            'status': 'complete',
            'processed_video_url': video_url,
            'analysis_data': job['stats']
        })

    return jsonify({'error': 'Unknown job status'}), 500

@app.route('/videos/<filename>')
def get_processed_video(filename):
    """Serves the processed video files."""
    return send_file(os.path.join(app.config['OUTPUT_FOLDER'], filename), as_attachment=True)

@app.route('/')
def index():
    return 'Cricket Ball Tracking API. POST a video to /analyze.'

@app.route('/health')
def health_check():
    """Health check endpoint for Railway"""
    return jsonify({'status': 'healthy', 'message': 'Cricket Ball Tracking API is running'})

if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
