import os
import docker
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import secrets

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './uploads'
app.config['RESULT_FOLDER'] = './results'

client = docker.from_env()
app.secret_key = secrets.token_hex(16)  # Secure random key

# Create folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)


def update_status(message, error=False):
    """Send a status update to the frontend."""
    return jsonify({"status": message, "error": error})


def pull_docker_image(image_name):
    """Pull the specified Docker image."""
    try:
        client.images.pull(image_name)
        return update_status(f"Pulled Docker image: {image_name}")
    except Exception as e:
        return update_status(f"Error pulling image: {str(e)}", error=True)


def run_docker_container(image_name, container_name):
    """Run a Docker container with the given image and name."""
    try:
        # Stop and remove existing container if needed
        existing_container = None
        for container in client.containers.list(all=True):
            if container.name == container_name:
                existing_container = container
                break

        if existing_container:
            existing_container.stop()
            existing_container.remove()

        # Run the new container
        client.containers.run(
            image_name,
            name=container_name,
            detach=True,
            tty=True
        )
        return update_status(f"Container '{container_name}' is running.")
    except Exception as e:
        return update_status(f"Error starting container: {str(e)}", error=True)


def upload_file_to_container(container_name, local_file, container_path):
    """Upload a file to a specific Docker container."""
    try:
        os.system(f"docker cp {local_file} {container_name}:{container_path}")
        return update_status("File uploaded successfully.")
    except Exception as e:
        return update_status(f"Error uploading file: {str(e)}", error=True)


def create_zip_from_results2(container, result_dir="/bdt/build/results", zip_name="results.zip"):
    """Create a ZIP file from the results directory inside the container using Python's zipfile."""
    try:
        # Multi-line Python code to create ZIP inside the container
        python_code = f"""
import zipfile
import os

with zipfile.ZipFile("/bdt/build/{zip_name}", "w", zipfile.ZIP_DEFLATED) as z:
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
        bits, stat = container.get_archive(container_path)
        
        # Write the bits to a local file
        with open(os.path.join(local_path, 'results.zip'), 'wb') as f:
            for chunk in bits:
                f.write(chunk)
        
        update_status("Downloading of results has started! Once the download is complete, you may delete the container")
    except Exception as e:
        print(f"Error downloading results: {e}")


@app.route('/')
def home():
    """Serve the frontend."""
    return render_template('index.html')


@app.route('/setup_environment', methods=['POST'])
def setup_environment():
    """Setup environment based on selected mode (encryption or decryption)."""
    mode = request.json.get('mode')
    if mode == 'encryption':
        image_name = 'encryptdev/fhe_health_enc:0.1'
        container_name = 'enc'
    elif mode == 'decryption':
        image_name = 'encryptdev/fhe_health_dec:0.1'
        container_name = 'dec'
    else:
        return update_status("Invalid mode selected.", error=True)

    # Pull image and run container
    pull_result = pull_docker_image(image_name)
    if pull_result.json['error']:
        return pull_result

    return run_docker_container(image_name, container_name)


@app.route('/upload', methods=['POST'])
def upload():
    """Upload a file for encryption or decryption."""
    mode = request.form.get('mode')
    container_name = 'fhe_data_encryption' if mode == 'encryption' else 'fhe_result_decryption'
    file = request.files['file']

    if not file:
        return update_status("No file uploaded.", error=True)

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    return upload_file_to_container(container_name, file_path, '/bdt/build/data')


@app.route('/start_process', methods=['POST'])
def start_process():
    """Start encryption or decryption process."""
    mode = request.json.get('mode')
    container_name = 'fhe_data_encryption' if mode == 'encryption' else 'fhe_result_decryption'
    script_name = './encrypt-medical-setup' if mode == 'encryption' else './decrypt-medical-setup'

    try:
        container = client.containers.get(container_name)
        exec_log = container.exec_run(script_name, stream=True)
        for line in exec_log.output:
            print(line.decode().strip())
        return update_status(f"{mode.capitalize()} process completed.")
    except Exception as e:
        return update_status(f"Error during {mode}: {str(e)}", error=True)


@app.route('/download', methods=['POST'])
def download():
    """Download the processed data as a ZIP file."""
    mode = request.json.get('mode')
    container_name = 'fhe_data_encryption' if mode == 'encryption' else 'fhe_result_decryption'
    container = client.containers.get(container_name)

    # Create ZIP file inside the container
    create_zip_from_results2(container)

    # Download the ZIP file
    local_zip_path = os.path.join(app.config['RESULT_FOLDER'], 'results.zip')
    try:
        bits, stat = container.get_archive('/bdt/build/results.zip')
        with open(local_zip_path, 'wb') as f:
            for chunk in bits:
                f.write(chunk)
    except Exception as e:
        return update_status(f"Error downloading results: {str(e)}", error=True)

    # Return the file for download
    return send_from_directory(app.config['RESULT_FOLDER'], 'results.zip', as_attachment=True)

@app.route('/remove_container', methods=['POST'])
def remove_container():
    """Remove the Docker container."""
    mode = request.json.get('mode')
    container_name = 'fhe_data_encryption' if mode == 'encryption' else 'fhe_result_decryption'

    try:
        container = client.containers.get(container_name)
        container.stop()
        container.remove()
        return update_status(f"Container '{container_name}' removed successfully.")
    except Exception as e:
        return update_status(f"Error removing container: {str(e)}", error=True)


if __name__ == '__main__':
    app.run(debug=True)
