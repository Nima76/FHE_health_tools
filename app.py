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


def upload_file_to_container(container_name, local_files, container_path):
    """Upload multiple files to a specific Docker container with their original names."""
    try:
        for local_file in local_files:
            # Extract the filename from the local file path
            filename = os.path.basename(local_file)
            print(filename)
            # Upload the file to the container with its original name
            if container_name == "enc":
                print(f"docker cp {local_file} {container_name}:{container_path}/table.csv")
                os.system(f"docker cp {local_file} {container_name}:{container_path}/table.csv")
            elif container_name == "dec":
                os.system(f"docker cp {local_file} {container_name}:{container_path}/{filename}")
        return update_status("Files uploaded successfully.")
    except Exception as e:
        return update_status(f"Error uploading files: {str(e)}", error=True)


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
        image_name = 'encryptdev/fhe_health_dec:0.2'
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
    """Upload files for encryption or decryption."""
    mode = request.form.get('mode')
    container_name = 'enc' if mode == 'encryption' else 'dec'
    files = request.files.getlist('file')  # Get all uploaded files

    if not files:
        return update_status("No files uploaded.", error=True)

    # Save files locally and prepare their paths
    local_files = []
    for file in files:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        local_files.append(file_path)
    print(local_files)
    # Specify the destination path in the container
    container_path = '/bdt/build/data'

    # For encryption, rename the file to "table.csv"
    if mode == 'encryption':
        if len(local_files) != 1:
            return update_status("Encryption requires exactly 1 file.", error=True)
        return upload_file_to_container(container_name, local_files, container_path)

    # For decryption, upload all files with their original names
    elif mode == 'decryption':
        if len(local_files) != 3:
            return update_status("Decryption requires exactly 3 files.", error=True)
        return upload_file_to_container(container_name, local_files, container_path)

    else:
        return update_status("Invalid mode selected.", error=True)


@app.route('/start_process', methods=['POST'])
def start_process():
    """Start encryption or decryption process."""
    mode = request.json.get('mode')
    container_name = 'enc' if mode == 'encryption' else 'dec'
    script_name = './encrypt-medical-setup' if mode == 'encryption' else './encrypt-medical-getresult'

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
    container_name = 'enc' if mode == 'encryption' else 'dec'
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
    container_name = 'enc' if mode == 'encryption' else 'dec'

    try:
        container = client.containers.get(container_name)
        container.stop()
        container.remove()
        return update_status(f"Container '{container_name}' removed successfully.")
    except Exception as e:
        return update_status(f"Error removing container: {str(e)}", error=True)

@app.route('/upload_file', methods=['POST'])
def upload_file():
    try:
        print("=====================")
        container_name = 'dec'
        files = request.files.getlist('file')
        print(files)
        file_type = request.form['fileType']
        print(file_type)
        container_path = '/bdt/build/data'

        # Define the target filenames for each file type
        filename_map = {
            'encrypted_result': 'encrypted_result.txt',
            'cryptocontext': 'cryptocontext.txt',
            'key-private': 'key-private.txt',
        }
        if file_type not in filename_map:
            return jsonify({'status': 'Invalid file type.', 'error': True}), 400
        # Save the file to the designated upload folder with the correct filename
        for file in files:
            print("+++++")
            target_filename = filename_map[file_type]
            print(target_filename)
            filename = secure_filename(target_filename)
            print(filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            print(f"{file_path}")
            file.save(file_path)
            print("file_saved")
            print(os.path.basename(file_path))     
            local_files = []
            local_files.append(file_path)   
            upload_file_to_container(container_name, local_files, container_path)
        return jsonify({'status': 'File uploaded successfully.', 'error': False}), 200

        #return jsonify({'status': f'{target_filename} uploaded successfully.', 'error': False}), 200

    except Exception as e:
        return jsonify({'status': f'Error22: {str(e)}', 'error': True}), 500

if __name__ == '__main__':
    app.run(debug=True)
