# UCI-ClusterManager

UCI-ClusterManager is a management tool designed for the High-Performance Computing (HPC) cluster at the University of California, Irvine (UCI). It provides an intuitive graphical interface to help researchers and students use UCI's HPC resources more efficiently.

## Key Features

- **Job Management**: Monitor and manage Slurm jobs with a user-friendly interface
- **Node Status**: View detailed information about compute nodes, including CPU and memory usage
- **VSCode Configuration**: Easily set up VSCode remote development environment
- **Account Balance**: Monitor compute resource usage and quotas
- **Automatic Updates**: Check and install the latest software versions

## System Requirements

- **Windows**: Windows 10 or later
- **macOS**: macOS 10.13 or later
- **Linux**: Ubuntu 18.04+, CentOS 7+, or similar systems

## Installation Instructions

Download the appropriate installer for your operating system from the [Releases page](https://github.com/songliangyu/UCI-ClusterManager/releases):

- Windows: `UCI-ClusterManager-[version]-win64.exe`
- macOS: `UCI-ClusterManager-[version]-macos.dmg`
- Linux: `uci-clustermanager_[version]_amd64.deb`

### Windows Installation
1. Download the .exe installer file
2. Double-click to run the installer
3. Follow the on-screen prompts to complete installation

### macOS Installation
1. Download the .dmg installation file
2. Open the .dmg file
3. Drag the application to the Applications folder
4. When launching for the first time, you may need to right-click the app and select "Open"

### Linux Installation
1. Download the .deb package
2. Run `sudo dpkg -i uci-clustermanager_[version]_amd64.deb`
3. Or install the downloaded .deb file using the Software Center

## User Guide

### First Login
When you first launch the application, you'll need to log in with your UCI account:
1. Enter your UCI ID and password
2. If you have an SSH key, you can choose to authenticate using the key

### Job Management
- View currently running jobs
- Submit new jobs
- Cancel or modify existing jobs
- View job history and statistics

### Node Status
- View real-time status of cluster nodes
- Monitor CPU, memory, and GPU usage
- View detailed node configuration information

### VSCode Integration
- Configure VSCode remote development environment
- Generate and manage SSH configurations
- Quickly launch pre-configured VSCode sessions

## Updates
The software automatically checks for updates and notifies you when new versions are available. You can also manually check for updates through the "Help" menu.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing
Contributions to the UCI-ClusterManager project are welcome. Please check [CONTRIBUTING.md](CONTRIBUTING.md) to learn how to participate.

## Contact
For questions or suggestions, please [submit an issue](https://github.com/songliangyu/UCI-ClusterManager/issues) or contact the project maintainer. 