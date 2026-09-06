// Badge GIF Generator - VM Infrastructure with AFD Integration
// Deploys: Linux VM backend for Azure Front Door, private networking, no public IP
// Version: 2.0.0

targetScope = 'resourceGroup'

@description('Base name for all resources')
@minLength(3)
@maxLength(20)
param baseName string = 'badgegifgen'

@description('Azure region for resources')
param location string = resourceGroup().location

@description('VM admin username')
param adminUsername string = 'azureuser'

@description('SSH public key for VM access (via WireGuard VPN only)')
@secure()
param sshPublicKey string

@description('VM size')
param vmSize string = 'Standard_B2s'

@description('Create a new storage account with private endpoint')
param createStorageAccount bool = true

@description('Existing storage account name (if createStorageAccount = false)')
param existingStorageAccountName string = ''

@description('GitHub repository URL for application code')
param githubRepo string = 'https://github.com/MicrosoftAzureAaron/badge-gif-generator.git'

@description('GitHub branch to deploy from')
param githubBranch string = 'main'

// AFD Integration Parameters
@description('ID of Layer7 main VNET for peering (required)')
param layer7VnetId string

@description('WireGuard NVA IP address for routing return traffic')
param wireGuardNvaIp string = ''

@description('Primary remote network CIDR (e.g., your home network: 192.168.50.0/24)')
param remoteNetworkPrefix string = ''

@description('Secondary remote network CIDR (e.g., your work network: 10.0.0.0/24) - optional')
param remoteNetworkPrefix2 string = ''

@description('Enable automatic OS updates via unattended-upgrades (security + reboot on Sunday 2 AM UTC)')
param enableAutoOsUpdates bool = true

@description('Enable VNET peering to Layer7 main VNET')
param enableVnetPeering bool = true

// Variables
var newStorageAccountName = take(toLower(replace('st${baseName}${uniqueString(resourceGroup().id)}', '-', '')), 24)
var storageAccountName = createStorageAccount ? newStorageAccountName : existingStorageAccountName
var vmSetupBootstrapScript = format('#!/bin/bash\nexport STORAGE_ACCOUNT_NAME="{0}"\nexport GITHUB_REPO="{1}"\nexport GITHUB_BRANCH="{2}"\nexport ENABLE_AUTO_OS_UPDATES="{3}"\n{4}', createStorageAccount ? newStorageAccountName : existingStorageAccountName, githubRepo, githubBranch, string(enableAutoOsUpdates), loadTextContent('vm-setup-github.sh'))
var vmName = 'vm-${baseName}'
var vnetName = 'vnet-${baseName}'
var subnetName = 'snet-backend'
var privateEndpointSubnetName = 'snet-privateendpoints'
var nsgName = 'nsg-${baseName}'
var nicName = 'nic-${baseName}'
var privateEndpointName = 'pe-storage-${baseName}'
var privateDnsZoneName = 'privatelink.blob.${az.environment().suffixes.storage}'
var routeTableName = 'rt-${baseName}'
var peergingName = 'peer-${baseName}-to-layer7'

// Badge VM static IP (within backend subnet)
var badgeVmPrivateIp = '10.30.1.4'
var vnetAddressPrefix = '10.30.0.0/16'
var backendSubnetPrefix = '10.30.1.0/24'
var peSubnetPrefix = '10.30.2.0/24'

// Network Security Group - Badge VM Access Only from AFD Path
resource nsg 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowHTTPFromAppGW'
        properties: {
          priority: 1000
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: '10.10.1.0/24'  // Layer7 App Gateway subnet
          destinationAddressPrefix: '*'
          description: 'Allow HTTP from Layer7 App Gateway'
        }
      }
      {
        name: 'AllowHTTPSFromAppGW'
        properties: {
          priority: 1001
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '10.10.1.0/24'  // Layer7 App Gateway subnet
          destinationAddressPrefix: '*'
          description: 'HTTPS from Layer7 App Gateway'
        }
      }
      {
        name: 'AllowSSHFromWireGuardNVA'
        properties: {
          priority: 1002
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: '100.127.0.0/24'  // WireGuard NVA subnet
          destinationAddressPrefix: '*'
          description: 'SSH access via WireGuard VPN NVA'
        }
      }
      {
        name: 'AllowOutboundInternet'
        properties: {
          priority: 1000
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'Internet'
          description: 'Allow all outbound to internet (for OS updates, package downloads)'
        }
      }
      {
        name: 'AllowOutboundAzure'
        properties: {
          priority: 1001
          direction: 'Outbound'
          access: 'Allow'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'AzureCloud'
          description: 'Allow outbound to Azure services (Key Vault, Storage, etc.)'
        }
      }
    ]
  }
}

// Virtual Network - NEW RANGE: 10.30.0.0/16 (no overlap with Layer7)
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: subnetName
        properties: {
          addressPrefix: backendSubnetPrefix
          networkSecurityGroup: {
            id: nsg.id
          }
          routeTable: {
            id: routeTable.id
          }
        }
      }
      {
        name: privateEndpointSubnetName
        properties: {
          addressPrefix: peSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// Route Table for Badge VM Backend Subnet
// Enables routing to Layer7 VMs and remote clients via WireGuard NVA
resource routeTable 'Microsoft.Network/routeTables@2023-05-01' = {
  name: routeTableName
  location: location
  properties: {
    routes: []
  }
}

// Add dynamic route for remote network if WireGuard parameters provided
resource remoteNetworkRoute 'Microsoft.Network/routeTables/routes@2023-05-01' = if (!empty(wireGuardNvaIp) && !empty(remoteNetworkPrefix)) {
  parent: routeTable
  name: 'RouteToRemoteNetwork'
  properties: {
    addressPrefix: remoteNetworkPrefix
    nextHopType: 'VirtualAppliance'
    nextHopIpAddress: wireGuardNvaIp
  }
}

// Add dynamic route for secondary remote network (e.g., work VLAN) if provided
resource remoteNetworkRoute2 'Microsoft.Network/routeTables/routes@2023-05-01' = if (!empty(wireGuardNvaIp) && !empty(remoteNetworkPrefix2)) {
  parent: routeTable
  name: 'RouteToRemoteNetwork2'
  properties: {
    addressPrefix: remoteNetworkPrefix2
    nextHopType: 'VirtualAppliance'
    nextHopIpAddress: wireGuardNvaIp
  }
}

// Network Interface - Static Private IP
resource nic 'Microsoft.Network/networkInterfaces@2023-05-01' = {
  name: nicName
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: '${vnet.id}/subnets/${subnetName}'
          }
          privateIPAddress: badgeVmPrivateIp
          privateIPAllocationMethod: 'Static'
        }
      }
    ]
  }
}

// Linux VM
resource vm 'Microsoft.Compute/virtualMachines@2023-03-01' = {
  name: vmName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
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
          storageAccountType: 'Premium_LRS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
          properties: {
            primary: true
          }
        }
      ]
    }
  }
}

// Role Assignment for VM managed identity to read storage
resource storageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createStorageAccount) {
  scope: storageAccount
  name: guid(storageAccount.id, vm.id, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')  // Storage Blob Data Reader
    principalId: vm.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = if (createStorageAccount) {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
    minimumTlsVersion: 'TLS1_2'
  }
}

// Blob containers for badges and logos
resource badgesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = if (createStorageAccount) {
  name: '${storageAccountName}/default/ms-badges'
  properties: {
    publicAccess: 'None'
  }
  dependsOn: [
    storageAccount
  ]
}

resource logosContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = if (createStorageAccount) {
  name: '${storageAccountName}/default/ms-logos'
  properties: {
    publicAccess: 'None'
  }
  dependsOn: [
    storageAccount
  ]
}

// Private DNS Zone for Storage Account
resource privateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (createStorageAccount) {
  name: privateDnsZoneName
  location: 'global'
}

// Private DNS Zone Link to Badge VM VNet
resource privateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (createStorageAccount) {
  parent: privateDnsZone
  name: '${vnet.name}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

// Private Endpoint for Storage Account
resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-05-01' = if (createStorageAccount) {
  name: privateEndpointName
  location: location
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/${privateEndpointSubnetName}'
    }
    privateLinkServiceConnections: [
      {
        name: 'storage-pe-connection'
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

// Private Endpoint DNS Group
resource privateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = if (createStorageAccount) {
  parent: privateEndpoint
  name: 'storage-dns-group'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'config'
        properties: {
          privateDnsZoneId: privateDnsZone.id
        }
      }
    ]
  }
}

// VNET Peering - Badge VM to Layer7 Main VNet
resource vnetPeering 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (enableVnetPeering && !empty(layer7VnetId)) {
  name: peergingName
  parent: vnet
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: layer7VnetId
    }
  }
}

// Custom Script Extension for VM setup
resource vmExtension 'Microsoft.Compute/virtualMachines/extensions@2023-03-01' = {
  parent: vm
  name: 'CustomScriptExtension'
  location: location
  properties: {
    publisher: 'Microsoft.Azure.Extensions'
    type: 'CustomScript'
    typeHandlerVersion: '2.0'
    autoUpgradeMinorVersion: true
    forceUpdateTag: uniqueString(vmSetupBootstrapScript)
    protectedSettings: {
      script: base64(vmSetupBootstrapScript)
    }
  }
}

// Outputs
@description('Badge VM private IP address')
output badgeVmPrivateIp string = badgeVmPrivateIp

@description('Badge VM name')
output badgeVmName string = vmName

@description('Virtual Network ID for peering or further configuration')
output vnetId string = vnet.id

@description('Backend subnet ID for routing tables')
output backendSubnetId string = '${vnet.id}/subnets/${subnetName}'

@description('Storage account name (if created)')
output storageAccountName string = createStorageAccount ? storageAccount.name : existingStorageAccountName

@description('Route table ID for reference')
output routeTableId string = routeTable.id

@description('VNET Peering resource ID')
output vnetPeeringId string = enableVnetPeering ? vnetPeering.id : ''

@description('System assigned managed identity principal ID')
output vmManagedIdentityPrincipalId string = vm.identity.principalId
