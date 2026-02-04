// Module to create DNS Zone link from another resource group
// This is needed because the DNS Zone is in the primary resource group
// but we need to link it to VNets in secondary resource groups

param privateDnsZoneName string
param vnetId string
param linkName string

resource privateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing = {
  name: privateDnsZoneName
}

resource dnsZoneVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateDnsZone
  name: linkName
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetId
    }
  }
}

output linkId string = dnsZoneVnetLink.id
