# Badge GIF Generator - VM Deployment Script
# Deploys a Linux VM with optional private storage endpoint

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroupName = "rg-badge-gif-generator-vm",
    
    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus2",
    
    [Parameter(Mandatory=$false)]
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\id_rsa.pub",
    
    [Parameter(Mandatory=$false)]
    [string]$CertEmail = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ExistingStorageAccountName = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ExistingStorageResourceGroup = "",
    
    [Parameter(Mandatory=$false)]
    [string]$PrimaryVNetId = "",
    
    [Parameter(Mandatory=$false)]
    [string]$GithubRepo = "https://github.com/MicrosoftAzureAaron/badge-gif-generator.git",
    
    [Parameter(Mandatory=$false)]
    [string]$GithubBranch = "main"
)

$ErrorActionPreference = "Stop"

# Determine if we're creating storage or using existing
$createStorage = [string]::IsNullOrEmpty($ExistingStorageAccountName)

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Badge GIF Generator - VM Deployment" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "GitHub Repo: $GithubRepo" -ForegroundColor Cyan
Write-Host "GitHub Branch: $GithubBranch" -ForegroundColor Cyan
if (-not $createStorage) {
    Write-Host "MODE: Secondary deployment (using existing storage)" -ForegroundColor Yellow
    Write-Host "  Storage Account: $ExistingStorageAccountName" -ForegroundColor Yellow
    if (-not [string]::IsNullOrEmpty($ExistingStorageResourceGroup)) {
        Write-Host "  Storage RG: $ExistingStorageResourceGroup" -ForegroundColor Yellow
    }
    if (-not [string]::IsNullOrEmpty($PrimaryVNetId)) {
        Write-Host "  VNet Peering: Enabled" -ForegroundColor Yellow
    }
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
    Write-Host "SSH key not found at $SshKeyPath" -ForegroundColor Yellow
    Write-Host "Generating new SSH key pair..." -ForegroundColor Yellow
    ssh-keygen -t rsa -b 4096 -f "$env:USERPROFILE\.ssh\id_rsa" -N '""'
}

$sshPublicKey = Get-Content $SshKeyPath -Raw
Write-Host "Using SSH public key from: $SshKeyPath" -ForegroundColor Green

# Create resource group
Write-Host ""
Write-Host "Creating resource group: $ResourceGroupName in $Location" -ForegroundColor Yellow
az group create --name $ResourceGroupName --location $Location --output none

# Deploy infrastructure
Write-Host ""
Write-Host "Deploying VM infrastructure (this may take 5-10 minutes)..." -ForegroundColor Yellow
Write-Host "Certificate email: $CertEmail" -ForegroundColor Cyan
if (-not $createStorage) {
    Write-Host "Storage: Using existing ($ExistingStorageAccountName)" -ForegroundColor Cyan
} else {
    Write-Host "Storage: Creating new storage account" -ForegroundColor Cyan
}

$deploymentOutput = az deployment group create `
    --resource-group $ResourceGroupName `
    --template-file infrastructure/main-vm.bicep `
    --parameters infrastructure/parameters-vm.json `
    --parameters sshPublicKey="$sshPublicKey" `
    --parameters certEmail="$CertEmail" `
    --parameters createStorageAccount=$($createStorage.ToString().ToLower()) `
    --parameters existingStorageAccountName="$ExistingStorageAccountName" `
    --parameters existingStorageResourceGroup="$ExistingStorageResourceGroup" `
    --parameters primaryVNetId="$PrimaryVNetId" `
    --parameters githubRepo="$GithubRepo" `
    --parameters githubBranch="$GithubBranch" `
    --query "properties.outputs" `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    Write-Error "Deployment failed!"
    exit 1
}

$vmPublicIp = $deploymentOutput.vmPublicIp.value
$vmFqdn = $deploymentOutput.vmFqdn.value
$vmName = $deploymentOutput.vmName.value
$storageAccountName = $deploymentOutput.storageAccountName.value
$storageAccountCreated = $deploymentOutput.storageAccountCreated.value
$sshCommand = $deploymentOutput.sshCommand.value
$websiteUrl = $deploymentOutput.websiteUrl.value
$httpsUrl = "https://$vmFqdn"

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "Infrastructure Deployed!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Resources:" -ForegroundColor Cyan
Write-Host "  VM Name: $vmName"
Write-Host "  VM Public IP: $vmPublicIp"
Write-Host "  VM FQDN: $vmFqdn"
Write-Host "  Storage Account: $storageAccountName $(if ($storageAccountCreated) { '(new)' } else { '(existing)' })"
Write-Host ""
Write-Host "SSH Access:" -ForegroundColor Cyan
Write-Host "  $sshCommand"
Write-Host ""
Write-Host "Website URLs:" -ForegroundColor Cyan
Write-Host "  HTTP:  $websiteUrl"
Write-Host "  HTTPS: $httpsUrl (after certificate setup)"
Write-Host ""

# Wait for VM to be ready
Write-Host "Waiting for VM to initialize and pull code from GitHub (90 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 90

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your Badge GIF Generator is now available at:" -ForegroundColor Cyan
Write-Host "  $websiteUrl" -ForegroundColor White
Write-Host "  $httpsUrl (HTTPS - may take a few minutes for cert)" -ForegroundColor White
Write-Host ""
Write-Host "The VM pulled the application from GitHub:" -ForegroundColor Yellow
Write-Host "  Repository: $GithubRepo"
Write-Host "  Branch: $GithubBranch"
Write-Host ""
Write-Host "To update the application from GitHub, SSH in and run:" -ForegroundColor Yellow
Write-Host "  cd /opt/badge-gif-repo && git pull"
Write-Host "  sudo cp -r api/* /opt/badge-gif-generator/api/"
Write-Host "  sudo cp -r frontend/* /opt/badge-gif-generator/frontend/"
Write-Host "  sudo systemctl restart badge-gif-generator"
Write-Host ""
Write-Host "Storage account: $storageAccountName" -ForegroundColor Cyan
Write-Host "  Badges will be seeded from GitHub assets/ folder if storage is empty" -ForegroundColor Yellow
Write-Host ""
