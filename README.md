# Badge GIF Generator

Create animated GIF slideshows from your certification badges and logos. Choose between an **Azure VM deployment** or a fully **offline local version**.

![Badge GIF Example](docs/example.gif)

## 🎯 Features

- **Drag & Drop Upload** - Add your own badge images
- **Searchable Badge Library** - Browse by category (Azure, AWS, Google, CompTIA, Cisco, etc.)
- **Customizable Settings** - Duration, size, background color, grouping
- **Transparent Background Support** - Perfect for presentations
- **Live Preview** - See your GIF before downloading
- **Multi-Badge Frames** - Group multiple badges per frame

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

Deploy to Azure with persistent badge storage and HTTPS:

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
| **HTTPS** | No | Yes (Let's Encrypt) |
| **Persistent** | No | Yes |
| **Cost** | Free | ~$15-30/month |
| **Best For** | Personal use, demos | Team/public access |

## 🤝 Contributing

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Certification badge images are property of their respective organizations
- Built with [Pillow](https://pillow.readthedocs.io/) for image processing
- [FastAPI](https://fastapi.tiangolo.com/) and [Flask](https://flask.palletsprojects.com/) for web serving
