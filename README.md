# Badge GIF Generator

Create animated GIF slideshows from your certification badges and logos. This repository stores the application code plus a simple deployment flow that the maintainer uses when adding new badges. It is not a prescriptive reference architecture for end-user Azure hosting.

![Badge GIF Example](docs/example.gif)

## 🎯 Features

- **Drag & Drop Upload** - Add your own badge images
- **Searchable Badge Library** - Browse by category (Azure, AWS, Google, CompTIA, Cisco, etc.)
- **Customizable Settings** - Duration, size, background color, grouping
- **Transparent Background Support** - Perfect for presentations
- **Live Preview** - See your GIF before downloading
- **Multi-Badge Frames** - Group multiple badges per frame

## Scope

- This repository is primarily the source for the badge GIF application code.
- The included Azure VM deployment is a simple maintainer workflow for publishing updates after new badges are added.
- Certificates, domain names, public IPs, access control, Application Gateway, Azure Front Door, and broader production networking decisions are intentionally left to the end user.
- End users should adapt the app to their own security, DNS, ingress, and certificate-management standards.

## 📁 Repository Structure

```
badge-gif-generator/
├── shared/                 # Shared code used by both deployments
│   ├── gif_generator.py    # Core GIF generation logic
│   └── frontend/           # Shared web interface (HTML/CSS/JS)
├── azure-vm/               # Azure VM deployment
│   ├── api/                # FastAPI backend
│   ├── infrastructure/     # Bicep templates & setup scripts
│   └── README.md           # Azure deployment docs
├── offline/                # Standalone offline version
│   ├── src/                # Flask server
│   ├── input/              # Local badge/logo folders
│   └── README.md           # Offline usage docs
└── README.md               # This file
```

## 🚀 Quick Start

### Option 1: Offline Mode (No Azure Required)

Run entirely on your local machine with local badge images:

```powershell
cd offline
pip install -r requirements.txt
python src/server.py
```

Then open http://localhost:5000

📖 **[Offline Mode Documentation](offline/README.md)**

### Option 2: Azure VM Deployment

Use the maintainer's simple Azure VM deployment as a reference starting point:

```powershell
cd azure-vm

# Deploy (pulls code from this GitHub repo)
.\deploy-vm.ps1 `
    -ResourceGroupName "rg-badge-gif-generator" `
    -Location "eastus2"
```

📖 **[Azure VM Documentation](azure-vm/README.md)**

## 🔧 Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| Duration | 1500ms | How long each badge frame displays |
| Logo Duration | 2500ms | How long logo frames display |
| Canvas Size | 320x180 | Output GIF dimensions |
| Background | #FFFFFF | Background color (or "transparent") |
| Group Size | 3 | Number of badges per frame |

## 🏗️ Architecture Comparison

| Feature | Offline Mode | Azure VM |
|---------|-------------|----------|
| **Hosting** | Local machine | Azure Linux VM |
| **Badge Storage** | Local folders | Azure Blob Storage |
| **HTTPS** | No | End-user choice |
| **Persistent** | No | Yes |
| **Cost** | Free | ~$15-30/month |
| **Best For** | Personal use, demos | Maintainer reference deployment |

## 🤝 Contributing

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

**Copyright Notice:** All certification badge images, logos, and trademarks included in this repository are the property of their respective copyright holders, including but not limited to Microsoft, Amazon Web Services, Google, Cisco, CompTIA, and AXELOS (ITIL). No ownership or affiliation is claimed by the repository author.

**Non-Commercial Use Only:** This project is provided for **personal, educational, and non-commercial purposes only**. It is not intended for profit or commercial distribution. The badge images are included solely to demonstrate the functionality of the GIF generator tool.

**Fair Use:** The use of these images is believed to constitute fair use for the purposes of education, personal portfolio creation, and software demonstration. If you are a rights holder and believe your content has been used inappropriately, please open an issue and it will be promptly addressed.

**Your Responsibility:** Users are responsible for ensuring their use of generated GIFs complies with the terms of service and trademark guidelines of the respective certification providers.

## 🙏 Acknowledgments

- Certification badge images are property of their respective organizations
- Built with [Pillow](https://pillow.readthedocs.io/) for image processing
- [FastAPI](https://fastapi.tiangolo.com/) and [Flask](https://flask.palletsprojects.com/) for web serving
