# Badge GIF Generator - VM Deployment Script
# Deploys a Linux VM with Azure Front Door / Layer7 VNet integration, WireGuard routing, and private storage endpoint

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroupName = "rg-badge-gif-vm",
    
    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus2",
    
    [Parameter(Mandatory=$false)]
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\id_ed25519.pub",
    
    [Parameter(Mandatory=$false)]
    [string]$CertEmail = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ExistingStorageAccountName = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ExistingStorageResourceGroup = "",
    
    [Parameter(Mandatory=$false)]
    [string]$Layer7VnetId = "/subscriptions/93737354-fb93-4823-949a-71c853b20439/resourceGroups/layer7lab/providers/Microsoft.Network/virtualNetworks/hightechlife-lab-vnet",

    [Parameter(Mandatory=$false)]
    [string]$Layer7VnetName = "hightechlife-lab-vnet",

    [Parameter(Mandatory=$false)]
    [string]$Layer7BackendSubnetId = "/subscriptions/93737354-fb93-4823-949a-71c853b20439/resourceGroups/layer7lab/providers/Microsoft.Network/virtualNetworks/hightechlife-lab-vnet/subnets/backend-subnet",

    [Parameter(Mandatory=$false)]
    [string]$Layer7ResourceGroup = "layer7lab",

    [Parameter(Mandatory=$false)]
    [string]$WireGuardNvaIp = "100.127.0.4",

    [Parameter(Mandatory=$false)]
    [string]$RemoteNetworkPrefix = "192.168.50.0/24",

    [Parameter(Mandatory=$false)]
    [string]$RemoteNetworkPrefix2 = "192.168.30.0/24",

    [Parameter(Mandatory=$false)]
    [string]$GithubRepo = "https://github.com/MicrosoftAzureAaron/badge-gif-generator.git",
    
    [Parameter(Mandatory=$false)]
    [string]$GithubBranch = "main"
)

$ErrorActionPreference = "Stop"

# Determine if we're creating storage or using existing
$createStorage = [string]::IsNullOrEmpty($ExistingStorageAccountName)

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Badge GIF Generator - VM Deployment (AFD/VPN)" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "GitHub Repo: $GithubRepo" -ForegroundColor Cyan
Write-Host "GitHub Branch: $GithubBranch" -ForegroundColor Cyan
if (-not $createStorage) {
    Write-Host "MODE: Secondary deployment (using existing storage)" -ForegroundColor Yellow
    Write-Host "  Storage Account: $ExistingStorageAccountName" -ForegroundColor Yellow
} else {
    Write-Host "MODE: Primary deployment (creating new storage)" -ForegroundColor Green
}
Write-Host ""

# Check Azure CLI
Write-Host "Checking Azure CLI..." -ForegroundColor Yellow
try {
    az --version | Out-Null
} catch {
    Write-Error "Azure CLI is not installed. Please install it from https://aka.ms/installazurecli"
    exit 1
}

# Check if logged in
Write-Host "Checking Azure login status..." -ForegroundColor Yellow
$accountInfo = az account show 2>&1 | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in. Please log in to Azure..." -ForegroundColor Yellow
    az login
    $accountInfo = az account show | ConvertFrom-Json
}

# Get email from Azure account if not provided
if ([string]::IsNullOrEmpty($CertEmail)) {
    $CertEmail = $accountInfo.user.name
    Write-Host "Using email from Azure subscription: $CertEmail" -ForegroundColor Green
}

# Check for SSH key
Write-Host ""
Write-Host "Checking SSH key..." -ForegroundColor Yellow
if (-not (Test-Path $SshKeyPath)) {
    $rsaPath = "$env:USERPROFILE\.ssh\id_rsa.pub"
    if (Test-Path $rsaPath) {
        $SshKeyPath = $rsaPath
    } else {
        Write-Host "SSH key not found at $SshKeyPath" -ForegroundColor Yellow
        Write-Host "Generating new ED25519 SSH key pair..." -ForegroundColor Yellow
        ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\id_ed25519" -N '""'
        $SshKeyPath = "$env:USERPROFILE\.ssh\id_ed25519.pub"
    }
}

$sshPublicKey = (Get-Content $SshKeyPath -Raw).Trim()
Write-Host "Using SSH public key from: $SshKeyPath" -ForegroundColor Green

# Create resource group
Write-Host ""
Write-Host "Creating resource group: $ResourceGroupName in $Location" -ForegroundColor Yellow
az group create --name $ResourceGroupName --location $Location --output none

# Deploy infrastructure
Write-Host ""
Write-Host "Deploying VM infrastructure (this may take 5-10 minutes)..." -ForegroundColor Yellow
if (-not $createStorage) {
    Write-Host "Storage: Using existing ($ExistingStorageAccountName)" -ForegroundColor Cyan
} else {
    Write-Host "Storage: Creating new storage account" -ForegroundColor Cyan
}

$scriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$templatePath = Join-Path $scriptDir "infrastructure\main-vm-afd.bicep"

$deploymentOutput = az deployment group create `
    --resource-group $ResourceGroupName `
    --template-file "$templatePath" `
    --parameters baseName="badgegifgen" `
    --parameters location="$Location" `
    --parameters adminUsername="azureuser" `
    --parameters sshPublicKey="$sshPublicKey" `
    --parameters createStorageAccount=$($createStorage.ToString().ToLower()) `
    --parameters existingStorageAccountName="$ExistingStorageAccountName" `
    --parameters layer7VnetId="$Layer7VnetId" `
    --parameters wireGuardNvaIp="$WireGuardNvaIp" `
    --parameters remoteNetworkPrefix="$RemoteNetworkPrefix" `
    --parameters remoteNetworkPrefix2="$RemoteNetworkPrefix2" `
    --parameters githubRepo="$GithubRepo" `
    --parameters githubBranch="$GithubBranch" `
    --query "properties.outputs" `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    Write-Error "Deployment failed!"
    exit 1
}

$vmPrivateIp = $deploymentOutput.badgeVmPrivateIp.value
$vmName = $deploymentOutput.badgeVmName.value
$storageAccountName = $deploymentOutput.storageAccountName.value
$vnetId = $deploymentOutput.vnetId.value

Write-Host ""
Write-Host "Setting up reciprocal VNet peerings between WireGuardNVA and Badge VM VNet..." -ForegroundColor Yellow
az network vnet peering create --resource-group WireGuardNVA --vnet-name WGNVA --name WGNVA-to-badgegifgen --remote-vnet "$vnetId" --allow-vnet-access --allow-forwarded-traffic --output none 2>&1 | Out-Null
az network vnet peering create --resource-group $ResourceGroupName --vnet-name "vnet-badgegifgen" --name badgegifgen-to-WGNVA --remote-vnet "/subscriptions/93737354-fb93-4823-949a-71c853b20439/resourceGroups/WireGuardNVA/providers/Microsoft.Network/virtualNetworks/WGNVA" --allow-vnet-access --allow-forwarded-traffic --output none 2>&1 | Out-Null

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "Infrastructure Deployed!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Resources:" -ForegroundColor Cyan
Write-Host "  VM Name: $vmName"
Write-Host "  VM Private IP: $vmPrivateIp"
Write-Host "  Storage Account: $storageAccountName"
Write-Host ""
Write-Host "SSH Access via WireGuard VPN:" -ForegroundColor Cyan
Write-Host "  ssh azureuser@$vmPrivateIp"
Write-Host ""

# Wait for VM to be ready
Write-Host "Waiting for VM setup to finish and seed storage account (60 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 60

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Public Domain via Azure Front Door:" -ForegroundColor Cyan
Write-Host "  https://badge.hightechlife.net" -ForegroundColor White
Write-Host ""
