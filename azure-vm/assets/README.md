# Badge GIF Generator - Azure Assets

This folder contains pre-loaded Microsoft logos and certification badges
that will be uploaded to Azure Blob Storage for use in the web application.

## Folder Structure

```
assets/
├── logos/           # Microsoft corporate logos
│   ├── microsoft-logo.png
│   ├── azure-logo.png
│   └── ...
└── badges/          # Microsoft certification badges
    ├── az-900-azure-fundamentals.png
    ├── az-104-azure-administrator.png
    └── ...
```

## Asset Naming Convention

Use lowercase with hyphens for file names:
- `azure-fundamentals-az-900.png`
- `microsoft-certified-azure-administrator.png`

The filename (without extension) becomes the asset ID and is used for:
- Generating display names (hyphens become spaces, title case)
- Creating searchable tags
- API references

## Uploading Assets to Azure

After deploying the infrastructure, upload assets using Azure CLI:

```powershell
# Get the storage account name from deployment output
$storageAccount = "<storage-account-name>"

# Upload logos
az storage blob upload-batch `
  --destination ms-logos `
  --source assets/logos `
  --account-name $storageAccount

# Upload badges
az storage blob upload-batch `
  --destination ms-badges `
  --source assets/badges `
  --account-name $storageAccount
```

## Supported Formats

- PNG (recommended for badges with transparency)
- JPEG
- GIF
- BMP
- WebP

## Recommended Dimensions

- **Badges**: 200x200 to 500x500 pixels (square)
- **Logos**: Any aspect ratio, recommended max 1000px wide
