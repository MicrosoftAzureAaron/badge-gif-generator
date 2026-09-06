# Badge GIF Generator - VM Deployment Script
# Deploys a Linux VM with Public IP and connects Azure Front Door directly to the VM.
# Assets are persistently stored in GitHub and loaded directly onto the local VM.

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroupName = "rg-badge-gif-vm",
    
    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus2",
    
    [Parameter(Mandatory=$false)]
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\id_rsa.pub",
    
    [Parameter(Mandatory=$false)]
    [bool]$CreateStorageAccount = $false,
    
    [Parameter(Mandatory=$false)]
    [string]$AfdResourceGroup = "layer7lab",

    [Parameter(Mandatory=$false)]
    [string]$AfdProfileName = "hightechlife-lab-afd",

    [Parameter(Mandatory=$false)]
    [string]$AfdOriginGroupName = "badge-og",

    [Parameter(Mandatory=$false)]
    [string]$AfdOriginName = "badge-agw-origin",

    [Parameter(Mandatory=$false)]
    [string]$GithubRepo = "https://github.com/MicrosoftAzureAaron/badge-gif-generator.git",
    
    [Parameter(Mandatory=$false)]
    [string]$GithubBranch = "main"
)

$ErrorActionPreference = "Stop"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Badge GIF Generator - VM Deployment" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "GitHub Repo: $GithubRepo" -ForegroundColor Cyan
Write-Host "GitHub Branch: $GithubBranch" -ForegroundColor Cyan
Write-Host "Storage Mode: GitHub Local VM Storage (CreateStorageAccount=$CreateStorageAccount)" -ForegroundColor Green
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

# Check for SSH key
Write-Host ""
Write-Host "Checking SSH key..." -ForegroundColor Yellow
if (-not (Test-Path $SshKeyPath)) {
    $edPath = "$env:USERPROFILE\.ssh\id_ed25519.pub"
    if (Test-Path $edPath) {
        $SshKeyPath = $edPath
    } else {
        Write-Host "SSH key not found at $SshKeyPath" -ForegroundColor Yellow
        Write-Host "Generating new RSA SSH key pair..." -ForegroundColor Yellow
        ssh-keygen -t rsa -b 4096 -f "$env:USERPROFILE\.ssh\id_rsa" -N '""'
        $SshKeyPath = "$env:USERPROFILE\.ssh\id_rsa.pub"
    }
}

$sshPublicKey = (Get-Content $SshKeyPath -Raw).Trim()
Write-Host "Using SSH public key from: $SshKeyPath" -ForegroundColor Green

# Create resource group with autodeletion cleanup tags
Write-Host ""
Write-Host "Creating resource group: $ResourceGroupName in $Location with autodeletion cleanup tags..." -ForegroundColor Yellow
az group create --name $ResourceGroupName --location $Location `
    --tags cleanupPolicy="Delete" cleanupScope="ResourceGroup" costProfile="ephemeral" deleteAfterUtc="2026-09-06T23:59:59Z" environment="lab" owner="aarosanders@microsoft.com" solution="BadgeGIFGenerator" `
    --output none

# Deploy infrastructure
Write-Host ""
Write-Host "Deploying VM infrastructure (this may take 3-5 minutes)..." -ForegroundColor Yellow

$scriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$templatePath = Join-Path $scriptDir "infrastructure\main-vm.bicep"

$deploymentOutput = az deployment group create `
    --resource-group $ResourceGroupName `
    --template-file "$templatePath" `
    --parameters baseName="badgegifgen" `
    --parameters location="$Location" `
    --parameters adminUsername="azureuser" `
    --parameters sshPublicKey="$sshPublicKey" `
    --parameters createStorageAccount=$($CreateStorageAccount.ToString().ToLower()) `
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
$sshCommand = $deploymentOutput.sshCommand.value
$websiteUrl = $deploymentOutput.websiteUrl.value

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "Infrastructure Deployed!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Resources:" -ForegroundColor Cyan
Write-Host "  VM Name: $vmName"
Write-Host "  VM Public IP: $vmPublicIp"
Write-Host "  VM FQDN: $vmFqdn"
Write-Host ""
Write-Host "Updating Azure Front Door origin to point directly to VM FQDN ($vmFqdn)..." -ForegroundColor Yellow
az afd origin update `
    --resource-group $AfdResourceGroup `
    --profile-name $AfdProfileName `
    --origin-group-name $AfdOriginGroupName `
    --origin-name $AfdOriginName `
    --host-name "$vmFqdn" `
    --origin-host-header "$vmFqdn" `
    --http-port 80 `
    --https-port 443 `
    --enabled-state Enabled `
    --output none 2>&1 | Out-Null

Write-Host "Azure Front Door origin updated successfully!" -ForegroundColor Green

# Wait for VM setup to complete
Write-Host ""
Write-Host "Waiting for VM setup script to clone GitHub repo and start services (45 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 45

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Direct VM Access:" -ForegroundColor Cyan
Write-Host "  HTTP:  $websiteUrl"
Write-Host "  SSH:   $sshCommand"
Write-Host ""
Write-Host "Public Domain via Azure Front Door:" -ForegroundColor Cyan
Write-Host "  https://badge.hightechlife.net" -ForegroundColor White
Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Direct VM Access:" -ForegroundColor Cyan
Write-Host "  HTTP:  $websiteUrl"
Write-Host "  SSH:   $sshCommand"
Write-Host ""
Write-Host "Public Domain via Azure Front Door:" -ForegroundColor Cyan
Write-Host "  https://badge.hightechlife.net" -ForegroundColor White
Write-Host ""
