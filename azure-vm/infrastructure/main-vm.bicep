// Badge GIF Generator - VM-Based Infrastructure
// Deploys: Linux VM, optionally with Storage Account and Private Endpoint

@description('Base name for all resources')
@minLength(3)
param baseName string = 'badgegifgen'

@description('Azure region for resources')
param location string = resourceGroup().location

@description('VM admin username')
param adminUsername string = 'azureuser'

@description('SSH public key for VM access')
@secure()
param sshPublicKey string

@description('VM size')
param vmSize string = 'Standard_B2s'

@description('Email for Let\'s Encrypt certificate registration')
param certEmail string = ''

@description('Create a new storage account and private endpoint, or use an existing one')
param createStorageAccount bool = true

@description('Existing storage account name (required if createStorageAccount is false)')
param existingStorageAccountName string = ''

@description('Resource group containing the existing storage account (required if createStorageAccount is false)')
param existingStorageResourceGroup string = ''

@description('Primary VNet resource ID for peering (required if createStorageAccount is false)')
param primaryVNetId string = ''

@description('GitHub repository URL for application code')
param githubRepo string = 'https://github.com/MicrosoftAzureAaron/badge-gif-generator.git'

@description('GitHub branch to deploy from')
param githubBranch string = 'main'

// Variables
var newStorageAccountName = take(toLower(replace('st${baseName}${uniqueString(resourceGroup().id)}', '-', '')), 24)
var storageAccountName = createStorageAccount ? newStorageAccountName : existingStorageAccountName
var vmName = 'vm-${baseName}'
var vnetName = 'vnet-${baseName}'
var subnetName = 'snet-default'
var privateEndpointSubnetName = 'snet-privateendpoints'
var nsgName = 'nsg-${baseName}'
var publicIpName = 'pip-${baseName}'
var nicName = 'nic-${baseName}'
var privateEndpointName = 'pe-storage-${baseName}'
var privateDnsZoneName = 'privatelink.blob.${az.environment().suffixes.storage}'

// Network Security Group
resource nsg 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowSSH'
        properties: {
          priority: 1000
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowHTTP'
        properties: {
          priority: 1001
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowHTTPS'
        properties: {
          priority: 1002
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// Virtual Network
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.0.0.0/16'
      ]
    }
    subnets: [
      {
        name: subnetName
        properties: {
          addressPrefix: '10.0.1.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
      {
        name: privateEndpointSubnetName
        properties: {
          addressPrefix: '10.0.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// Public IP
resource publicIp 'Microsoft.Network/publicIPAddresses@2023-05-01' = {
  name: publicIpName
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: toLower(baseName)
    }
  }
}

// Network Interface
resource nic 'Microsoft.Network/networkInterfaces@2023-05-01' = {
  name: nicName
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: vnet.properties.subnets[0].id
          }
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
  }
}

// Storage Account (private access only) - only created if createStorageAccount is true
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = if (createStorageAccount) {
  #disable-next-line BCP334
  name: newStorageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'None'
    }
  }
}

// Blob Service
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = if (createStorageAccount) {
  parent: storageAccount
  name: 'default'
}

// Containers
resource logosContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = if (createStorageAccount) {
  parent: blobService
  name: 'ms-logos'
  properties: {
    publicAccess: 'None'
  }
}

resource badgesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = if (createStorageAccount) {
  parent: blobService
  name: 'ms-badges'
  properties: {
    publicAccess: 'None'
  }
}

resource generatedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = if (createStorageAccount) {
  parent: blobService
  name: 'generated'
  properties: {
    publicAccess: 'None'
  }
}

// Private DNS Zone for Blob Storage
resource privateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (createStorageAccount) {
  name: privateDnsZoneName
  location: 'global'
}

// Link DNS Zone to VNet
resource privateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (createStorageAccount) {
  parent: privateDnsZone
  name: '${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

// Private Endpoint for Storage
resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-05-01' = if (createStorageAccount) {
  name: privateEndpointName
  location: location
  properties: {
    subnet: {
      id: vnet.properties.subnets[1].id
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointName
        properties: {
          privateLinkServiceId: storageAccount.id
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

// DNS Zone Group for Private Endpoint
resource privateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = if (createStorageAccount) {
  parent: privateEndpoint
  name: 'dnsgroupname'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'config1'
        properties: {
          privateDnsZoneId: privateDnsZone.id
        }
      }
    ]
  }
}

// ============ Secondary Deployment Resources ============
// These resources are created when using an existing storage account

// VNet Peering: Secondary VNet -> Primary VNet
resource vnetPeeringToPrimary 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (!createStorageAccount && !empty(primaryVNetId)) {
  parent: vnet
  name: 'peer-to-primary'
  properties: {
    remoteVirtualNetwork: {
      id: primaryVNetId
    }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
  }
}

// Link existing DNS Zone to this VNet (for secondary deployments)
module dnsZoneLink 'dns-zone-link.bicep' = if (!createStorageAccount && !empty(existingStorageResourceGroup)) {
  name: 'dns-zone-link-${baseName}'
  scope: resourceGroup(existingStorageResourceGroup)
  params: {
    privateDnsZoneName: privateDnsZoneName
    vnetId: vnet.id
    linkName: '${vnetName}-link'
  }
}

// Linux VM
resource vm 'Microsoft.Compute/virtualMachines@2023-07-01' = {
  name: vmName
  location: location
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshPublicKey
            }
          ]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'Standard_LRS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
  }
  identity: {
    type: 'SystemAssigned'
  }
}

// Role Assignment - Give VM access to Storage Account (only when creating new storage)
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createStorageAccount) {
  name: guid(storageAccount.id, vm.id, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: vm.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Role Assignment for secondary deployments - Grant VM access to existing storage account in primary resource group
module secondaryRoleAssignment 'storage-role-assignment.bicep' = if (!createStorageAccount && !empty(existingStorageResourceGroup)) {
  name: 'role-assignment-${baseName}'
  scope: resourceGroup(existingStorageResourceGroup)
  params: {
    storageAccountName: existingStorageAccountName
    principalId: vm.identity.principalId
  }
}

// Custom Script Extension to setup the VM
var setupScriptContent = loadTextContent('vm-setup-github.sh')
var setupScriptWithEnv = 'export CERT_EMAIL="${certEmail}"\nexport CERT_DOMAIN="${publicIp.properties.dnsSettings.fqdn}"\nexport STORAGE_ACCOUNT_NAME="${storageAccountName}"\nexport GITHUB_REPO="${githubRepo}"\nexport GITHUB_BRANCH="${githubBranch}"\n${setupScriptContent}'

resource vmExtension 'Microsoft.Compute/virtualMachines/extensions@2023-07-01' = {
  parent: vm
  name: 'setupScript'
  location: location
  properties: {
    publisher: 'Microsoft.Azure.Extensions'
    type: 'CustomScript'
    typeHandlerVersion: '2.1'
    autoUpgradeMinorVersion: true
    settings: {
      script: base64(setupScriptWithEnv)
    }
  }
}

// Outputs
output vmPublicIp string = publicIp.properties.ipAddress
output vmFqdn string = publicIp.properties.dnsSettings.fqdn
output vmName string = vm.name
output storageAccountName string = storageAccountName
output storageAccountCreated bool = createStorageAccount
output sshCommand string = 'ssh ${adminUsername}@${publicIp.properties.ipAddress}'
output websiteUrl string = 'http://${publicIp.properties.dnsSettings.fqdn}'
