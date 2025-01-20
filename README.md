FHE_Health_Tools is a **Local application** that facilitates encryption of health data using Fully Homomorphic Encryption (FHE). This tool provides a user-friendly interface to securely encrypt sensitive data while running the core logic in a Docker container.

This work is built on top of the repository [MedicalHEClient](https://github.com/JPBultel/MedicalHEClient/tree/main "MedicalHEClient") and is developed as part of the [**ENCRYPT Project**](http://encrypt-project.eu "**ENCRYPT Project**"). The ENCRYPT Project focuses on enabling secure and privacy-preserving data sharing and computation.

# Features
-	Data Encryption: Encrypt health-related data using advanced FHE technology.
-   Docker Integration: Runs securely in an isolated Docker container.
-   Local Interface: Interact through a user-friendly browser-based interface running on localhost.
-	Ease of Use: Minimal setup, designed for simplicity.
_____
## How to Use

#### Step 1: Clone the Repository
Download the project by cloning the GitHub repository:

`git clone <repository_url>`

#### Step 2: Install Requirements

Navigate to the project folder and install the required Python libraries:

`pip install -r requirements.txt `

#### Step 3: Run the Application

Start the application by running the app.py file:

`python3 app.py`

> Note: The application will run by default on localhost port 5000.

#### Step 4: Open in Your Browser

Open your web browser and navigate to:

http://localhost:5000

#### Step 5: Encrypt Your Results

Follow the on-screen instructions to upload your data and perform encryption. The interface will guide you through each step.
_____

## Acknowledgments

This project builds upon the excellent work provided in MedicalHEClient, which serves as the foundational framework for enabling FHE in health data encryption.

It is developed as part of the [**ENCRYPT Project**](http://encrypt-project.eu "**ENCRYPT Project**") which focuses on secure data handling and computation technologies.

##Support

If you encounter any issues or have questions, feel free to open an issue on this repository or reach out for support.
