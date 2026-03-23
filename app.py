from flask import Flask, render_template, request, send_file, after_this_request, jsonify
import os
import time
from datetime import datetime
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import img2pdf

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'output'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'rtf', 'jpg', 'jpeg', 'png', 'gif', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def cleanup_old_files(folder_path, max_age_seconds=3600):
    """Delete files older than 60 minutes"""
    try:
        now = time.time()
        for filename in os.listdir(folder_path):
            filepath = os.path.join(folder_path, filename)
            if os.path.isfile(filepath):
                if now - os.path.getmtime(filepath) > max_age_seconds:
                    os.remove(filepath)
                    print(f"Cleaned up old file: {filename}")
    except Exception as e:
        print(f"Cleanup error: {e}")

def merge_pdfs(pdf_paths, output_path):
    writer = PdfWriter()
    for pdf_path in pdf_paths:
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                writer.add_page(page)
        except Exception as e:
            print(f"Error merging {pdf_path}: {e}")
    
    with open(output_path, 'wb') as f:
        writer.write(f)
    return output_path

def convert_word_to_pdf(word_path, output_path):
    try:
        from docx2pdf import convert
        convert(word_path, output_path)
        return True
    except:
        try:
            import subprocess
            subprocess.run([
                'libreoffice', '--headless', '--convert-to', 'pdf',
                '--outdir', os.path.dirname(output_path),
                word_path
            ], check=True, timeout=30)
            generated_pdf = os.path.splitext(word_path)[0] + '.pdf'
            if os.path.exists(generated_pdf):
                os.rename(generated_pdf, output_path)
                return True
        except:
            pass
    return False

def convert_image_to_pdf(image_path, output_path):
    """Convert image to PDF with proper A4 fitting"""
    try:
        from PIL import Image
        img = Image.open(image_path)
        
        # A4 dimensions in points (72 DPI)
        A4_WIDTH = 595
        A4_HEIGHT = 842
        MARGIN = 40
        
        # Calculate image dimensions
        img_width, img_height = img.size
        
        # Calculate available space
        avail_width = A4_WIDTH - (MARGIN * 2)
        avail_height = A4_HEIGHT - (MARGIN * 2)
        
        # Calculate scaling factor to fit image within A4
        scale = min(avail_width / img_width, avail_height / img_height)
        
        # New dimensions
        new_width = img_width * scale
        new_height = img_height * scale
        
        # Create PDF with image centered on A4 page
        c = canvas.Canvas(output_path, pagesize=A4)
        x_position = (A4_WIDTH - new_width) / 2
        y_position = (A4_HEIGHT - new_height) / 2
        
        c.drawImage(image_path, x_position, y_position, width=new_width, height=new_height)
        c.save()
        return True
    except Exception as e:
        print(f"Image conversion error: {e}")
        # Fallback to img2pdf
        try:
            with open(output_path, 'wb') as f:
                f.write(img2pdf.convert(image_path))
            return True
        except:
            return False

def convert_text_to_pdf(text_path, output_path):
    try:
        with open(text_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        with open(text_path, 'r', encoding='latin-1') as f:
            content = f.read()
    
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica", 11)
    y_position = height - 50
    lines = content.split('\n')
    
    for line in lines:
        if y_position < 50:
            c.showPage()
            c.setFont("Helvetica", 11)
            y_position = height - 50
        max_chars = 70
        while len(line) > max_chars:
            c.drawString(50, y_position, line[:max_chars])
            y_position -= 15
            line = line[max_chars:]
        c.drawString(50, y_position, line)
        y_position -= 15
    c.save()
    return True

@app.route('/')
def index():
    cleanup_old_files(app.config['UPLOAD_FOLDER'])
    cleanup_old_files(app.config['OUTPUT_FOLDER'])
    return render_template('index.html')

@app.route('/get-files')
def get_files():
    """Get list of current session files"""
    files = []
    try:
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(filepath):
                files.append({
                    'name': filename,
                    'size': os.path.getsize(filepath),
                    'time': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                })
    except Exception as e:
        print(f"Error getting files: {e}")
    return jsonify(files)

@app.route('/delete-file', methods=['POST'])
def delete_file():
    """Manually delete a specific file"""
    try:
        filename = request.json.get('filename')
        if filename:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                return jsonify({'success': True, 'message': 'File deleted'})
        return jsonify({'success': False, 'message': 'File not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/delete-all', methods=['POST'])
def delete_all():
    """Manually delete all uploaded files"""
    try:
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
        return jsonify({'success': True, 'message': 'All files deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/combine', methods=['POST'])
def combine_files():
    files_to_delete = []
    try:
        if 'files' not in request.files:
            return "No files uploaded", 400
        
        files = request.files.getlist('files')
        if len(files) == 0:
            return "No files selected", 400
        
        file_order = []
        for i, file in enumerate(files, 1):
            if file and allowed_file(file.filename):
                ext = get_file_extension(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}_{os.urandom(4).hex()}_{file.filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                files_to_delete.append(filepath)
                file_order.append({'path': filepath, 'ext': ext, 'original': file.filename})
        
        if not file_order:
            return "No valid files", 400
        
        temp_pdfs = []
        for info in file_order:
            temp_pdf_path = os.path.join(app.config['OUTPUT_FOLDER'], f"temp_{os.urandom(4).hex()}.pdf")
            if info['ext'] == 'pdf':
                temp_pdfs.append(info['path'])
            elif info['ext'] in ['docx', 'doc']:
                if convert_word_to_pdf(info['path'], temp_pdf_path):
                    temp_pdfs.append(temp_pdf_path)
                    files_to_delete.append(temp_pdf_path)
            elif info['ext'] in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
                if convert_image_to_pdf(info['path'], temp_pdf_path):
                    temp_pdfs.append(temp_pdf_path)
                    files_to_delete.append(temp_pdf_path)
            elif info['ext'] in ['txt', 'rtf']:
                convert_text_to_pdf(info['path'], temp_pdf_path)
                temp_pdfs.append(temp_pdf_path)
                files_to_delete.append(temp_pdf_path)
        
        output_filename = f"combined_{os.urandom(4).hex()}.pdf"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        if temp_pdfs:
            merge_pdfs(temp_pdfs, output_path)
            files_to_delete.append(output_path)
        else:
            return "Conversion failed", 500

        @after_this_request
        def remove_files(response):
            for file_path in files_to_delete:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as error:
                    print(f"Error deleting: {error}")
            return response

        return send_file(output_path, as_attachment=True, download_name="combined_document.pdf")

    except Exception as e:
        for file_path in files_to_delete:
            if os.path.exists(file_path):
                os.remove(file_path)
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)