# HPC Management System

This is a desktop application for managing High-Performance Computing (HPC) clusters, developed using PyQt5. The system provides the following main features:

1. SSH Key Management and Auto Login
2. Slurm Job Management (Submit, Monitor, Cancel Jobs)
3. Cluster Node Status Monitoring
4. User Account Management
5. Storage Space Management

## Installation

### Requirements

- Python 3.7+
- PyQt5
- paramiko
- pexpect

### Steps

1. Clone this repository:
   ```
   git clone <repository-url>
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the application:
   ```
   cd my_hpc_app
   python main.py
   ```

## User Guide

### Login

For first-time users, you need to enter your UCI ID and password. The system will automatically generate an SSH key and upload it to the HPC server. After successful login, you can use the key for subsequent logins without entering the password.

### Job Management

1. **View Job List**: The job management interface is displayed by default after login, showing all current jobs
2. **Submit New Job**: Click the "Submit New Job" button, fill in job configuration and edit the script
3. **Job Details**: Double-click a job or right-click and select "Job Details" to view detailed information
4. **Cancel Job**: Right-click on a job and select "Cancel Job"

### Job Script Writing

The system provides Slurm script templates with common parameter configurations that can be modified as needed:

```bash
#!/bin/bash
#SBATCH --job-name=my_job
#SBATCH --partition=default
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --mem=1G
#SBATCH --time=1:00:00
#SBATCH --output=slurm-%j.out

# Load modules
module load python/3.9.0

# Print current working directory
echo "Current working directory: $PWD"
echo "Current node: $(hostname)"

# Add your commands here
echo "Hello, Slurm!"
sleep 10
echo "Job completed"
```

## Common Issues

1. **Login Failure**: Ensure network connection is stable and verify UCI ID and password are correct
2. **Job Submission Failure**: Check script content for syntax errors and verify partition access permissions 