import os
import docker
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, flash
from werkzeug.utils import secure_filename
import zipfile

import secrets

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './uploads'
app.config['RESULT_FOLDER'] = './results'

client = docker.from_env()
app.secret_key = secrets.token_hex(16)  # Generates a secure random key

# Create upload and result folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)


# def update_status(message):
#     """Updates the status in the web interface."""
#     print(message)  # This will be printed to console for logs.

def update_status(message):
    """Updates the status in the web interface."""
    flash(message)

def pull_docker_image():
    """Pull Docker image."""
    try:
        #update_status("Pulling Docker image...")
        client.images.pull('encryptdev/fhe_health_data_encryption')
        #update_status("Image pulled successfully! Ready to run container.")
    except Exception as e:
        update_status(f"Error pulling image: {e}")

def run_docker_container():
    """Run Docker container with a specific name."""
    try:
        # Check if container already exists
        existing_container = None
        for container in client.containers.list(all=True):
            if container.name == 'fhe_data_encryption':
                existing_container = container
                break

        # If the container exists, remove it
        if existing_container:
            #update_status("Existing container found. Removing it...")
            existing_container.stop()
            existing_container.remove()
            #update_status("Existing container removed.")

        # Now run a new container
        #update_status("Starting container...")
        container = client.containers.run(
            'encryptdev/fhe_health_data_encryption',
            name='fhe_data_encryption',  # Named container
            detach=True,
            tty=True
        )
        update_status("Container running! Ready to upload data.")
        return container
    except Exception as e:
        update_status(f"Error starting container: {e}")
        return None

def upload_file_to_container(container, local_file, container_path):
    """Upload a file to the Docker container using `docker cp`."""
    try:
        #update_status(f"Uploading {local_file} to container...")
        os.system(f"docker cp {local_file} fhe_data_encryption:/bdt/data")
        update_status("File uploaded! Ready for encryption.")
    except Exception as e:
        update_status(f"Error uploading file: {e}")

def initiate_encryption(container):
    """Start the encryption process inside the container."""
    try:
        #update_status("Starting encryption process...")
        exec_log = container.exec_run('./encrypt-medical-setup', stream=True)
        for line in exec_log.output:
            print(line.decode().strip())
        update_status("Encryption complete! Ready to create ZIP.")
    except Exception as e:
        update_status(f"Error during encryption: {e}")

def create_zip_from_results2(container, result_dir="/bdt/results2", zip_name="results.zip"):
    """Create a ZIP file from the results directory inside the container using Python's zipfile."""
    try:
        #update_status(f"Creating ZIP from results directory...")

        # Multi-line Python code to create ZIP inside the container
        python_code = f"""
import zipfile
import os

with zipfile.ZipFile("/bdt/{zip_name}", "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk("{result_dir}"):
        for file in files:
            if not file.startswith("."):
                archive_name = os.path.relpath(os.path.join(root, file), "{result_dir}")
                z.write(os.path.join(root, file), archive_name)
        """

        # Running the code inside the container
        exec_log = container.exec_run(f"python3 -c '{python_code}'")

        if exec_log.exit_code == 0:
            print("ZIP created successfully, Ready to Download it")
        else:
            update_status(f"Error creating ZIP file: {exec_log.output.decode().strip()}")
            print(f"Error: {exec_log.output.decode().strip()}")
    except Exception as e:
        update_status(f"Error creating ZIP file: {e}")
        print(f"Error: {e}")

def download_results_from_container(container, container_path, local_path):
    try:
        #print(f"Downloading results from {container_path}...")
        bits, stat = container.get_archive(container_path)
        
        # Write the bits to a local file
        with open(os.path.join(local_path, 'results.zip'), 'wb') as f:
            for chunk in bits:
                f.write(chunk)
        
        update_status("Downloading of results has started! Once the download is complete, you may delete the container")
    except Exception as e:
        print(f"Error downloading results: {e}")


def remove_docker_container():
    """Stop and remove Docker container."""
    try:
        container = client.containers.get('fhe_data_encryption')
        container.stop()
        container.remove()
        update_status("Container removed successfully!")
    except Exception as e:
        update_status(f"Error removing container: {e}")


@app.route('/remove_container', methods=['POST'])
def remove_container():
    remove_docker_container()
    return redirect(url_for('home'))

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        container = client.containers.get('fhe_data_encryption')
        upload_file_to_container(container, file_path, '/bdt/data')
        return redirect(url_for('home'))
    return "Error: No file uploaded", 400


@app.route('/start_encryption', methods=['POST'])
def start_encryption():
    container = client.containers.get('fhe_data_encryption')
    initiate_encryption(container)
    return redirect(url_for('home'))


@app.route('/setup_environment', methods=['POST'])
def setup_environment():
    """Pull Docker image and run container."""
    pull_docker_image()
    run_docker_container()
    return redirect(url_for('home'))


@app.route('/download_encrypted_data', methods=['POST'])
def download_encrypted_data():
    """Create ZIP file and download encrypted data."""
    container = client.containers.get('fhe_data_encryption')
    create_zip_from_results2(container)
    download_results_from_container(container, '/bdt/results', app.config['RESULT_FOLDER'])
    return send_from_directory(app.config['RESULT_FOLDER'], 'results.zip', as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
